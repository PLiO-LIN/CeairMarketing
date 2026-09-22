from __future__ import annotations

from app.agents.agentscope_runtime import AGENTSCOPE_VERSION, AgentScopeRuntime, PROFILES
from app.agents.harness import HarnessContext, UnifiedHarness
from app.llm import LLMConfig


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

