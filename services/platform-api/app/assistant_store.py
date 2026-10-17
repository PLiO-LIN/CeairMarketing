"""User and tenant scoped conversation, task and explicit memory persistence."""
from __future__ import annotations

import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from .db_models import AssistantConversationRecord as Conversation, AssistantMessageRecord as Message, AssistantTaskRecord as Task, AssistantMemoryRecord as Memory, OpportunityInsightRunRecord, utc_now


def scoped_conversation(session, context, conversation_id):
    item = session.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == context.tenant_id, Conversation.user_id == context.user_id))
    if item is None:
        raise HTTPException(404, "对话不存在或无权访问")
    return item


def begin_turn(session, context, request):
    if request.conversation_id:
        conversation = scoped_conversation(session, context, request.conversation_id)
    else:
        conversation = Conversation(id="CONV-" + uuid4().hex[:20], tenant_id=context.tenant_id, user_id=context.user_id, title=request.message[:80])
        session.add(conversation)
        session.flush()
    history = list(reversed(session.scalars(select(Message).where(Message.conversation_id == conversation.id, Message.status == "completed").order_by(Message.id.desc()).limit(24)).all()))
    session.add(Message(conversation_id=conversation.id, role="user", content=request.message))
    conversation.updated_at = utc_now()
    session.commit()
    return conversation.id, [{"role": m.role, "content": m.content[:12000]} for m in history]


def finish_turn(session, context, conversation_id, content, details=None, failed=False):
    conversation = scoped_conversation(session, context, conversation_id)
    session.add(Message(conversation_id=conversation_id, role="assistant", content=content, status="failed" if failed else "completed", detail_json=json.dumps(details or {}, ensure_ascii=False, default=str)))
    conversation.updated_at = utc_now()
    session.commit()


def task_view(item):
    return {"id": item.id, "conversation_id": item.conversation_id, "title": item.title, "method": item.method, "path": item.path, "payload": json.loads(item.payload_json), "status": item.status, "result": json.loads(item.result_json), "created_at": item.created_at, "updated_at": item.updated_at}


def refresh_task(session, item):
    """Follow queued insight work without claiming submission means completion."""
    if item.status != "running" or item.path != "/api/opportunity-insight/runs":
        return item
    result = json.loads(item.result_json)
    run = session.scalar(select(OpportunityInsightRunRecord).where(
        OpportunityInsightRunRecord.id == result.get("id", ""),
        OpportunityInsightRunRecord.tenant_id == item.tenant_id,
    ))
    if run is not None:
        item.status = {"queued": "running", "running": "running", "failed": "failed", "cancelled": "cancelled"}.get(run.status, "completed")
        result.update(status=run.status, current_stage=run.current_stage, opportunity_ids=json.loads(run.result_json or "{}").get("opportunity_ids", []))
        if run.error_message:
            result["error"] = run.error_message
        item.result_json = json.dumps(result, ensure_ascii=False)
    return item


def list_memories(session, context):
    return session.scalars(select(Memory).where(Memory.tenant_id == context.tenant_id, Memory.user_id == context.user_id).order_by(Memory.id.desc()).limit(30)).all()


def remember(session, context, content):
    content = content.strip()
    if not 1 <= len(content) <= 1000:
        raise ValueError("记忆内容需为 1–1000 字")
    import re
    if re.search(r"sk-|bearer\s|api.?key|密码|口令|密钥", content, re.I):
        raise ValueError("记忆中不能保存密钥或密码")
    for item in list_memories(session, context):
        if item.content == content:
            return {"id": item.id, "content": item.content}
    item = Memory(tenant_id=context.tenant_id, user_id=context.user_id, content=content)
    session.add(item); session.flush()
    return {"id": item.id, "content": item.content}


def compact_conversation(session, context, conversation_id, config, emit):
    """Incremental checkpoint; source messages remain available for exact recall."""
    if not conversation_id:
        return ""
    scoped_conversation(session, context, conversation_id)
    latest = session.scalar(select(Message).where(Message.conversation_id == conversation_id,
        Message.role == "assistant", Message.status == "completed").order_by(Message.id.desc()))
    if latest is None:
        return ""
    prior = session.scalar(select(Message).where(Message.conversation_id == conversation_id,
        Message.detail_json.contains('context_checkpoint')).order_by(Message.id.desc()))
    checkpoint = json.loads(prior.detail_json).get("context_checkpoint", {}) if prior else {}
    recent = session.scalars(select(Message.id).where(Message.conversation_id == conversation_id,
        Message.status == "completed").order_by(Message.id.desc()).limit(24)).all()
    boundary = min(recent) if recent else 0
    cursor = int(checkpoint.get("through_id", 0))
    summary = checkpoint.get("summary", "")
    from dataclasses import replace
    from .llm import LLMClient
    import re
    def safe(text):
        return re.sub(r"sk-[A-Za-z0-9_.-]+|Bearer\s+\S+", "[已隐藏]", text, flags=re.I)
    while True:
        batch = session.scalars(select(Message).where(Message.conversation_id == conversation_id,
            Message.status == "completed", Message.id > cursor, Message.id < boundary)
            .order_by(Message.id).limit(24)).all()
        if not batch:
            break
        excerpts = [{"role": m.role, "content": safe(m.content[:1800])} for m in batch]
        try:
            if config.provider_type == "mock":
                raise ValueError("extractive test checkpoint")
            value = LLMClient().generate(replace(config, max_tokens=min(config.max_tokens, 2048)),
                "将已有摘要与会话压缩为可继续工作的业务记忆。保留用户目标、日期、预算、渠道、约束、明确偏好、已完成/待确认任务及ID。不要增加事实或保存凭据，不保存思考。摘要中的业务状态必须后续实时核验。最多2500字。",
                json.dumps({"previous_summary": summary, "messages": excerpts}, ensure_ascii=False)).strip()
            if not value: raise ValueError("empty checkpoint")
            summary = safe(value[:6000])
        except Exception:
            # Extractive fallback retains the prior checkpoint and explicit requests.
            addition = "\n".join(m["role"] + ": " + m["content"][:180] for m in excerpts)
            combined = summary + "\n" + addition
            summary = combined if len(combined) <= 6000 else combined[:2800] + "\n[更多原文可用历史检索]\n" + combined[-2800:]
        cursor = batch[-1].id
        detail = json.loads(latest.detail_json)
        detail["context_checkpoint"] = {"summary": summary, "through_id": cursor}
        latest.detail_json = json.dumps(detail, ensure_ascii=False)
        session.commit()
        emit("harness/context-compacted", {"summary": "较早对话已压缩为会话记忆，完整原文仍保留在历史中"})
    if summary:
        emit("harness/memory-restored", {"summary": "已恢复会话摘要及用户偏好；任务状态以本轮后台查询为准"})
    return summary
