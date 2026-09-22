"""Compatibility facade backed by AgentScope 2.0.8."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..llm import LLMConfig, LLMResult
from .agentscope_runtime import AgentScopeRuntime, profile_for


@dataclass
class HarnessContext:
    tenant_id: int
    run_id: str
    agent_id: str
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


class UnifiedHarness:
    """AgentScope-backed execution facade used by existing modules."""

    def __init__(self, emit: Callable[[str, dict[str, Any]], None] | None = None, record_usage: Callable[[LLMResult], None] | None = None) -> None:
        self._emit_callback = emit
        self._record_usage = record_usage
        self._context: HarnessContext | None = None
        self._runtime = AgentScopeRuntime(emit=emit, record_usage=record_usage)

    def emit(self, event_type: str, **payload: Any) -> None:
        if self._emit_callback:
            self._emit_callback(event_type, payload)

    def set_usage_recorder(self, recorder: Callable[[LLMResult], None] | None) -> None:
        self._record_usage = recorder
        self._runtime = AgentScopeRuntime(emit=self._emit_callback, record_usage=recorder)

    def load_context(self, context: HarnessContext) -> None:
        self._context = context
        self.emit("harness/context-loaded", agent_id=context.agent_id, reads=context.reads, writes=context.writes, functions=context.functions, framework="agentscope", framework_version="2.0.8")

    def run_tool(self, name: str, handler: Callable[[], Any]) -> Any:
        self.emit("harness/tool-started", tool=name, framework="agentscope")
        try:
            result = handler()
        except Exception as exc:
            self.emit("harness/tool-failed", tool=name, error_type=type(exc).__name__)
            raise
        self.emit("harness/tool-finished", tool=name, framework="agentscope")
        return result

    def generate_json(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        output = self.generate_text(config, system_prompt, user_prompt)
        parsed = self._parse_json(output)
        self.emit("harness/json-parsed", output_keys=list(parsed.keys()), framework="agentscope")
        return parsed

    def generate_text(self, config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
        return self._runtime.run_sync(profile_id=self._profile_id(), tenant_id=self._tenant_id(), run_id=self._run_id(), config=config, system_prompt=system_prompt, user_prompt=user_prompt, use_mcp=True)

    def generate_text_stream(self, config: LLMConfig, system_prompt: str, user_prompt: str, on_token: Callable[[str], None]) -> str:
        return self._runtime.run_sync(profile_id=self._profile_id(), tenant_id=self._tenant_id(), run_id=self._run_id(), config=config, system_prompt=system_prompt, user_prompt=user_prompt, token_sink=on_token, use_mcp=True)

    def _profile_id(self) -> str:
        agent_id = self._context.agent_id if self._context else "marketing-copilot"
        if agent_id == "market-hotspot-processing":
            return "opportunity-insight"
        if agent_id.startswith("data") or agent_id.startswith("pipeline"):
            return "data-processing"
        return profile_for(agent_id).agent_id

    def _tenant_id(self) -> int:
        return self._context.tenant_id if self._context else 0

    def _run_id(self) -> str:
        return self._context.run_id if self._context else "HARNESS-RUN"

    @staticmethod
    def _parse_json(output: str) -> dict[str, Any]:
        text = output.strip()
        fence = chr(96) * 3
        if text.startswith(fence):
            text = text.split(chr(10), 1)[1].rsplit(fence, 1)[0].strip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("model output must be a JSON object")
        return value

