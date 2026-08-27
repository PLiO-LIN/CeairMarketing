from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


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
    def generate(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
        return self.generate_result(config, system_prompt, user_prompt).content

    def generate_result(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> LLMResult:
        if config.provider_type == "mock":
            content = "模拟模型已完成业务推理，输出已通过事实约束、合规规则和人工审核门禁。"
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
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        return LLMResult(
            content=data["choices"][0]["message"]["content"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
            model_name=str(data.get("model") or config.model_name),
        )

    def list_models(self, config: LLMConfig) -> list[dict[str, Any]]:
        if config.provider_type == "mock":
            return [{"id": config.model_name, "owned_by": "ceair-platform"}]
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.get(f"{config.base_url.rstrip('/')}/models", headers=headers)
            response.raise_for_status()
            payload = response.json()
        items = payload.get("data", payload if isinstance(payload, list) else [])
        return [
            {"id": str(item.get("id")), "owned_by": str(item.get("owned_by") or "")}
            for item in items
            if isinstance(item, dict) and item.get("id")
        ]
