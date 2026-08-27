from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.llm import LLMClient, LLMConfig, LLMServiceError


def config() -> LLMConfig:
    return LLMConfig(
        provider_type="openai-compatible",
        base_url="https://model.example/v1",
        model_name="test-model",
        api_key="secret-that-must-not-leak",
        timeout_seconds=30,
        temperature=0.1,
        max_tokens=512,
    )


def response(status_code: int, payload: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload or {},
        request=httpx.Request("POST", "https://model.example/v1/chat/completions"),
    )


class FakeClient:
    def __init__(self, handler: Callable[..., httpx.Response], calls: list[dict]) -> None:
        self.handler = handler
        self.calls = calls

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.handler(method, url, **kwargs)


def install_client(monkeypatch: pytest.MonkeyPatch, handler: Callable[..., httpx.Response]) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: FakeClient(handler, calls))
    return calls


def successful_completion(content: str = "ok") -> httpx.Response:
    return response(200, {
        "model": "test-model",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
    })


def test_retries_retryable_status_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [response(503), response(429), successful_completion("recovered")]
    calls = install_client(monkeypatch, lambda *_args, **_kwargs: outcomes.pop(0))

    result = LLMClient(max_attempts=3, backoff_seconds=0).generate_result(config(), "system", "user")

    assert result.content == "recovered"
    assert result.total_tokens == 16
    assert len(calls) == 3


def test_retries_transient_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(*_args: object, **_kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.RemoteProtocolError("connection closed")
        return successful_completion()

    install_client(monkeypatch, handler)
    assert LLMClient(max_attempts=3, backoff_seconds=0).generate(config(), "system", "user") == "ok"
    assert attempts == 3


def test_does_not_retry_non_retryable_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_client(monkeypatch, lambda *_args, **_kwargs: response(400))

    with pytest.raises(LLMServiceError, match="HTTP 400") as error:
        LLMClient(max_attempts=3, backoff_seconds=0).generate(config(), "system", "user")

    assert len(calls) == 1
    assert config().api_key not in str(error.value)


def test_exhausted_retry_has_sanitized_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = install_client(monkeypatch, lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ReadError("socket EOF")))

    with pytest.raises(LLMServiceError, match="3 attempts") as error:
        LLMClient(max_attempts=3, backoff_seconds=0).generate(config(), "system", "user")

    assert len(calls) == 3
    assert config().api_key not in str(error.value)


def test_rejects_malformed_success_response(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, lambda *_args, **_kwargs: response(200, {"unexpected": True}))

    with pytest.raises(LLMServiceError, match="Invalid response format"):
        LLMClient(backoff_seconds=0).generate(config(), "system", "user")


def test_model_discovery_uses_same_retry_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [response(502), response(200, {"data": [{"id": "qwen", "owned_by": "provider"}]})]
    calls = install_client(monkeypatch, lambda *_args, **_kwargs: outcomes.pop(0))

    models = LLMClient(max_attempts=3, backoff_seconds=0).list_models(config())

    assert models == [{"id": "qwen", "owned_by": "provider"}]
    assert len(calls) == 2
    assert calls[-1]["method"] == "GET"


def test_model_discovery_accepts_top_level_array(monkeypatch: pytest.MonkeyPatch) -> None:
    install_client(monkeypatch, lambda *_args, **_kwargs: httpx.Response(
        200,
        json=[{"id": "qwen-array"}],
        request=httpx.Request("GET", "https://model.example/v1/models"),
    ))

    assert LLMClient(backoff_seconds=0).list_models(config()) == [{"id": "qwen-array", "owned_by": ""}]
