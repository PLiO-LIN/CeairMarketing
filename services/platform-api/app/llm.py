from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx


class LLMServiceError(RuntimeError):
    """A sanitized provider error that is safe to surface in traces and APIs."""


RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)


@dataclass
class LLMConfig:
    provider_type: str
    base_url: str
    model_name: str
    api_key: str
    timeout_seconds: int
    temperature: float
    max_tokens: int


@dataclass
class LLMResult:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_name: str = ""


class LLMClient:
    def __init__(self, max_attempts: int = 3, backoff_seconds: float = 0.5) -> None:
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = max(0.0, backoff_seconds)

    def generate(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
        return self.generate_result(config, system_prompt, user_prompt).content

    def generate_result(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> LLMResult:
        if config.provider_type == "mock":
            content = "测试模型已完成业务推理，输出已通过事实约束、合规规则和人工审核门禁。"
            return LLMResult(content=content, prompt_tokens=32, completion_tokens=24, total_tokens=56, model_name=config.model_name)

        endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        payload = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        response = self._request(config, "POST", endpoint, headers=headers, json=payload)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError("Invalid response format from model service") from exc
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        return LLMResult(
            content=str(content),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
            model_name=str(data.get("model") or config.model_name),
        )

    def generate_stream_result(
        self,
        config: LLMConfig,
        system_prompt: str,
        user_prompt: str,
        on_token: Callable[[str], None],
    ) -> LLMResult:
        """Stream provider tokens to the caller while collecting usage metadata."""
        if config.provider_type == "mock":
            result = self.generate_result(config, system_prompt, user_prompt)
            for index in range(0, len(result.content), 8):
                on_token(result.content[index:index + 8])
            return result

        endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        payload = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        timeout_seconds = max(1, config.timeout_seconds)
        timeout = httpx.Timeout(timeout_seconds, connect=min(10, timeout_seconds), write=min(30, timeout_seconds), pool=min(10, timeout_seconds))
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            content_parts: list[str] = []
            usage: dict[str, Any] = {}
            response_model = config.model_name
            try:
                with httpx.Client(timeout=timeout) as client:
                    with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                        if response.status_code in RETRYABLE_STATUS_CODES:
                            response.read()
                            if attempt < self.max_attempts:
                                self._backoff(attempt)
                                continue
                            raise LLMServiceError(f"Model service unavailable (HTTP {response.status_code}; {attempt} attempts)")
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            try:
                                event = json.loads(raw)
                            except ValueError:
                                continue
                            usage = event.get("usage") or usage
                            response_model = str(event.get("model") or response_model)
                            token = self._extract_stream_text(event)
                            if token:
                                content_parts.append(token)
                                on_token(token)
                prompt_tokens = int(usage.get("prompt_tokens") or 0)
                completion_tokens = int(usage.get("completion_tokens") or 0)
                return LLMResult(
                    content="".join(content_parts),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
                    model_name=response_model,
                )
            except RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                if content_parts:
                    raise LLMServiceError("Model stream interrupted after output started") from exc
                if attempt < self.max_attempts:
                    self._backoff(attempt)
                    continue
                raise LLMServiceError(f"Model service connection failed after {attempt} attempts") from exc
            except httpx.HTTPStatusError as exc:
                raise LLMServiceError(f"Model service rejected request (HTTP {exc.response.status_code})") from exc
        raise LLMServiceError("Model service stream failed") from last_error

    @staticmethod
    def _extract_stream_text(event: dict[str, Any]) -> str:
        if event.get("type") == "response.output_text.delta":
            return str(event.get("delta") or "")
        choices = event.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            return ""
        delta = choices[0].get("delta") or choices[0].get("message") or {}
        content = delta.get("content") if isinstance(delta, dict) else ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        return ""

    def list_models(self, config: LLMConfig) -> list[dict[str, Any]]:
        if config.provider_type == "mock":
            return [{"id": config.model_name, "owned_by": "ceair-platform"}]
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        response = self._request(config, "GET", f"{config.base_url.rstrip('/')}/models", headers=headers)
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMServiceError("Invalid response format from model list service") from exc
        items = payload if isinstance(payload, list) else payload.get("data", [])
        return [
            {"id": str(item.get("id")), "owned_by": str(item.get("owned_by") or "")}
            for item in items
            if isinstance(item, dict) and item.get("id")
        ]

    def _request(self, config: LLMConfig, method: str, url: str, **kwargs: Any) -> httpx.Response:
        timeout_seconds = max(1, config.timeout_seconds)
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(10, timeout_seconds),
            write=min(30, timeout_seconds),
            pool=min(10, timeout_seconds),
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.request(method, url, **kwargs)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < self.max_attempts:
                        self._backoff(attempt)
                        continue
                    raise LLMServiceError(f"Model service unavailable (HTTP {response.status_code}; {attempt} attempts)")
                response.raise_for_status()
                return response
            except RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                if attempt < self.max_attempts:
                    self._backoff(attempt)
                    continue
                raise LLMServiceError(f"Model service connection failed after {attempt} attempts") from exc
            except httpx.HTTPStatusError as exc:
                raise LLMServiceError(f"Model service rejected request (HTTP {exc.response.status_code})") from exc
        raise LLMServiceError("Model service request failed") from last_error

    def _backoff(self, attempt: int) -> None:
        if self.backoff_seconds:
            time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
