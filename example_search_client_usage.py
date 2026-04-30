import json

from search_api_client import RunwaySearchClient


def demo_single_search() -> None:
    client = RunwaySearchClient()

    response = client.search(
        query="关节纹太重怎么办",
        search_engine="bing",
    )

    print("=== Single API search ===")
    print(f"engine: {response.engine}")
    print(f"request_id: {response.request_id}")
    print(f"elapsed_seconds: {response.elapsed_seconds:.4f}")
    print(f"result_count: {len(response.results)}")

    for item in response.results[:3]:
        print()
        print(f"[{item.rank}] {item.title}")
        print(f"link: {item.link}")
        print(f"media: {item.media}")
        print(f"publish_date: {item.publish_date}")
        print(f"refer: {item.refer}")
        print(f"content: {item.content[:120]}")

    client.close()


def demo_multi_search() -> None:
    with RunwaySearchClient() as client:
        responses = client.search_many(
            query="关节纹太重怎么办",
            search_engines=["jina", "google", "bing", "sogou", "quark", "baidu"],
        )

    print("\n=== Multiple API search ===")
    for name, response in responses.items():
        print(
            f"{name:<6} engine={response.engine:<16} "
            f"results={len(response.results):<2} "
            f"time={response.elapsed_seconds:.4f}s"
        )


def demo_export_normalized_json() -> None:
    with RunwaySearchClient() as client:
        response = client.search(
            query="关节纹太重怎么办",
            search_engine="google",
        )

    normalized_data = response.to_dict(include_raw=False)

    print("\n=== Normalized JSON ===")
    print(json.dumps(normalized_data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    demo_single_search()
    demo_multi_search()
    demo_export_normalized_json()
