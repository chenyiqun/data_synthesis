import json
import os
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import requests


DEFAULT_API_KEY = os.getenv(
    "XHS_API_KEY",
    "QST3c5a3031954a44af7b12a71c3d37f5e7",
)
DEFAULT_API_URL = (
    "https://maas.devops.xiaohongshu.com/runway/global/openai/chat/completions"
    "?api-version=2024-12-01-preview"
)
DEFAULT_MODEL_NAME = os.getenv("XHS_MODEL_NAME", "gpt-5.4")


@dataclass
class GPTUsage:
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Any) -> "GPTUsage":
        if not isinstance(raw, Mapping):
            return cls()

        raw_dict = dict(raw)
        return cls(
            prompt_tokens=raw_dict.get("prompt_tokens"),
            completion_tokens=raw_dict.get("completion_tokens"),
            total_tokens=raw_dict.get("total_tokens"),
            raw=raw_dict,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GPTResponse:
    ok: bool
    content: str = ""
    status_code: Optional[int] = None
    latency: float = 0.0
    attempts: int = 0
    model: str = ""
    request_id: str = ""
    error: str = ""
    usage: GPTUsage = field(default_factory=GPTUsage)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        data = {
            "ok": self.ok,
            "content": self.content,
            "status_code": self.status_code,
            "latency": self.latency,
            "attempts": self.attempts,
            "model": self.model,
            "request_id": self.request_id,
            "error": self.error,
            "usage": self.usage.to_dict(),
        }
        if include_raw:
            data["raw"] = self.raw
        return data

    def raise_for_error(self) -> None:
        if self.ok:
            return
        raise RuntimeError(
            f"GPT API request failed: status={self.status_code}, "
            f"attempts={self.attempts}, error={self.error}"
        )


class GPTApiClient:
    """Small client for the XHS Runway OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        api_url: str = DEFAULT_API_URL,
        model_name: str = DEFAULT_MODEL_NAME,
        timeout: int = 120,
        max_retries: int = 5,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("XHS_API_KEY") or DEFAULT_API_KEY
        if not self.api_key:
            raise ValueError("请传入 api_key，或设置 XHS_API_KEY / DEFAULT_API_KEY")

        self.api_url = api_url
        self.model_name = model_name
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = session or requests.Session()

    def build_headers(self) -> Dict[str, str]:
        return {
            "api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
            "Accept": "application/json",
        }

    def build_payload(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = "You are a helpful assistant.",
        model: Optional[str] = None,
        stream: bool = False,
        **extra_payload: Any,
    ) -> Dict[str, Any]:
        if messages is None:
            if prompt is None:
                raise ValueError("prompt 和 messages 至少需要传入一个")
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

        payload = {
            "model": model or self.model_name,
            "messages": messages,
            "stream": stream,
        }
        payload.update(extra_payload)
        return payload

    @staticmethod
    def safe_decode_response(response: requests.Response) -> str:
        for encoding in ("utf-8", "utf-8-sig", "latin1"):
            try:
                return response.content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return response.text

    @staticmethod
    def _retry_sleep(attempt: int) -> None:
        sleep_time = min(10.0, 0.5 * (2 ** (attempt - 1)))
        sleep_time += random.uniform(0.0, 0.3)
        time.sleep(sleep_time)

    def chat(
        self,
        *,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = "You are a helpful assistant.",
        model: Optional[str] = None,
        stream: bool = False,
        timeout: Optional[int] = None,
        **extra_payload: Any,
    ) -> GPTResponse:
        payload = self.build_payload(
            prompt=prompt,
            messages=messages,
            system_prompt=system_prompt,
            model=model,
            stream=stream,
            **extra_payload,
        )
        headers = self.build_headers()

        started_at = time.time()
        result = GPTResponse(ok=False, model=str(payload.get("model") or ""))

        for attempt in range(1, self.max_retries + 1):
            result.attempts = attempt

            try:
                response = self.session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout or self.timeout,
                )
                raw_text = self.safe_decode_response(response)
                result.status_code = response.status_code

                if response.status_code == 200:
                    try:
                        data = json.loads(raw_text)
                    except Exception as exc:
                        result.error = (
                            f"JSON parse error: {repr(exc)}; "
                            f"raw_text={raw_text[:1000]}"
                        )
                        self._retry_sleep(attempt)
                        continue

                    content = ""
                    try:
                        content = data["choices"][0]["message"]["content"] or ""
                    except Exception:
                        content = ""

                    result.ok = True
                    result.content = content
                    result.latency = time.time() - started_at
                    result.request_id = str(
                        data.get("id")
                        or data.get("request_id")
                        or response.headers.get("x-request-id")
                        or ""
                    )
                    result.usage = GPTUsage.from_raw(data.get("usage"))
                    result.raw = data
                    return result

                result.error = raw_text[:1000]
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    self._retry_sleep(attempt)
                    continue

                result.latency = time.time() - started_at
                return result

            except Exception as exc:
                result.error = repr(exc)
                self._retry_sleep(attempt)

        result.latency = time.time() - started_at
        return result

    def chat_text(self, prompt: str, **kwargs: Any) -> str:
        response = self.chat(prompt=prompt, **kwargs)
        response.raise_for_error()
        return response.content

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "GPTApiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
