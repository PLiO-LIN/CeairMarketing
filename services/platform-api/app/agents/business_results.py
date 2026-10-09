from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select

from ..db_models import (
    AgentRunRecord, AudiencePackageRecord, AudienceSnapshotRecord, CampaignRecord,
    CampaignVersionRecord, ChannelTaskRecord, ContentAssetRecord,
    OntologyEntityRecord, OntologyRelationRecord, PersonaDimensionDefinitionRecord, ProductPackageRecord, RuntimeEventRecord,
)
from ..models import ContentAssetBase


def business_context(session, tenant_id, campaign, request):
    version = session.scalar(select(CampaignVersionRecord).where(
        CampaignVersionRecord.tenant_id == tenant_id, CampaignVersionRecord.campaign_id == campaign.id,
    ).order_by(CampaignVersionRecord.id.desc()))
    snapshot = session.scalar(select(AudienceSnapshotRecord).where(
        AudienceSnapshotRecord.tenant_id == tenant_id, AudienceSnapshotRecord.id == version.audience_snapshot_id,
    )) if version and version.audience_snapshot_id else None
    audience_id = request.audience_package_id or (snapshot.package_id if snapshot else None)
    product_id = request.product_package_id or (version.product_package_id if version else None)
    audience = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == tenant_id, AudiencePackageRecord.id == audience_id)) if audience_id else None
    product = session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.tenant_id == tenant_id, ProductPackageRecord.id == product_id)) if product_id else None
    if request.audience_package_id and audience is None:
        raise ValueError("所选客群包不存在或不属于当前租户")
    if request.product_package_id and product is None:
        raise ValueError("所选产品包不存在或不属于当前租户")
    if request.domain_id == "content-generation" and (audience is None or product is None):
        raise ValueError("生成内容需要选择客群包和产品包")
    from ..db_models import ExecutionBatchRecord
    latest_batch = session.scalar(select(ExecutionBatchRecord).where(ExecutionBatchRecord.tenant_id == tenant_id, ExecutionBatchRecord.campaign_id == campaign.id).order_by(ExecutionBatchRecord.id.desc()))
    tasks = session.scalars(select(ChannelTaskRecord).where(ChannelTaskRecord.tenant_id == tenant_id, ChannelTaskRecord.batch_id == latest_batch.id)).all() if latest_batch else []
    facts = {
        "campaign": {"id": campaign.id, "name": campaign.name, "status": campaign.status, "budget_yuan": campaign.budget_yuan},
        "audience": {"id": audience.id, "name": audience.name, "estimated_size": audience.estimated_size, "expression": json.loads(audience.expression_json)} if audience else None,
        "product": {"id": product.id, "name": product.name, "description": product.description, "eligibility": product.eligibility, "status": product.status} if product else None,
        "feedback": [{"channel": item.channel, "sent": item.sent_count, "delivered": item.delivered_count, "clicked": item.clicked_count, "converted": item.converted_count} for item in tasks],
        "instruction": request.instruction, "channel": request.channel, "objective": request.objective,
        "version": {"id": version.id, "version": version.version, "snapshot_id": snapshot.id if snapshot else None, "channels": json.loads(version.channels_json or "[]")} if version else None,
        "sellability_status": "待上游核验",
    }
    if request.domain_id == "audience-insight":
        facts["available_fields"] = [
            {"code": item.field_code, "name": item.field_name, "type": item.data_type}
            for item in session.scalars(select(PersonaDimensionDefinitionRecord).where(PersonaDimensionDefinitionRecord.tenant_id == tenant_id))
            if item.field_code not in {"member_id", "full_name", "id_number", "mobile", "phone", "email"}
        ]
    return facts


def structured_result(domain, facts, text):
    kinds = {"opportunity-insight": "Recommendation", "product-match": "ValueProposition", "activity-orchestration": "StrategyPlan", "effect-analysis": "Review"}
    result = {"object_type": kinds.get(domain, "Recommendation"), "text": text, "structured": {"status": "待人工确认", "evidence": ["活动版本", "聚合客群", "产品规则"], "sellability_status": "待上游核验"}}
    value = result["structured"]
    if domain == "product-match":
        value.update({"proposition": "按已选客群需求匹配产品规则", "product_id": (facts.get("product") or {}).get("id"), "eligibility": (facts.get("product") or {}).get("eligibility", ""), "inventory_verified": False})
    elif domain == "activity-orchestration":
        value.update({"budget_yuan": facts["campaign"]["budget_yuan"], "touchpoints": [{"channel": channel, "time_window": "19:00—20:00", "trigger": "已授权且未响应才触达", "frequency_cap": "跨渠道7天最多2次", "reason": "按客群渠道偏好与已审核内容配置；实施前人工确认"} for channel in (facts.get("version") or {}).get("channels", [])]})
    elif domain == "effect-analysis":
        feedback = facts.get("feedback", [])
        value.update({"delivered_events": sum(f["delivered"] for f in feedback), "clicked_events": sum(f["clicked"] for f in feedback), "converted_events": sum(f["converted"] for f in feedback), "counting_unit": "渠道事件，非去重旅客", "revenue": None, "roi": None, "attribution_status": "待交易归因", "next_action": "优先核验失败渠道与授权，交易回流后再分析收益"})
    return result


def read_result(events):
    output, applied = {}, None
    for event in events:
        if event.event_type == "business/result-generated":
            output = json.loads(event.payload_json).get("output", {})
        if event.event_type == "business/result-accepted":
            applied = json.loads(event.payload_json).get("object")
    return output, applied


def accept_result(session, context, run_id):
    # Serialize acceptance on PostgreSQL; a repeat request returns the same object.
    run = session.scalar(select(AgentRunRecord).where(AgentRunRecord.id == run_id, AgentRunRecord.tenant_id == context.tenant_id).with_for_update())
    if run is None:
        raise HTTPException(404, "智能域运行不存在")
    session.expire(run, ["events"])
    output, applied = read_result(run.events)
    if applied:
        return applied
    if run.status == "failed" or not output:
        raise HTTPException(409, "本次运行没有可确认的结果")
    facts = output.get("context", {})
    campaign = session.scalar(select(CampaignRecord).where(CampaignRecord.tenant_id == context.tenant_id, CampaignRecord.id == run.campaign_id))
    if campaign is None or campaign.status == "已归档":
        raise HTTPException(409, "活动不存在或已归档")
    if run.domain_id in {"product-match", "activity-orchestration"}:
        product = facts.get("product") or {}
        current = session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.tenant_id == context.tenant_id, ProductPackageRecord.id == product.get("id")))
        if current is None or current.status not in {"已审批", "已通过", "可用"}:
            raise HTTPException(409, "产品依据已失效，请重新生成")
    if run.domain_id == "content-generation":
        audience = facts.get("audience") or {}
        product = facts.get("product") or {}
        if not session.scalar(select(AudiencePackageRecord.id).where(AudiencePackageRecord.tenant_id == context.tenant_id, AudiencePackageRecord.id == audience.get("id"))) or not session.scalar(select(ProductPackageRecord.id).where(ProductPackageRecord.tenant_id == context.tenant_id, ProductPackageRecord.id == product.get("id"))):
            raise HTTPException(409, "生成依据已失效，请重新生成")
        payload = ContentAssetBase(
            campaign_id=campaign.id, audience_package_id=audience["id"], product_package_id=product["id"],
            name=f"{campaign.name}·{facts.get('channel', 'App')}内容"[:160],
            title=output["title"], body=output["body"], channel=facts.get("channel", "App"),
            generation_objective=facts.get("objective", "提升转化"), generation_context={**facts, "visual": output.get("visual", {})},
            generated_by="content-generation", status="待审核",
        )
        asset = ContentAssetRecord(tenant_id=context.tenant_id, external_id=f"CNT-{run.id}", created_by=context.user_id, **payload.model_dump(exclude={"generation_context"}), generation_context_json=json.dumps(payload.generation_context, ensure_ascii=False))
        session.add(asset)
        session.flush()
        applied = {"type": "ContentAsset", "id": asset.id, "external_id": asset.external_id, "label": asset.name}
    elif run.domain_id == "audience-insight":
        audience = facts.get("audience") or {}
        selection = output.get("selection") or {"instruction": facts.get("instruction", ""), "requires_calculation": True}
        if not selection.get("conditions"):
            raise HTTPException(409, "未生成有效圈选条件，请人工配置或重新运行")
        # Model estimates never become a measured population.
        measured = audience.get("estimated_size", 0) if selection == audience.get("expression") else 0
        package = AudiencePackageRecord(tenant_id=context.tenant_id, external_id=f"AUD-{run.id}", name=f"{campaign.name}·圈选草稿"[:160], selection_mode="ai-selection", expression_json=json.dumps(selection, ensure_ascii=False), estimated_size=measured, status="草稿", created_by=context.user_id)
        session.add(package)
        session.flush()
        applied = {"type": "CustomerAggregate", "id": package.id, "external_id": package.external_id, "label": package.name}
    else:
        kind = {"product-match": "ValueProposition", "activity-orchestration": "StrategyPlan", "effect-analysis": "Review"}.get(run.domain_id, "Recommendation")
        applied = {"type": kind, "id": f"RESULT-{run.id}", "external_id": f"RESULT-{run.id}", "label": f"{campaign.name}·{run.domain_id}"}
    from ..ontology.projection import put_entity, put_relation
    entity = put_entity(session, context.tenant_id, applied["external_id"], applied["type"], applied["label"], {"run_id": run.id, "campaign_id": campaign.id, "output": output, **output.get("structured", {}), "status": "待审核" if applied["type"] == "ContentAsset" else "草稿", "confidence_status": "未评估"}, f"agent:{run.id}", 0.0)
    agent = put_entity(session, context.tenant_id, run.id, "AgentRun", run.summary[:200], {"campaign_id": run.campaign_id, "domain_id": run.domain_id, "status": "已确认"}, f"agent:{run.id}")
    put_relation(session, context.tenant_id, agent, "produces_object", entity, f"用户{context.user_id}确认运行{run.id}")
    cn = put_entity(session, context.tenant_id, campaign.id, "Campaign", campaign.name, {"status": campaign.status})
    put_relation(session, context.tenant_id, agent, "supports_campaign", cn)
    decision = put_entity(session, context.tenant_id, "DEC-" + run.id, "HumanDecision", "确认智能体结果", {"operator": context.user_id, "decision": "保存草稿", "campaign_id": campaign.id})
    put_relation(session, context.tenant_id, entity, "confirmed_by_human", decision)
    evidence = put_entity(session, context.tenant_id, "EVID-" + run.id, "Evidence", "智能体输入依据", {"run_id": run.id, "campaign_id": campaign.id, "context": facts, "source_ref": run.id})
    put_relation(session, context.tenant_id, agent, "has_evidence", evidence)
    if applied["type"] == "StrategyPlan":
        put_relation(session, context.tenant_id, cn, "has_strategy_plan", entity)
        for index, plan in enumerate(output.get("structured", {}).get("touchpoints", [])):
            pn = put_entity(session, context.tenant_id, f"TOUCH-{run.id}-{index}", "TouchpointPlan", str(plan.get("channel", "渠道")) + "触点计划", {"campaign_id": campaign.id, "status": "草稿", **plan})
            put_relation(session, context.tenant_id, entity, "uses_touchpoint_plan", pn)
    if applied["type"] == "Review":
        put_relation(session, context.tenant_id, cn, "reviewed_by", entity)
    run.status = "completed"
    session.add(RuntimeEventRecord(id=f"EVT-ACCEPT-{run.id}", run_id=run.id, event_type="business/result-accepted", payload_json=json.dumps({"object": applied, "accepted_by": context.user_id}, ensure_ascii=False)))
    session.commit()
    return applied
