import json

from gpt_api_client import GPTApiClient


def test_simple_prompt() -> int:
    with GPTApiClient() as client:
        response = client.chat(
            prompt="你好，请用一句话介绍一下大语言模型。",
        )

    print("=== GPT API simple test ===")
    print(f"ok: {response.ok}")
    print(f"status_code: {response.status_code}")
    print(f"model: {response.model}")
    print(f"request_id: {response.request_id}")
    print(f"latency: {response.latency:.2f}s")
    print(f"attempts: {response.attempts}")
    print(f"prompt_tokens: {response.usage.prompt_tokens}")
    print(f"completion_tokens: {response.usage.completion_tokens}")
    print(f"total_tokens: {response.usage.total_tokens}")

    if not response.ok:
        print(f"error: {response.error}")
        return 1

    print("\ncontent:")
    print(response.content)
    return 0


def test_messages() -> int:
    messages = [
        {"role": "system", "content": "你是一个回答简洁的助手。"},
        {"role": "user", "content": "用三点说明 API 客户端封装的好处。"},
    ]

    with GPTApiClient() as client:
        response = client.chat(messages=messages)

    print("\n=== GPT API messages test ===")
    if not response.ok:
        print(f"error: {response.error}")
        return 1

    print(response.content)
    return 0


def test_export_response_dict() -> int:
    with GPTApiClient() as client:
        response = client.chat(prompt="请只回复 JSON 两个字。")

    print("\n=== Normalized response dict ===")
    print(json.dumps(response.to_dict(include_raw=False), ensure_ascii=False, indent=2))
    return 0 if response.ok else 1


if __name__ == "__main__":
    exit_code = 0
    exit_code |= test_simple_prompt()
    exit_code |= test_messages()
    exit_code |= test_export_response_dict()
    raise SystemExit(exit_code)
