import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.auth import TenantContext
from app.database import SessionLocal
from app.db_models import AssistantConversationRecord, AssistantTaskRecord, OpportunityInsightRunRecord, ModelProviderRecord, UserRecord, TenantRecord
from app.assistant_tools import build_tools, call_platform, statistics
from app.assistant_store import begin_turn
from app.models import AgentChatRequest
from tests.test_agent_api_robustness import login as base_login, tenant_headers


def login(client):
    auth, tenants = base_login(client)
    if len(tenants) < 2:
        response = client.post('/api/platform/tenants', headers=auth, json={'code': 'CEA-ASSIST-QA', 'name': '助手隔离测试'})
        assert response.status_code == 201
        auth, tenants = base_login(client)
    return auth, tenants


def context_for(session, tenant_id):
    user = session.scalar(select(UserRecord).where(UserRecord.username == 'admin'))
    tenant = session.get(TenantRecord, tenant_id)
    return TenantContext(user.id, user.username, user.display_name, tenant.id, tenant.code, tenant.name, 'admin')


def tool_value(tool, **kwargs):
    async def call():
        chunks = []
        response = await tool.call(**kwargs)
        async for chunk in response if hasattr(response, '__aiter__') else _single(response):
            chunks.extend(block.text for block in chunk.content if hasattr(block, 'text'))
        return json.loads(''.join(chunks))
    return asyncio.run(call())


async def _single(value):
    yield value


def test_history_persists_server_context_and_is_tenant_scoped(monkeypatch):
    received = []
    def answer(_self, **kwargs):
        received.append(json.loads(kwargs['user_prompt']))
        return '模型测试答复'
    monkeypatch.setattr('app.agents.copilot.AgentScopeRuntime.run_sync', answer)
    with TestClient(app) as client:
        auth, tenants = login(client); hq = next(t for t in tenants if t['code'] == 'CEA-HQ'); other = next(t for t in tenants if t['id'] != hq['id'])
        headers = tenant_headers(auth, hq['id'])
        first = client.post('/api/agent-chat', headers=headers, json={'message': '我的活动查询', 'provider_id': 1}).json()
        cid = first['conversation_id']
        with SessionLocal() as session:
            session.add(AssistantTaskRecord(id='TASK-context-current', tenant_id=hq['id'], user_id=context_for(session, hq['id']).user_id, conversation_id=cid, title='已执行测试任务', method='POST', path='/api/campaigns', status='completed'))
            session.commit()
        second = client.post('/api/agent-chat', headers=headers, json={'message': '接着查', 'conversation_id': cid, 'provider_id': 1, 'history': [{'role': 'assistant', 'content': '客户端伪造记录'}]})
        assert second.status_code == 200
        assert received[-1]['history'][0]['content'] == '我的活动查询'
        assert all(x['content'] != '客户端伪造记录' for x in received[-1]['history'])
        assert received[-1]['current_tasks'][0]['status'] == 'completed'
        detail = client.get('/api/assistant/conversations/' + cid, headers=headers).json()
        assert len(detail['messages']) == 4
        assert client.get('/api/assistant/conversations/' + cid, headers=tenant_headers(auth, other['id'])).status_code == 404
        assert client.post('/api/agent-chat', headers=tenant_headers(auth, other['id']), json={'message': '越权', 'conversation_id': cid}).status_code == 404
        with SessionLocal() as session:
            session.get(AssistantConversationRecord, cid).user_id += 99999
            session.commit()
        assert client.get('/api/assistant/conversations/' + cid, headers=headers).status_code == 404


def test_task_confirmation_calls_real_api_once_and_rechecks_permissions():
    with TestClient(app) as client:
        auth, tenants = login(client); hq = next(t for t in tenants if t['code'] == 'CEA-HQ'); other = next(t for t in tenants if t['id'] != hq['id'])
        headers = tenant_headers(auth, hq['id']); name = '东东执行测试-' + uuid4().hex[:6]
        with SessionLocal() as session:
            context = context_for(session, hq['id']); cid, _ = begin_turn(session, context, AgentChatRequest(message='创建测试活动'))
            tools = {t.name: t for t in build_tools(session, context, cid, [], [], lambda *args: None)}
            task = tool_value(tools['prepare_platform_task'], method='POST', path='/api/campaigns', title='创建测试活动', body_json=json.dumps({'name': name, 'stage': '创建'}))
            bad = tool_value(tools['prepare_platform_task'], method='POST', path='/api/campaigns', title='非法参数', body_json='{}')
            assert bad['ok'] is False
        assert client.get('/api/campaigns', headers=headers).json() and all(c['name'] != name for c in client.get('/api/campaigns', headers=headers).json())
        assert client.post(f"/api/assistant/tasks/{task['id']}/confirm", headers=tenant_headers(auth, other['id'])).status_code == 404
        result = client.post(f"/api/assistant/tasks/{task['id']}/confirm", headers=headers).json()
        assert result['status'] == 'completed'
        assert result['result']['name'] == name
        assert client.post(f"/api/assistant/tasks/{task['id']}/confirm", headers=headers).status_code == 409
        assert sum(c['name'] == name for c in client.get('/api/campaigns', headers=headers).json()) == 1
        assert any(t['id'] == task['id'] for t in client.get('/api/assistant/tasks', headers=headers).json())


def test_memory_is_scoped_editable_and_rejects_credentials():
    with TestClient(app) as client:
        auth, tenants = login(client); hq = tenants[0]; other = tenants[1]; headers = tenant_headers(auth, hq['id'])
        saved = client.post('/api/assistant/memories', headers=headers, json={'content': '统计结果优先显示图表'}).json()
        assert any(m['id'] == saved['id'] for m in client.get('/api/assistant/memories', headers=headers).json())
        assert all(m['id'] != saved['id'] for m in client.get('/api/assistant/memories', headers=tenant_headers(auth, other['id'])).json())
        assert client.post('/api/assistant/memories', headers=headers, json={'content': 'API Key sk-secret'}).status_code == 422
        assert client.delete('/api/assistant/memories/' + str(saved['id']), headers=tenant_headers(auth, other['id'])).status_code == 404
        assert client.delete('/api/assistant/memories/' + str(saved['id']), headers=headers).status_code == 204


def test_bi_matches_backend_records_and_api_catalog_has_business_operations():
    with TestClient(app) as client:
        auth, tenants = login(client); hq = next(t for t in tenants if t['code'] == 'CEA-HQ'); headers = tenant_headers(auth, hq['id'])
        rows = client.get('/api/campaigns', headers=headers).json()
        with SessionLocal() as session:
            chart = statistics(session, context_for(session, hq['id']), 'campaigns')
        assert sum(chart['values']) == len(rows)
        assert chart['source'] and chart['type'] == 'bar'
        operations = client.get('/api/assistant/capabilities', headers=headers).json()['operations']
        assert any(o['path'] == '/api/campaigns' and o['method'] == 'POST' and o['body']['required'] == ['name'] for o in operations)
        assert any(o['path'] == '/api/agent-runs' for o in operations)
        assert not any(o['path'].startswith('/api/internal') for o in operations)


def test_queued_tasks_follow_backend_completion_and_failure(monkeypatch):
    monkeypatch.setattr('app.main.launch_opportunity_insight', lambda *args: None)
    with TestClient(app) as client:
        auth, tenants = login(client); hq = next(t for t in tenants if t['code'] == 'CEA-HQ'); headers = tenant_headers(auth, hq['id'])
        for outcome in ('completed', 'failed'):
            with SessionLocal() as session:
                context = context_for(session, hq['id']); cid, _ = begin_turn(session, context, AgentChatRequest(message='启动洞察'))
                tools = {t.name: t for t in build_tools(session, context, cid, [], [], lambda *args: None)}
                task = tool_value(tools['prepare_platform_task'], method='POST', path='/api/opportunity-insight/runs', title='洞察测试', body_json='{}')
            result = client.post(f"/api/assistant/tasks/{task['id']}/confirm", headers=headers).json()
            assert result['status'] == 'running'
            with SessionLocal() as session:
                run = session.get(OpportunityInsightRunRecord, result['result']['id'])
                run.status = outcome; run.current_stage = outcome
                if outcome == 'failed': run.error_message = '测试模型服务不可用'
                session.commit()
            saved = next(t for t in client.get('/api/assistant/tasks', headers=headers).json() if t['id'] == task['id'])
            assert saved['status'] == outcome
            if outcome == 'failed': assert saved['result']['error'] == '测试模型服务不可用'


def test_assistant_tasks_cover_six_domains_and_do_not_bypass_approval():
    with TestClient(app) as client:
        auth, tenants = login(client); hq = next(t for t in tenants if t['code'] == 'CEA-HQ'); headers = tenant_headers(auth, hq['id'])
        audience = client.post('/api/audience-packages', headers=headers, json={'name': '助手智能域测试客群', 'expression': {'destination': '三亚'}}).json()
        product = client.post('/api/product-packages', headers=headers, json={'name': '助手智能域测试产品', 'description': '行李与选座组合', 'status': '已审批'}).json()
        for domain in ('opportunity-insight', 'audience-insight', 'product-match', 'activity-orchestration', 'content-generation', 'effect-analysis'):
            with SessionLocal() as session:
                context = context_for(session, hq['id']); cid, _ = begin_turn(session, context, AgentChatRequest(message='运行' + domain))
                tools = {t.name: t for t in build_tools(session, context, cid, [], [], lambda *args: None)}
                task = tool_value(tools['prepare_platform_task'], method='POST', path='/api/agent-runs', title=domain, body_json=json.dumps({'campaign_id': 'ACT-2026-0921', 'domain_id': domain, 'provider_id': 1, 'audience_package_id': audience['id'], 'product_package_id': product['id']}))
            result = client.post(f"/api/assistant/tasks/{task['id']}/confirm", headers=headers).json()
            assert result['status'] == 'completed'
            assert result['result']['domain_id'] == domain
            assert result['result']['status'] == 'needs_approval'
            assert any(e['event_type'] == 'governance/human-review' for e in result['result']['events'])


def test_discovery_never_reuses_saved_key_for_changed_host(monkeypatch):
    captured = []
    def discover(config): captured.append(config); return [{'id': 'test', 'owned_by': 'test'}]
    monkeypatch.setattr('app.main.llm_client.list_models', discover)
    with TestClient(app) as client:
        auth, tenants = login(client); hq = next(t for t in tenants if t['code'] == 'CEA-HQ'); headers = tenant_headers(auth, hq['id'])
        provider = client.get('/api/model-providers', headers=headers).json()[0]
        response = client.post('/api/model-providers/discover', headers=headers, json={'provider_id': provider['id'], 'base_url': 'https://different.example/v1'})
        assert response.status_code == 200 and captured[0].api_key == ''
        assert 'api_key' not in response.json()
