from __future__ import annotations

import html
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import select

from .agents.agentscope_runtime import AgentScopeRuntime
from .database import SessionLocal
from .db_models import ModelProviderRecord, OpportunityInsightRunRecord, OpportunityInsightSourceRecord, OpportunityRecord
from .llm import LLMConfig
from .security import SecretCipher


def _now():
    return datetime.now(timezone.utc)


def _json(value, default):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return default


def _append_step(run_id: str, tenant_id: int, step: dict) -> None:
    with SessionLocal() as session:
        run = session.scalar(select(OpportunityInsightRunRecord).where(OpportunityInsightRunRecord.id == run_id, OpportunityInsightRunRecord.tenant_id == tenant_id))
        if run is None:
            return
        steps = _json(run.steps_json, [])
        steps.append({"timestamp": _now().isoformat(), **step})
        run.steps_json = json.dumps(steps[-120:], ensure_ascii=False)
        run.current_stage = step.get("stage", run.current_stage)
        session.commit()


def _set_run(run_id: str, tenant_id: int, **values) -> None:
    with SessionLocal() as session:
        run = session.scalar(select(OpportunityInsightRunRecord).where(OpportunityInsightRunRecord.id == run_id, OpportunityInsightRunRecord.tenant_id == tenant_id))
        if run is None:
            return
        for key, value in values.items():
            if key in {"source_ids", "steps", "result"}:
                value = json.dumps(value, ensure_ascii=False)
                key = {"source_ids": "source_ids_json", "steps": "steps_json", "result": "result_json"}[key]
            setattr(run, key, value)
        session.commit()


def _fetch_source(source: OpportunityInsightSourceRecord) -> dict:
    evidence = {"source_id": source.id, "name": source.name, "url": source.source_url, "focus": source.focus, "title": source.name, "text": ""}
    if not source.source_url:
        evidence["text"] = source.focus or source.name
        return evidence | {"status": "metadata-only"}
    try:
        request = Request(source.source_url, headers={"User-Agent": "CeairMarketingOpportunityAgent/1.0"})
        with urlopen(request, timeout=8) as response:
            raw = response.read(1_000_000)
            charset = response.headers.get_content_charset() or "utf-8"
        page = raw.decode(charset, errors="ignore")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else source.name
        text = html.unescape(re.sub(r"<[^>]+>", " ", page))
        text = re.sub(r"\s+", " ", text).strip()
        evidence.update({"title": title[:240], "text": text[:6000], "status": "fetched"})
    except Exception as exc:
        evidence.update({"text": source.focus or source.name, "status": "fallback", "error": type(exc).__name__})
    return evidence


def _heuristic(role: str, prompt: str, evidence: list[dict]) -> dict:
    text = " ".join([prompt] + [f"{item.get('title', '')} {item.get('text', '')}" for item in evidence]).lower()
    keywords = [word for word in ("国庆", "暑期", "春运", "旅游", "亲子", "中转", "客座率", "航班", "价格", "会员", "行李", "卡券") if word.lower() in text]
    topic = "、".join(keywords[:4]) or "航线经营与市场需求"
    role_names = {"market": "市场信号", "route": "航线经营", "product": "产品商业化"}
    score = min(96, 68 + len(keywords) * 4 + (8 if role == "route" and "航班" in text else 0))
    return {"role": role, "agent_name": f"{role_names[role]}洞察智能体", "topic": topic, "score": score, "summary": f"基于{topic}识别到可经营信号，建议结合东航航线、客群和可售产品进行人工确认。", "evidence_count": len(evidence)}


def _provider_config(session, tenant_id: int) -> tuple[ModelProviderRecord | None, LLMConfig | None]:
    provider = session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.enabled.is_(True)).order_by(ModelProviderRecord.is_default.desc(), ModelProviderRecord.id))
    if provider is None:
        return None, None
    api_key = ""
    if provider.encrypted_api_key:
        try:
            api_key = SecretCipher().decrypt(provider.encrypted_api_key)
        except RuntimeError:
            api_key = ""
    return provider, LLMConfig(provider.provider_type, provider.base_url, provider.model_name, api_key, provider.timeout_seconds, provider.temperature, provider.max_tokens)


def _agent_result(role: str, profile_id: str, run_id: str, tenant_id: int, prompt: str, evidence: list[dict], config: LLMConfig | None) -> dict:
    result = _heuristic(role, prompt, evidence)
    if config is None:
        return result | {"execution": "deterministic-fallback"}
    events = []
    runtime = AgentScopeRuntime(emit=lambda event, payload: events.append({"event": event, "payload": payload}), record_usage=None)
    request = json.dumps({"role": role, "prompt": prompt, "evidence": evidence[:12], "required_fields": ["topic", "score", "summary"]}, ensure_ascii=False)
    try:
        output = runtime.run_sync(profile_id=profile_id, tenant_id=tenant_id, run_id=f"{run_id}-{role}", config=config, system_prompt="你是东航商机洞察智能体，只基于证据输出JSON，不编造航班、价格、库存或旅客个人信息。", user_prompt=request, use_mcp=True)
        parsed = json.loads(output) if output.strip().startswith("{") else {}
        if isinstance(parsed, dict):
            result.update({key: parsed[key] for key in ("topic", "score", "summary") if key in parsed})
    except Exception as exc:
        result["model_error"] = type(exc).__name__
    result["execution"] = "agentscope"
    result["events"] = events[-20:]
    return result


def run_opportunity_insight(run_id: str, tenant_id: int) -> None:
    with SessionLocal() as session:
        run = session.scalar(select(OpportunityInsightRunRecord).where(OpportunityInsightRunRecord.id == run_id, OpportunityInsightRunRecord.tenant_id == tenant_id))
        if run is None:
            return
        source_ids = _json(run.source_ids_json, [])
        sources = session.scalars(select(OpportunityInsightSourceRecord).where(OpportunityInsightSourceRecord.tenant_id == tenant_id, OpportunityInsightSourceRecord.id.in_(source_ids), OpportunityInsightSourceRecord.enabled.is_(True))).all() if source_ids else session.scalars(select(OpportunityInsightSourceRecord).where(OpportunityInsightSourceRecord.tenant_id == tenant_id, OpportunityInsightSourceRecord.enabled.is_(True))).all()
        prompt = run.prompt
        operator = run.operator
        provider, config = _provider_config(session, tenant_id)
        run.status = "running"
        run.current_stage = "plan"
        run.started_at = _now()
        session.commit()
    try:
        _append_step(run_id, tenant_id, {"stage": "plan", "status": "completed", "detail": f"已规划{len(sources)}个业务来源，准备并行洞察"})
        evidence = []
        for source in sources:
            _append_step(run_id, tenant_id, {"stage": "fetch", "status": "running", "source": source.name, "detail": "读取来源并保留证据"})
            item = _fetch_source(source)
            evidence.append(item)
            _append_step(run_id, tenant_id, {"stage": "fetch", "status": "completed", "source": source.name, "detail": item.get("status"), "url": source.source_url})
        roles = [("market", "opportunity-market"), ("route", "opportunity-route"), ("product", "opportunity-product")]
        results = []
        _append_step(run_id, tenant_id, {"stage": "multi-agent", "status": "running", "detail": "市场、航线、产品三类智能体并行分析"})
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_agent_result, role, profile, run_id, tenant_id, prompt, evidence, config): role for role, profile in roles}
            for future in as_completed(futures):
                role = futures[future]
                result = future.result()
                results.append(result)
                _append_step(run_id, tenant_id, {"stage": "multi-agent", "status": "completed", "agent": result["agent_name"], "detail": result["summary"], "score": result["score"]})
        score = round(sum(int(item.get("score", 0)) for item in results) / max(1, len(results)))
        topic = "、".join(dict.fromkeys(item.get("topic", "") for item in results if item.get("topic")))
        name = f"{topic[:48] or '航空市场'}商机洞察"
        opportunity_id = f"OPP-{_now():%Y%m%d}-{uuid4().hex[:6].upper()}"
        with SessionLocal() as session:
            record = OpportunityRecord(tenant_id=tenant_id, id=opportunity_id, name=name, market_scope="国内", route="待智能体确认", signal_summary=f"{prompt or '基于配置来源的多智能体洞察'}；{topic}。"[:2000], status="待评估", score=score, estimated_audience=max(0, 8000 + score * 180), estimated_revenue_yuan=max(0, score * 26000), owner=operator)
            session.add(record)
            run = session.scalar(select(OpportunityInsightRunRecord).where(OpportunityInsightRunRecord.id == run_id, OpportunityInsightRunRecord.tenant_id == tenant_id))
            run.status = "completed"
            run.current_stage = "synthesis"
            run.result_json = json.dumps({"opportunity_ids": [opportunity_id], "agents": results, "evidence": evidence}, ensure_ascii=False)
            run.completed_at = _now()
            session.commit()
        _append_step(run_id, tenant_id, {"stage": "synthesis", "status": "completed", "detail": f"已形成商机候选：{name}", "opportunity_id": opportunity_id})
    except Exception as exc:
        _set_run(run_id, tenant_id, status="failed", current_stage="failed", error_message=str(exc), completed_at=_now())
        _append_step(run_id, tenant_id, {"stage": "failed", "status": "failed", "detail": str(exc)})


def launch_opportunity_insight(run_id: str, tenant_id: int) -> None:
    threading.Thread(target=run_opportunity_insight, args=(run_id, tenant_id), name="ceair-opportunity-insight", daemon=True).start()
