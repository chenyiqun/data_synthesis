import os
import time
from typing import Any, Dict, Optional

import requests


DEFAULT_URL = "https://runway.devops.xiaohongshu.com/openai/zhipu/paas/v4/web_search"

# 既支持你给出的 API 名，也支持更容易记的别名。
SEARCH_ENGINES = {
    "search_pro_jina": "search_pro_jina",  # jina 搜索
    "jina": "search_pro_jina",
    "search_prime": "search_prime",  # google 搜索
    "google": "search_prime",
    "search_pro_ms": "search_pro_ms",  # bing 搜索
    "bing": "search_pro_ms",
    "search_live": "search_live",  # sogou 搜索
    "sogou": "search_live",
    "search_lite": "search_lite",  # 夸克搜索
    "quark": "search_lite",
    "search_plus": "search_plus",  # baidu 搜索
    "baidu": "search_plus",
}


def normalize_search_engine(search_engine: str) -> str:
    """把别名或原始 API 名统一成接口需要的 search_engine 值。"""
    try:
        return SEARCH_ENGINES[search_engine]
    except KeyError as exc:
        supported = ", ".join(sorted(SEARCH_ENGINES))
        raise ValueError(f"不支持的 search_engine: {search_engine}。可选值: {supported}") from exc


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
    """
    调用任意一个搜索 API。

    Args:
        search_engine: 搜索 API 名或别名，例如 "search_prime"、"google"、"bing"。
        search_query: 搜索词。
        api_key: 接口密钥；不传时读取环境变量 RUNWAY_API_KEY。
        url: 接口地址，默认使用线上 web_search。
        query_rewrite: 是否开启 query rewrite。
        timeout: 请求超时时间，单位秒。
        **extra_payload: 其他需要透传给接口的字段，例如 request_id。

    Returns:
        dict，包含接口 JSON 响应、请求耗时和实际发送的 payload。
    """
    resolved_api_key = api_key or os.getenv("RUNWAY_API_KEY")
    if not resolved_api_key:
        raise ValueError("请传入 api_key，或先设置环境变量 RUNWAY_API_KEY")

    payload = {
        "search_engine": normalize_search_engine(search_engine),
        "search_query": search_query,
        "query_rewrite": str(query_rewrite).lower(),
    }
    payload.update(extra_payload)

    headers = {"api-key": resolved_api_key}

    start_time = time.time()
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    elapsed_seconds = time.time() - start_time

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(
            f"{exc}; response_text={response.text[:1000]}"
        ) from exc

    return {
        "elapsed_seconds": elapsed_seconds,
        "payload": payload,
        "data": response.json(),
    }


if __name__ == "__main__":
    # 用法 1：推荐把密钥放到环境变量里：
    # export RUNWAY_API_KEY="你的 api-key"
    result = call_search_api("google", "关节纹太重怎么办")
    print(f"google 搜索耗时: {result['elapsed_seconds']:.4f} 秒")
    print(result["data"])

    # 用法 2：切换到任意其他搜索 API，只需要换 search_engine。
    for engine in ["jina", "bing", "sogou", "quark", "baidu"]:
        result = call_search_api(engine, "关节纹太重怎么办")
        print(f"{engine} 搜索耗时: {result['elapsed_seconds']:.4f} 秒")
        print(result["data"])

    # 用法 3：如果接口需要额外字段，可以直接透传。
    result = call_search_api(
        "search_pro_ms",
        "关节纹太重怎么办",
        request_id="demo-request-id",
    )
    print(result["data"])
