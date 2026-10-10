from __future__ import annotations

from app.agents.agentscope_runtime import AGENTSCOPE_VERSION, AgentScopeRuntime, PROFILES
from app.agents.harness import HarnessContext, UnifiedHarness
from app.llm import LLMConfig


def test_final_message_recovers_missing_deltas_without_duplicate_tokens():
    import asyncio
    from agentscope.event import ReplyEndEvent, TextBlockDeltaEvent, TextBlockEndEvent
    from agentscope.message import AssistantMsg
    runtime = AgentScopeRuntime()
    async def events(values):
        for value in values: yield value
    final = AssistantMsg(name="assistant", content="完整答复")
    end = ReplyEndEvent(session_id="s", reply_id="r")
    tokens = []
    output = asyncio.run(runtime._consume_reply(events([TextBlockEndEvent(reply_id="r", block_id="b", text="完整答复"), end, final]), tokens.append, {}))
    assert output == "完整答复" and ''.join(tokens) == output
    tokens.clear()
    output = asyncio.run(runtime._consume_reply(events([TextBlockDeltaEvent(reply_id="r", block_id="b", delta="完整答复"), end, final]), tokens.append, {}))
    assert output == "完整答复" and tokens == ["完整答复"]


def test_parked_interrupted_and_empty_replies_fail_explicitly():
    import asyncio
    import pytest
    from agentscope.event import ReplyEndEvent, RequireUserConfirmEvent
    from agentscope.message import AssistantMsg
    from app.llm import LLMServiceError
    async def events(values):
        for value in values: yield value
    for value, message in [(RequireUserConfirmEvent(reply_id="r", tool_calls=[]), "人工确认"), (ReplyEndEvent(session_id="s", reply_id="r", finished_reason="exceed_max_iters"), "轮数上限"), (ReplyEndEvent(session_id="s", reply_id="r", finished_reason="interrupted"), "中断")]:
        with pytest.raises(LLMServiceError, match=message):
            asyncio.run(AgentScopeRuntime()._consume_reply(events([value]), None, {}))
    with pytest.raises(LLMServiceError, match="正文"):
        asyncio.run(AgentScopeRuntime()._consume_reply(events([ReplyEndEvent(session_id="s", reply_id="r"), AssistantMsg(name="a", content="")]), None, {}))


def mock_config() -> LLMConfig:
    return LLMConfig(provider_type="mock", base_url="", model_name="ceair-governed-mock-v1", api_key="", timeout_seconds=20, temperature=0.0, max_tokens=256)


def test_agentscope_profiles_are_complete() -> None:
    assert AGENTSCOPE_VERSION == "2.0.8"
    assert {"data-processing", "opportunity-insight", "audience-insight", "product-match", "activity-orchestration", "content-generation", "effect-analysis", "marketing-copilot"} <= set(PROFILES)
    assert len({profile.workspace for profile in PROFILES.values()}) == len(PROFILES)
    assert all(profile.skill and profile.mcp for profile in PROFILES.values())


def test_agentscope_runtime_emits_framework_and_stream_events() -> None:
    events = []
    tokens = []
    runtime = AgentScopeRuntime(emit=lambda event, payload: events.append((event, payload)))
    output = runtime.run_sync(profile_id="data-processing", tenant_id=1, run_id="AS-TEST", config=mock_config(), system_prompt="Return JSON with ontology_gate", user_prompt="test", token_sink=tokens.append, use_mcp=True)
    assert "ontology_gate" in output
    assert tokens
    names = {name for name, _payload in events}
    assert {"agentscope/mcp-connected", "agentscope/agent-created", "harness/model-started", "harness/model-finished", "agentscope/mcp-closed"} <= names
    assert all(payload.get("framework") == "agentscope" for name, payload in events if name.startswith("harness/model"))


def test_legacy_unified_harness_delegates_to_agentscope() -> None:
    events = []
    harness = UnifiedHarness(emit=lambda event, payload: events.append((event, payload)))
    harness.load_context(HarnessContext(tenant_id=1, run_id="HARNESS-TEST", agent_id="data-processing"))
    value = harness.generate_json(mock_config(), "Return JSON with ontology_gate", "test")
    assert value["ontology_gate"]["decision"] == "knowledge_only"
    context_events = [payload for event, payload in events if event == "harness/context-loaded"]
    assert context_events[0]["framework"] == "agentscope"
