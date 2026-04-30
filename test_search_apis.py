import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import requests


DEFAULT_URL = "https://runway.devops.xiaohongshu.com/openai/zhipu/paas/v4/web_search"
DEFAULT_QUERY = "关节纹太重怎么办"

SEARCH_APIS: List[Tuple[str, str]] = [
    ("jina", "search_pro_jina"),
    ("google", "search_prime"),
    ("bing", "search_pro_ms"),
    ("sogou", "search_live"),
    ("quark", "search_lite"),
    ("baidu", "search_plus"),
]


def validate_response(data: Dict[str, Any]) -> List[str]:
    errors = []

    if not isinstance(data, dict):
        return ["response json is not an object"]

    if data.get("error"):
        errors.append(f"response contains error: {data.get('error')}")

    search_result = data.get("search_result")
    if not isinstance(search_result, list):
        errors.append("missing or invalid field: search_result")
    elif not search_result:
        errors.append("search_result is empty")
    else:
        first_result = search_result[0]
        if not isinstance(first_result, dict):
            errors.append("first search_result item is not an object")
        else:
            for field in ("title", "link", "content"):
                if field not in first_result:
                    errors.append(f"first search_result item missing field: {field}")

    return errors


def call_search_api(
    url: str,
    api_key: str,
    engine: str,
    query: str,
    timeout: int,
) -> Dict[str, Any]:
    payload = {
        "search_engine": engine,
        "search_query": query,
        "query_rewrite": "false",
    }
    headers = {"api-key": api_key}

    start_time = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    elapsed_seconds = time.time() - start_time
    response.raise_for_status()

    return {
        "elapsed_seconds": elapsed_seconds,
        "payload": payload,
        "data": response.json(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Test all Runway web_search APIs.")
    parser.add_argument("--url", default=DEFAULT_URL, help="web_search endpoint URL")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="search query")
    parser.add_argument("--timeout", type=int, default=60, help="request timeout seconds")
    parser.add_argument(
        "--dump-json",
        action="store_true",
        help="print each raw JSON response after validation",
    )
    args = parser.parse_args()

    api_key = os.getenv("RUNWAY_API_KEY")
    if not api_key:
        print("ERROR: please set RUNWAY_API_KEY before running this test.", file=sys.stderr)
        return 2

    failed = []
    print(f"Testing {len(SEARCH_APIS)} search APIs with query: {args.query}")

    for alias, engine in SEARCH_APIS:
        try:
            result = call_search_api(
                url=args.url,
                api_key=api_key,
                engine=engine,
                query=args.query,
                timeout=args.timeout,
            )
            errors = validate_response(result["data"])
            result_count = len(result["data"].get("search_result") or [])

            if errors:
                failed.append(alias)
                print(
                    f"[FAIL] {alias:<6} engine={engine:<16} "
                    f"time={result['elapsed_seconds']:.4f}s results={result_count}"
                )
                for error in errors:
                    print(f"       - {error}")
            else:
                print(
                    f"[ OK ] {alias:<6} engine={engine:<16} "
                    f"time={result['elapsed_seconds']:.4f}s results={result_count}"
                )

            if args.dump_json:
                print(json.dumps(result["data"], ensure_ascii=False, indent=2))

        except requests.exceptions.HTTPError as exc:
            failed.append(alias)
            response = exc.response
            response_text = response.text[:1000] if response is not None else ""
            print(f"[FAIL] {alias:<6} engine={engine:<16} HTTP error: {exc}")
            if response_text:
                print(f"       response_text={response_text}")
        except Exception as exc:
            failed.append(alias)
            print(f"[FAIL] {alias:<6} engine={engine:<16} error: {exc}")

    if failed:
        print(f"\nFAILED APIs: {', '.join(failed)}")
        return 1

    print("\nAll APIs returned normal search results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
