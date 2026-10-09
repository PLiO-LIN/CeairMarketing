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
    tasks = session.scalars(select(ChannelTaskRecord).where(ChannelTaskRecord.tenant_id == tenant_id, ChannelTaskRecord.campaign_id == campaign.id)).all()
    facts = {
        "campaign": {"id": campaign.id, "name": campaign.name, "status": campaign.status, "budget_yuan": campaign.budget_yuan},
        "audience": {"id": audience.id, "name": audience.name, "estimated_size": audience.estimated_size, "expression": json.loads(audience.expression_json)} if audience else None,
        "product": {"id": product.id, "name": product.name, "description": product.description, "eligibility": product.eligibility, "status": product.status} if product else None,
        "feedback": [{"channel": item.channel, "sent": item.sent_count, "delivered": item.delivered_count, "clicked": item.clicked_count, "converted": item.converted_count} for item in tasks],
        "instruction": request.instruction, "channel": request.channel, "objective": request.objective,
    }
    if request.domain_id == "audience-insight":
        facts["available_fields"] = [
            {"code": item.field_code, "name": item.field_name, "type": item.data_type}
            for item in session.scalars(select(PersonaDimensionDefinitionRecord).where(PersonaDimensionDefinitionRecord.tenant_id == tenant_id))
            if item.field_code not in {"member_id", "full_name", "id_number", "mobile", "phone", "email"}
        ]
    return facts


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
    if run.domain_id == "content-generation":
        audience = facts.get("audience") or {}
        product = facts.get("product") or {}
        if not session.scalar(select(AudiencePackageRecord.id).where(AudiencePackageRecord.tenant_id == context.tenant_id, AudiencePackageRecord.id == audience.get("id"))) or not session.scalar(select(ProductPackageRecord.id).where(ProductPackageRecord.tenant_id == context.tenant_id, ProductPackageRecord.id == product.get("id"))):
            raise HTTPException(409, "生成依据已失效，请重新生成")
        payload = ContentAssetBase(
            campaign_id=campaign.id, audience_package_id=audience["id"], product_package_id=product["id"],
            name=f"{campaign.name}·{facts.get('channel', 'App')}内容"[:160],
            title=output["title"], body=output["body"], channel=facts.get("channel", "App"),
            generation_objective=facts.get("objective", "提升转化"), generation_context=facts,
            generated_by="content-generation", status="待审核",
        )
        asset = ContentAssetRecord(tenant_id=context.tenant_id, external_id=f"CNT-{run.id}", created_by=context.user_id, **payload.model_dump(exclude={"generation_context"}), generation_context_json=json.dumps(facts, ensure_ascii=False))
        session.add(asset)
        session.flush()
        applied = {"type": "ContentAsset", "id": asset.id, "external_id": asset.external_id, "label": asset.name}
    elif run.domain_id == "audience-insight":
        audience = facts.get("audience") or {}
        selection = output.get("selection") or {"instruction": facts.get("instruction", ""), "requires_calculation": True}
        # Model estimates never become a measured population.
        measured = audience.get("estimated_size", 0) if selection == audience.get("expression") else 0
        package = AudiencePackageRecord(tenant_id=context.tenant_id, external_id=f"AUD-{run.id}", name=f"{campaign.name}·圈选草稿"[:160], selection_mode="ai-selection", expression_json=json.dumps(selection, ensure_ascii=False), estimated_size=measured, status="草稿", created_by=context.user_id)
        session.add(package)
        session.flush()
        applied = {"type": "CustomerAggregate", "id": package.id, "external_id": package.external_id, "label": package.name}
    else:
        applied = {"type": "Recommendation", "id": f"REC-{run.id}", "external_id": f"REC-{run.id}", "label": f"{campaign.name}·{run.domain_id}"}
    entity = OntologyEntityRecord(tenant_id=context.tenant_id, external_id=applied["external_id"], entity_type=applied["type"], label=applied["label"], attributes_json=json.dumps({"run_id": run.id, "status": "draft", "output": output}, ensure_ascii=False), source=f"agent:{run.id}", confidence=0.0)
    session.add(entity)
    session.flush()
    agent = OntologyEntityRecord(tenant_id=context.tenant_id, external_id=run.id, entity_type="AgentRun", label=run.summary[:200], attributes_json=json.dumps({"campaign_id": run.campaign_id, "domain_id": run.domain_id}), source=f"agent:{run.id}", confidence=1.0)
    session.add(agent)
    session.flush()
    if applied["type"] in {"ContentAsset", "Recommendation"}:
        relation = "generates_content" if applied["type"] == "ContentAsset" else "generates_recommendation"
        session.add(OntologyRelationRecord(tenant_id=context.tenant_id, source_entity_id=agent.id, target_entity_id=entity.id, relation_type=relation, evidence=f"用户{context.user_id}确认运行{run.id}", source=f"agent:{run.id}", confidence=1.0))
    session.add(RuntimeEventRecord(id=f"EVT-ACCEPT-{run.id}", run_id=run.id, event_type="business/result-accepted", payload_json=json.dumps({"object": applied, "accepted_by": context.user_id}, ensure_ascii=False)))
    session.commit()
    return applied
