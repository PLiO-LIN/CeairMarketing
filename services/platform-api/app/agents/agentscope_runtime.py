"""AgentScope 2.0.8 adapter for the airline marketing platform.

The API layer stays synchronous for compatibility with the existing FastAPI
routes. Each invocation creates an AgentScope agent, a tenant-scoped local
workspace, a skill set and a short-lived local MCP client. Business writes
remain in the platform services; MCP is deliberately read-oriented.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Callable

from pydantic import BaseModel, SecretStr

from ..llm import LLMConfig, LLMResult

try:
    from agentscope.agent import Agent, ContextConfig, ReActConfig
    from agentscope.credential import OpenAICredential
    from agentscope.event import (
        ModelCallEndEvent,
        ModelCallStartEvent,
        ReplyEndEvent,
        TextBlockDeltaEvent,
        ThinkingBlockDeltaEvent,
        ToolCallStartEvent,
        ToolResultEndEvent,
        ToolResultStartEvent,
        ToolResultTextDeltaEvent,
    )
    from agentscope.message import Msg, TextBlock, ToolCallBlock, UserMsg
    from agentscope.formatter import OpenAIChatFormatter
    from agentscope.mcp import MCPClient, StdioMCPConfig
    from agentscope.model import ChatModelBase, ChatResponse, ChatUsage, OpenAIChatModel
    from agentscope.tool import FunctionTool, Toolkit, ToolChunk
    from agentscope.workspace import LocalWorkspace
    AGENTSCOPE_VERSION = "2.0.8"
except ImportError as exc:  # pragma: no cover - dependency is pinned in requirements
    AGENTSCOPE_VERSION = "unavailable"
    _AGENTSCOPE_IMPORT_ERROR = exc


ROOT = Path(__file__).resolve().parents[2]
PROFILES_PATH = Path(__file__).with_name("profiles.json")
SKILLS_ROOT = Path(__file__).with_name("skills")
WORKSPACES_ROOT = ROOT / ".agent_workspaces"
MCP_SERVER_PATH = Path(__file__).with_name("mcp_server.py")


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    name: str
    skill: str
    workspace: str
    mcp: str
    mcp_tools: list[str]
    system_prompt: str


def _load_profiles() -> dict[str, AgentProfile]:
    payload = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    return {
        agent_id: AgentProfile(agent_id=agent_id, **item)
        for agent_id, item in payload.get("agents", {}).items()
    }


PROFILES = _load_profiles()


def profile_for(agent_id: str) -> AgentProfile:
    aliases = {
        "market-hotspot-processing": "opportunity-insight",
        "data-pipeline": "data-processing",
        "data-processing-agent": "data-processing",
    }
    normalized = aliases.get(agent_id, agent_id) if agent_id not in PROFILES else agent_id
    normalized = normalized if normalized in PROFILES else "marketing-copilot"
    return PROFILES[normalized]


class GovernedMockChatModel(ChatModelBase):
    """AgentScope-compatible deterministic model used by local tests."""

    class Parameters(BaseModel):
        temperature: float = 0.0
        max_tokens: int = 512

    type = "ceair_governed_mock_chat"

    def __init__(self, model: str, response_factory: Callable[[list[Any]], str], probe_tools: bool = False):
        super().__init__(
            credential=OpenAICredential(api_key=SecretStr("mock")),
            model=model,
            parameters=self.Parameters(),
            stream=False,
            max_retries=0,
            context_size=32768,
        )
        self.formatter = OpenAIChatFormatter()
        self.response_factory = response_factory
        self.probe_tools = probe_tools
        self._tool_probe_done = False

    async def _call_api(self, model_name: str, messages: list[Any], tools: list[dict] | None = None, tool_choice: Any = None, **kwargs: Any) -> ChatResponse:
        if self.probe_tools and tools and not self._tool_probe_done:
            tool_name = next((item.get("function", {}).get("name") for item in tools if "search_marketing_knowledge" in item.get("function", {}).get("name", "")), None)
            tool_name = tool_name or next((item.get("function", {}).get("name") for item in tools if "query_marketing_ontology" in item.get("function", {}).get("name", "")), None)
            if tool_name:
                self._tool_probe_done = True
                return ChatResponse(content=[ToolCallBlock(id="mock-tool-call", name=tool_name, input=json.dumps({"query": "东航营销"}, ensure_ascii=False))], is_last=True)
        text = self.response_factory(messages)
        return ChatResponse(
            content=[TextBlock(text=text)],
            is_last=True,
            usage=ChatUsage(input_tokens=1, output_tokens=max(1, len(text) // 2), time=0.0),
        )


def _mock_response(messages: list[Any]) -> str:
    prompt = "\n".join(str(msg.get_text_content() or "") for msg in messages if hasattr(msg, "get_text_content"))
    if "ontology_gate" in prompt or "JSON" in prompt or "json" in prompt:
        return json.dumps(
            {
                "ontology_gate": {"eligible": False, "decision": "knowledge_only", "reason": "本地测试模型不对业务事实作推断", "confidence": 0.9},
                "entities": [],
                "relations": [],
            },
            ensure_ascii=False,
        )
    return "已通过 AgentScope 2.0.8 本地治理模型完成处理；真实业务结论需要配置租户模型并核验工具来源。"


class AgentScopeRuntime:
    """Build and execute one AgentScope agent with a governed profile."""

    def __init__(
        self,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        record_usage: Callable[[LLMResult], None] | None = None,
        source_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._emit_callback = emit
        self._record_usage = record_usage
        self._source_sink = source_sink

    def emit(self, event_type: str, **payload: Any) -> None:
        if self._emit_callback:
            self._emit_callback(event_type, payload)

    def run_sync(
        self,
        *,
        profile_id: str,
        tenant_id: int,
        run_id: str,
        config: LLMConfig,
        system_prompt: str,
        user_prompt: str,
        token_sink: Callable[[str], None] | None = None,
        python_tools: list[Any] | None = None,
        use_mcp: bool = True,
    ) -> str:
        return asyncio.run(self.run(
            profile_id=profile_id,
            tenant_id=tenant_id,
            run_id=run_id,
            config=config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            token_sink=token_sink,
            python_tools=python_tools,
            use_mcp=use_mcp,
        ))

    async def run(
        self,
        *,
        profile_id: str,
        tenant_id: int,
        run_id: str,
        config: LLMConfig,
        system_prompt: str,
        user_prompt: str,
        token_sink: Callable[[str], None] | None = None,
        python_tools: list[Any] | None = None,
        use_mcp: bool = True,
    ) -> str:
        if AGENTSCOPE_VERSION == "unavailable":
            raise RuntimeError(f"AgentScope 2.0.8 is unavailable: {_AGENTSCOPE_IMPORT_ERROR}")
        profile = profile_for(profile_id)
        workspace_path = WORKSPACES_ROOT / f"tenant-{tenant_id}" / profile.workspace
        workspace_path.mkdir(parents=True, exist_ok=True)
        skill_path = SKILLS_ROOT / profile.skill
        mcp_client = None
        tool_result_buffers: dict[str, list[str]] = {}
        if use_mcp:
            mcp_client = MCPClient(
                name=profile.mcp,
                is_stateful=True,
                mcp_config=StdioMCPConfig(
                    command=sys.executable,
                    args=[str(MCP_SERVER_PATH), "--profile", profile_id],
                    cwd=str(ROOT),
                    env={
                        **os.environ,
                        "CEAIR_MARKETING_DB": str(ROOT / "ceair-marketing.db"),
                        "CEAIR_TENANT_ID": str(tenant_id),
                    },
                ),
                enable_tools=profile.mcp_tools,
            )
            await mcp_client.connect()
            self.emit("agentscope/mcp-connected", name=profile.mcp, profile=profile_id)
        try:
            async with LocalWorkspace(workdir=str(workspace_path), skill_paths=[str(skill_path)] if skill_path.is_dir() else []) as workspace:
                toolkit = Toolkit(
                    tools=python_tools or [],
                    skills_or_loaders=await workspace.list_skills(agent_id=profile_id),
                    mcps=[mcp_client] if mcp_client is not None else [],
                )
                workspace_instructions = await workspace.get_instructions()
                agent = Agent(
                    name=profile.name,
                    system_prompt=(system_prompt + "\n\n" + profile.system_prompt + "\n\n" + workspace_instructions),
                    model=self._model(config, profile_id),
                    toolkit=toolkit,
                    offloader=workspace,
                    context_config=ContextConfig(trigger_ratio=0.75, reserve_ratio=0.2, tool_result_limit=4000),
                    react_config=ReActConfig(max_iters=8, structured_output_grace_iters=2, stop_on_reject=True),
                )
                self.emit("agentscope/agent-created", agent_id=profile_id, workspace=str(workspace_path), skill=profile.skill, mcp=profile.mcp if mcp_client else None)
                answer_parts: list[str] = []
                async for event in agent.reply_stream(UserMsg(name="营销平台", content=user_prompt), yield_final_msg=False):
                    self._handle_event(event, answer_parts, token_sink, tool_result_buffers)
                answer = "".join(answer_parts).strip()
                if not answer:
                    self.emit("agentscope/empty-reply", profile=profile_id)
                return answer
        finally:
            if mcp_client is not None:
                await mcp_client.close()
                self.emit("agentscope/mcp-closed", name=profile.mcp, profile=profile_id)

    def _model(self, config: LLMConfig, profile_id: str) -> ChatModelBase:
        if config.provider_type == "mock":
            return GovernedMockChatModel(config.model_name or "ceair-governed-mock-v1", _mock_response, probe_tools=profile_id == "marketing-copilot")
        credential = OpenAICredential(api_key=SecretStr(config.api_key), base_url=config.base_url.rstrip("/"))
        params = OpenAIChatModel.Parameters(
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        return OpenAIChatModel(
            credential=credential,
            model=config.model_name,
            parameters=params,
            stream=True,
            max_retries=3,
            client_kwargs={"timeout": config.timeout_seconds},
        )

    def _handle_event(
        self,
        event: Any,
        answer_parts: list[str],
        token_sink: Callable[[str], None] | None,
        tool_result_buffers: dict[str, list[str]],
    ) -> None:
        if isinstance(event, ModelCallStartEvent):
            self.emit("harness/model-started", model=event.model_name, framework="agentscope", version=AGENTSCOPE_VERSION)
        elif isinstance(event, ModelCallEndEvent):
            total = event.input_tokens + event.output_tokens
            self.emit("harness/model-finished", model=event.metadata.get("model_name", "") if event.metadata else "", prompt_tokens=event.input_tokens, completion_tokens=event.output_tokens, total_tokens=total, framework="agentscope")
            if self._record_usage:
                self._record_usage(LLMResult(content="", prompt_tokens=event.input_tokens, completion_tokens=event.output_tokens, total_tokens=total, model_name=str(event.metadata.get("model_name", "")) if event.metadata else ""))
        elif isinstance(event, TextBlockDeltaEvent):
            answer_parts.append(event.delta)
            self.emit("agent/text-delta", text=event.delta, block_id=event.block_id)
            if token_sink:
                token_sink(event.delta)
        elif isinstance(event, ThinkingBlockDeltaEvent):
            self.emit("agent/thinking-delta", text=event.delta, block_id=event.block_id)
        elif isinstance(event, ToolCallStartEvent):
            self.emit("harness/tool-started", tool=event.tool_call_name, tool_call_id=event.tool_call_id, framework="agentscope")
        elif isinstance(event, ToolResultStartEvent):
            tool_result_buffers[event.tool_call_id] = []
            self.emit("harness/tool-result-started", tool_call_id=event.tool_call_id, framework="agentscope")
        elif isinstance(event, ToolResultTextDeltaEvent):
            tool_result_buffers.setdefault(event.tool_call_id, []).append(event.delta)
        elif isinstance(event, ToolResultEndEvent):
            raw = "".join(tool_result_buffers.pop(event.tool_call_id, []))
            self.emit("harness/tool-finished", tool_call_id=event.tool_call_id, framework="agentscope")
            if self._source_sink and raw:
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    payload = {}
                for source in payload.get("sources", []) if isinstance(payload, dict) else []:
                    if isinstance(source, dict):
                        self._source_sink(source)
        elif isinstance(event, ReplyEndEvent):
            self.emit("agentscope/reply-finished", reason=str(event.finished_reason))
        elif isinstance(event, Msg):
            text = event.get_text_content()
            if text and not answer_parts:
                answer_parts.append(text)
                if token_sink:
                    token_sink(text)


def make_tool(func: Callable[..., Any], *, name: str | None = None, description: str | None = None, read_only: bool = True) -> FunctionTool:
    return FunctionTool(func, name=name, description=description, is_read_only=read_only)


def text_tool_result(value: Any) -> ToolChunk:
    return ToolChunk(content=[TextBlock(text=json.dumps(value, ensure_ascii=False, default=str))])
