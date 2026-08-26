from __future__ import annotations

from dataclasses import dataclass

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


class LLMClient:
    def generate(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
        if config.provider_type == "mock":
            return "模拟模型已完成业务推理，输出已通过事实约束、合规规则和人工审核门禁。"

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
        return data["choices"][0]["message"]["content"]
