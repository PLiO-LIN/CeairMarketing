import json
from uuid import uuid4
from sqlalchemy import select
from app.database import SessionLocal
from app.db_models import AssistantMessageRecord, TenantRecord
from app.assistant_store import begin_turn, compact_conversation
from app.models import AgentChatRequest
from tests.test_assistant_workspace import context_for, tool_value
from tests.test_agentscope_runtime import mock_config
from app.assistant_tools import build_tools


def test_compaction_preserves_early_constraints_and_original_history():
    with SessionLocal() as session:
        tenant = session.scalar(select(TenantRecord).where(TenantRecord.code == 'CEA-HQ'))
        context = context_for(session, tenant.id)
        cid, _ = begin_turn(session, context, AgentChatRequest(message='预算不能超过80000元，渠道仅限App'))
        for i in range(32):
            session.add(AssistantMessageRecord(conversation_id=cid, role='assistant' if i % 2 == 0 else 'user', content=f'继续处理第{i}条'))
        session.commit()
        events = []
        summary = compact_conversation(session, context, cid, mock_config(), lambda *args: events.append(args))
        assert '80000元' in summary and '渠道仅限App' in summary
        assert any(name == 'harness/context-compacted' for name, _ in events)
        again = compact_conversation(session, context, cid, mock_config(), lambda *args: None)
        assert again == summary
        tools = {tool.name: tool for tool in build_tools(session, context, cid, [], [], lambda *args: None)}
        original = tool_value(tools['recall_conversation'], query='80000')
        assert original['messages'][0]['content'] == '预算不能超过80000元，渠道仅限App'
        assert session.scalar(select(AssistantMessageRecord).where(AssistantMessageRecord.conversation_id == cid, AssistantMessageRecord.content.contains('80000')))


def test_chart_choice_and_caption_are_published_from_backend_facts():
    with SessionLocal() as session:
        tenant = session.scalar(select(TenantRecord).where(TenantRecord.code == 'CEA-HQ'))
        context = context_for(session, tenant.id)
        cid, _ = begin_turn(session, context, AgentChatRequest(message='查活动'))
        widgets, surfaces = [], []
        tools = {tool.name: tool for tool in build_tools(session, context, cid, widgets, [], lambda *args: None, lambda item, kind: surfaces.append(item))}
        first = tool_value(tools['query_statistics'], metric='campaigns', view='donut', caption='活动阶段占比')
        second = tool_value(tools['query_statistics'], metric='campaigns', view='table', caption='核对明细')
        assert first['values'] == second['values']
        assert [item['view'] for item in surfaces] == ['donut', 'table']
        assert surfaces[0]['caption'] == '活动阶段占比'
