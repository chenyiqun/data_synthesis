import argparse
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import requests


DEFAULT_URL = "https://runway.devops.xiaohongshu.com/openai/zhipu/paas/v4/web_search"
DEFAULT_API_KEY = "4325d9d15bb045da86b7178f66890bbb"
# DEFAULT_API_KEY = "1e6fc76b069c443cb807de0f4373ae16"

SEARCH_ENGINES: Dict[str, str] = {
    "search_pro_jina": "search_pro_jina",
    "jina": "search_pro_jina",
    "search_prime": "search_prime",
    "google": "search_prime",
    "search_pro_ms": "search_pro_ms",
    "bing": "search_pro_ms",
    "search_live": "search_live",
    "sogou": "search_live",
    "search_lite": "search_lite",
    "quark": "search_lite",
    "search_plus": "search_plus",
    "baidu": "search_plus",
}

DEFAULT_SEARCH_ALIASES: Tuple[str, ...] = (
    "jina",
    "google",
    "bing",
    "sogou",
    "quark",
    "baidu",
)


@dataclass
class SearchIntent:
    intent: str = ""
    keywords: str = ""
    query: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Any) -> "SearchIntent":
        if not isinstance(raw, Mapping):
            return cls(raw={})
        raw_dict = dict(raw)
        return cls(
            intent=str(raw_dict.get("intent") or ""),
            keywords=str(raw_dict.get("keywords") or ""),
            query=str(raw_dict.get("query") or ""),
            raw=raw_dict,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResult:
    title: str = ""
    content: str = ""
    link: str = ""
    icon: str = ""
    media: str = ""
    publish_date: str = ""
    refer: str = ""
    rank: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Any, rank: int) -> "SearchResult":
        if not isinstance(raw, Mapping):
            return cls(rank=rank, raw={})

        raw_dict = dict(raw)
        return cls(
            title=str(raw_dict.get("title") or ""),
            content=str(raw_dict.get("content") or ""),
            link=str(raw_dict.get("link") or ""),
            icon=str(raw_dict.get("icon") or ""),
            media=str(raw_dict.get("media") or ""),
            publish_date=str(raw_dict.get("publish_date") or ""),
            refer=str(raw_dict.get("refer") or ""),
            rank=rank,
            raw=raw_dict,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SearchResponse:
    alias: str
    engine: str
    query: str
    request_id: str = ""
    response_id: str = ""
    created: Optional[int] = None
    elapsed_seconds: float = 0.0
    intents: List[SearchIntent] = field(default_factory=list)
    results: List[SearchResult] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    payload: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        *,
        alias: str,
        engine: str,
        query: str,
        elapsed_seconds: float,
        payload: Dict[str, Any],
        raw: Dict[str, Any],
    ) -> "SearchResponse":
        raw_intents = raw.get("search_intent") if isinstance(raw, Mapping) else None
        raw_results = raw.get("search_result") if isinstance(raw, Mapping) else None

        intents = [
            SearchIntent.from_raw(item)
            for item in (raw_intents if isinstance(raw_intents, list) else [])
        ]
        results = [
            SearchResult.from_raw(item, rank=index)
            for index, item in enumerate(
                raw_results if isinstance(raw_results, list) else [],
                start=1,
            )
        ]

        return cls(
            alias=alias,
            engine=engine,
            query=query,
            request_id=str(raw.get("request_id") or ""),
            response_id=str(raw.get("id") or ""),
            created=raw.get("created") if isinstance(raw.get("created"), int) else None,
            elapsed_seconds=elapsed_seconds,
            intents=intents,
            results=results,
            raw=dict(raw),
            payload=payload,
        )

    @property
    def ok(self) -> bool:
        return bool(self.results)

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        data = {
            "alias": self.alias,
            "engine": self.engine,
            "query": self.query,
            "request_id": self.request_id,
            "response_id": self.response_id,
            "created": self.created,
            "elapsed_seconds": self.elapsed_seconds,
            "intents": [item.to_dict() for item in self.intents],
            "results": [item.to_dict() for item in self.results],
            "payload": self.payload,
        }
        if include_raw:
            data["raw"] = self.raw
        return data

    def compact(self, limit: int = 3) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "engine": self.engine,
            "query": self.query,
            "request_id": self.request_id,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "result_count": len(self.results),
            "results": [
                {
                    "rank": item.rank,
                    "title": item.title,
                    "link": item.link,
                    "content": item.content,
                    "media": item.media,
                    "publish_date": item.publish_date,
                    "refer": item.refer,
                }
                for item in self.results[:limit]
            ],
        }


class RunwaySearchClient:
    """Client for Runway Zhipu web_search with normalized cross-engine output."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        url: str = DEFAULT_URL,
        timeout: int = 60,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("RUNWAY_API_KEY") or DEFAULT_API_KEY
        if not self.api_key:
            raise ValueError("请传入 api_key，或设置 DEFAULT_API_KEY / RUNWAY_API_KEY")

        self.url = url
        self.timeout = timeout
        self.session = session or requests.Session()

    @staticmethod
    def normalize_engine(search_engine: str) -> str:
        try:
            return SEARCH_ENGINES[search_engine]
        except KeyError as exc:
            supported = ", ".join(sorted(SEARCH_ENGINES))
            raise ValueError(f"不支持的 search_engine: {search_engine}。可选值: {supported}") from exc

    def search(
        self,
        query: str,
        search_engine: str = "google",
        *,
        query_rewrite: bool = False,
        timeout: Optional[int] = None,
        **extra_payload: Any,
    ) -> SearchResponse:
        engine = self.normalize_engine(search_engine)
        payload = {
            "search_engine": engine,
            "search_query": query,
            "query_rewrite": str(query_rewrite).lower(),
        }
        payload.update(extra_payload)

        headers = {"api-key": self.api_key}
        start_time = time.time()
        response = self.session.post(
            self.url,
            headers=headers,
            json=payload,
            timeout=timeout or self.timeout,
        )
        elapsed_seconds = time.time() - start_time

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}; response_text={response.text[:1000]}"
            ) from exc

        raw = response.json()
        if not isinstance(raw, dict):
            raise ValueError(f"接口返回不是 JSON object: {type(raw).__name__}")

        return SearchResponse.from_raw(
            alias=search_engine,
            engine=engine,
            query=query,
            elapsed_seconds=elapsed_seconds,
            payload=payload,
            raw=raw,
        )

    def search_many(
        self,
        query: str,
        search_engines: Iterable[str] = DEFAULT_SEARCH_ALIASES,
        *,
        query_rewrite: bool = False,
        **extra_payload: Any,
    ) -> Dict[str, SearchResponse]:
        responses = {}
        for search_engine in search_engines:
            responses[search_engine] = self.search(
                query,
                search_engine,
                query_rewrite=query_rewrite,
                **extra_payload,
            )
        return responses

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "RunwaySearchClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def normalize_search_engine(search_engine: str) -> str:
    return RunwaySearchClient.normalize_engine(search_engine)


def call_search_api(
    search_engine: str,
    search_query: str,
    *,
    api_key: Optional[str] = None,
    url: str = DEFAULT_URL,
    query_rewrite: bool = False,
    timeout: int = 60,
    **extra_payload: Any,
) -> Dict[str, Any]:
    client = RunwaySearchClient(api_key=api_key, url=url, timeout=timeout)
    try:
        result = client.search(
            search_query,
            search_engine,
            query_rewrite=query_rewrite,
            **extra_payload,
        )
        return {
            "elapsed_seconds": result.elapsed_seconds,
            "payload": result.payload,
            "data": result.raw,
            "normalized": result.to_dict(),
        }
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Runway web_search once.")
    parser.add_argument("--query", default="关节纹太重怎么办", help="search query")
    parser.add_argument("--engine", default="google", help="engine alias or API name")
    parser.add_argument("--limit", type=int, default=3, help="number of results to print")
    parser.add_argument("--raw", action="store_true", help="print raw JSON response")
    args = parser.parse_args()

    with RunwaySearchClient() as client:
        result = client.search(args.query, args.engine)

    print(
        f"{args.engine} 搜索完成，耗时 {result.elapsed_seconds:.4f} 秒，"
        f"结果数 {len(result.results)}"
    )
    if args.raw:
        print(json.dumps(result.raw, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result.compact(limit=args.limit), ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
