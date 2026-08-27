"""Shared provider-neutral harness for data and marketing agents."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..llm import LLMClient, LLMConfig


@dataclass
class HarnessContext:
    tenant_id: int
    run_id: str
    agent_id: str
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


class UnifiedHarness:
    """Execute governed agent steps with consistent context and event output."""

    def __init__(self, emit: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self._emit_callback = emit
        self._llm = LLMClient()

    def emit(self, event_type: str, **payload: Any) -> None:
        if self._emit_callback:
            self._emit_callback(event_type, payload)

    def load_context(self, context: HarnessContext) -> None:
        self.emit("harness/context-loaded", agent_id=context.agent_id, reads=context.reads, writes=context.writes, functions=context.functions)

    def run_tool(self, name: str, handler: Callable[[], Any]) -> Any:
        self.emit("harness/tool-started", tool=name)
        try:
            result = handler()
        except Exception as exc:
            self.emit("harness/tool-failed", tool=name, error_type=type(exc).__name__)
            raise
        self.emit("harness/tool-finished", tool=name)
        return result

    def generate_json(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        output = self.generate_text(config, system_prompt, user_prompt)
        parsed = self._parse_json(output)
        self.emit("harness/json-parsed", output_keys=list(parsed.keys()))
        return parsed

    def generate_text(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
        self.emit("harness/model-started", model=config.model_name)
        output = self._llm.generate(config, system_prompt, user_prompt)
        self.emit("harness/model-finished", output_length=len(output))
        return output

    @staticmethod
    def _parse_json(output: str) -> dict[str, Any]:
        text = output.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("model output must be a JSON object")
        return value
