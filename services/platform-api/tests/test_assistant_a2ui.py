import json

import pytest
from fastapi.testclient import TestClient
from jsonschema import ValidationError

from app.a2ui import ReplySurfaces, VALIDATOR, ACTION_VALIDATOR
from app.agent_process import public_value
from app.main import app
from tests.test_agent_api_robustness import login, tenant_headers


def test_wire_messages_validate_upstream_schema_and_catalog():
    surfaces = ReplySurfaces('run')
    for item, kind in [({'title': '活动统计', 'metric': 'campaigns', 'labels': ['草稿'], 'values': [3]}, 'bar'), ({'title': '活动记录', 'columns': ['名称'], 'rows': [['草稿活动']], 'path': '/api/campaigns'}, 'table'), ({'id': 'TASK-1', 'title': '创建草稿', 'status': 'pending_confirmation'}, 'task'), ({'title': '模型配置', 'page': 'models'}, 'navigation')]:
        surfaces.add(item, kind)
    assert len(surfaces.messages) == 12
    for message in surfaces.messages:
        VALIDATOR.validate(message)
    unknown = {'version': 'v0.9.1', 'updateComponents': {'surfaceId': 'run-1', 'components': [{'id': 'root', 'component': 'ExecutableHtml', 'html': '<script>alert(1)</script>'}]}}
    with pytest.raises(ValidationError):
        VALIDATOR.validate(unknown)
    with pytest.raises(ValidationError):
        VALIDATOR.validate({'version': 'v0.9.1', 'beginRendering': {}})


def test_sse_streams_a2ui_before_completion_and_restores_process(monkeypatch):
    def run(_self, **kwargs):
        tools = kwargs['python_tools']
        from tests.test_assistant_workspace import tool_value
        tool_value(next(t for t in tools if t.name == 'query_statistics'), metric='campaigns')
        return '统计完成'
    monkeypatch.setattr('app.agents.copilot.AgentScopeRuntime.run_sync', run)
    with TestClient(app) as client:
        auth, tenants = login(client)
        headers = tenant_headers(auth, tenants[0]['id'])
        response = client.post('/api/agent-chat/stream', headers=headers, json={'message': '活动阶段统计', 'provider_id': 1})
        assert response.status_code == 200
        assert 'event: error' not in response.text
        assert response.text.index('event: a2ui') < response.text.index('event: complete')
        complete = next(json.loads(frame.split('data: ', 1)[1]) for frame in response.text.split('\n\n') if frame.startswith('event: complete'))
        saved = client.get('/api/assistant/conversations/' + complete['conversation_id'], headers=headers).json()['messages'][-1]['detail']
        assert saved['a2ui'] == complete['a2ui']
        assert saved['trace'] == complete['trace'] and saved['trace']
        assert saved['a2ui'][2]['updateComponents']['components'][1]['component'] == 'Chart'


def test_public_tool_events_link_inputs_outputs_and_hide_private_data():
    from agentscope.event import ToolCallStartEvent, ToolCallDeltaEvent, ToolCallEndEvent, ToolResultStartEvent, ToolResultTextDeltaEvent, ToolResultEndEvent, ThinkingBlockDeltaEvent
    from app.agents.agentscope_runtime import AgentScopeRuntime
    events = []
    runtime = AgentScopeRuntime(emit=lambda name, data: events.append({'event': name, **data}))
    common = {'reply_id': 'round', 'tool_call_id': 'tool'}
    values = [ToolCallStartEvent(**common, tool_call_name='query_platform'), ToolCallDeltaEvent(**common, delta=json.dumps({'body_json': json.dumps({'password': 'never-show'})})), ToolCallEndEvent(**common), ToolResultStartEvent(**common, tool_call_name='query_platform'), ToolResultTextDeltaEvent(**common, delta=json.dumps({'ok': False, 'error': 'no permission', 'access_token': 'never-show'})), ToolResultEndEvent(**common, state='error'), ThinkingBlockDeltaEvent(reply_id='round', block_id='private', delta='private-thought')]
    buffers = {}
    for event in values:
        runtime._handle_event(event, [], None, buffers)
    assert all(e['tool_call_id'] == 'tool' for e in events)
    assert any(e['event'] == 'harness/tool-input' for e in events)
    assert events[-1]['event'] == 'harness/tool-failed'
    serialized = json.dumps(events)
    assert 'private-thought' not in serialized and 'never-show' not in serialized
    assert public_value({'reasoning_content': 'private'}) == {'reasoning_content': '[已隐藏]'}


def test_a2ui_action_uses_standard_envelope_and_only_navigates():
    action = {'version': 'v0.9.1', 'action': {'name': 'open_page', 'surfaceId': 'run-1', 'sourceComponentId': 'content', 'timestamp': '2026-10-10T12:00:00Z', 'context': {'page': 'campaigns'}}}
    ACTION_VALIDATOR.validate(action)
    with TestClient(app) as client:
        auth, tenants = login(client); headers = tenant_headers(auth, tenants[0]['id'])
        assert client.post('/api/assistant/ui-action', headers=headers, json=action).json() == {'page': 'campaigns'}
        action['action']['name'] = 'execute_arbitrary_api'
        assert client.post('/api/assistant/ui-action', headers=headers, json=action).status_code == 422
        assert client.post('/api/assistant/ui-action', json=action).status_code == 401


def test_failed_turn_preserves_emitted_process_and_ui(monkeypatch):
    from app.llm import LLMServiceError
    def fail(_self, **kwargs):
        _self.emit('harness/tool-started', tool='query_statistics', tool_call_id='stat')
        from tests.test_assistant_workspace import tool_value
        tool_value(next(t for t in kwargs['python_tools'] if t.name == 'query_statistics'), metric='campaigns')
        raise LLMServiceError('测试模型连接中断')
    monkeypatch.setattr('app.agents.copilot.AgentScopeRuntime.run_sync', fail)
    with TestClient(app) as client:
        auth, tenants = login(client); headers = tenant_headers(auth, tenants[0]['id'])
        response = client.post('/api/agent-chat/stream', headers=headers, json={'message': '部分结果失败恢复', 'provider_id': 1})
        assert 'event: error' in response.text and 'event: complete' not in response.text
        cid = next(json.loads(frame.split('data: ', 1)[1])['conversation_id'] for frame in response.text.split('\n\n') if frame.startswith('event: conversation'))
        message = client.get('/api/assistant/conversations/' + cid, headers=headers).json()['messages'][-1]
        assert message['status'] == 'failed' and message['detail']['trace'] and message['detail']['a2ui']
