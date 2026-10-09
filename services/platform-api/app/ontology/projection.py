"""Maintain the ontology projection from tenant business records in the same transaction."""
import json
from sqlalchemy import select, delete, event
from sqlalchemy.orm import Session
from ..db_models import (CampaignRecord, CampaignVersionRecord, AudienceSnapshotRecord, AudiencePackageRecord, ProductPackageRecord, ContentAssetRecord, ApprovalTaskRecord, ExecutionBatchRecord, ChannelTaskRecord, AgentRunRecord, OntologyEntityRecord, OntologyRelationRecord)
from .semantic_model import validate_relation_endpoints


def put_entity(session, tenant_id, external_id, entity_type, label, attributes, source="业务同步", confidence=1.0):
    record = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == external_id))
    if record is None:
        record = OntologyEntityRecord(tenant_id=tenant_id, external_id=external_id, entity_type=entity_type, label=label, source=source, confidence=confidence)
        session.add(record)
    old = json.loads(record.attributes_json or "{}")
    value = json.dumps({**old, **attributes}, ensure_ascii=False, sort_keys=True)
    if record.attributes_json != value:
        record.attributes_json = value
    record.label, record.entity_type = label, entity_type
    session.flush()
    return record


def put_relation(session, tenant_id, source, relation, target, evidence="业务记录关联", provenance="业务同步"):
    problem = validate_relation_endpoints(relation, source.entity_type, target.entity_type)
    if problem:
        raise ValueError(problem)
    existing = session.scalar(select(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == tenant_id, OntologyRelationRecord.source_entity_id == source.id, OntologyRelationRecord.target_entity_id == target.id, OntologyRelationRecord.relation_type == relation))
    if existing is None:
        session.add(OntologyRelationRecord(tenant_id=tenant_id, source_entity_id=source.id, target_entity_id=target.id, relation_type=relation, evidence=evidence, source=provenance, confidence=1.0))


def sync_business_graph(session, tenant_id):
    session.flush()
    def rows(model):
        return list(session.scalars(select(model).where(model.tenant_id == tenant_id)))
    campaigns = {c.id: c for c in rows(CampaignRecord)}
    versions = rows(CampaignVersionRecord)
    snapshots = {s.id: s for s in rows(AudienceSnapshotRecord)}
    products = {p.id: p for p in rows(ProductPackageRecord)}
    contents = {c.id: c for c in rows(ContentAssetRecord)}
    nodes = {}
    def node(key, kind, label, attrs):
        nodes[key] = put_entity(session, tenant_id, key, kind, label, {**attrs, "business_projection": True})
        return nodes[key]
    def link(a, rel, b, evidence="业务记录关联"):
        put_relation(session, tenant_id, a, rel, b, evidence, "business-projection")
    for snapshot in snapshots.values():
        node(snapshot.external_id, "AudienceSnapshot", snapshot.external_id, {"population": snapshot.estimated_size, "status": snapshot.status, "selection_logic": json.loads(snapshot.expression_json), "frozen_at": snapshot.created_at.isoformat()})
    for audience in rows(AudiencePackageRecord):
        node(audience.external_id, "CustomerAggregate", audience.name, {"status": audience.status, "population": audience.estimated_size, "selection_logic": json.loads(audience.expression_json)})
    for product in products.values():
        node(product.external_id, "ProductPackage", product.name, {"status": product.status, "version": product.version, "eligibility": product.eligibility, "sellability_status": "待上游核验"})
    for content in contents.values():
        node(content.external_id, "ContentAsset", content.name, {"campaign_id": content.campaign_id, "channel": content.channel, "status": content.status, "version": content.version, "title": content.title})
    for campaign in campaigns.values():
        node(campaign.id, "Campaign", campaign.name, {"campaign_id": campaign.id, "status": campaign.status, "stage": campaign.stage, "version": campaign.version, "owner": campaign.owner})
    for run in rows(AgentRunRecord):
        rn = node(run.id, "AgentRun", run.summary[:200], {"campaign_id": run.campaign_id, "domain_id": run.domain_id, "status": run.status})
        if run.campaign_id in nodes:
            link(rn, "supports_campaign", nodes[run.campaign_id])
    for version in versions:
        campaign = campaigns.get(version.campaign_id)
        if not campaign:
            continue
        attrs = {"campaign_id": campaign.id, "status": version.status, "version": version.version, "channels": json.loads(version.channels_json or "[]"), "budget_yuan": version.budget_yuan}
        vn = node(version.external_id, "CampaignVersion", campaign.name + " " + version.version, attrs)
        cn = nodes[campaign.id]
        link(cn, "has_campaign_version", vn)
        snapshot, product = snapshots.get(version.audience_snapshot_id), products.get(version.product_package_id)
        if snapshot:
            sn = node(snapshot.external_id, "AudienceSnapshot", snapshot.external_id, {"population": snapshot.estimated_size, "status": snapshot.status, "selection_logic": json.loads(snapshot.expression_json), "frozen_at": snapshot.created_at.isoformat()})
            link(cn, "targets_audience", sn)
        if product:
            pn = node(product.external_id, "ProductPackage", product.name, {"status": product.status, "version": product.version, "eligibility": product.eligibility, "sellability_status": "待上游核验"})
            link(cn, "uses_product_package", pn)
        for content_id in json.loads(version.content_asset_ids_json or "[]"):
            content = contents.get(content_id)
            if content:
                an = node(content.external_id, "ContentAsset", content.name, {"campaign_id": campaign.id, "channel": content.channel, "status": content.status, "version": content.version, "title": content.title})
                link(vn, "generates_content", an)
    for approval in rows(ApprovalTaskRecord):
        version = next((v for v in versions if v.id == approval.campaign_version_id), None)
        if not version or version.external_id not in nodes:
            continue
        an = node(approval.external_id, "ApprovalTask", "审批 · " + approval.status, {"campaign_id": approval.campaign_id, "status": approval.status, "comment": approval.comment, "approver_role": approval.approver_role})
        link(nodes[version.external_id], "requires_approval", an)
        if approval.decided_at:
            hn = node("DECISION-" + approval.external_id, "HumanDecision", "人工决策 · " + approval.status, {"campaign_id": approval.campaign_id, "decision": approval.status, "operator": approval.decided_by, "comment": approval.comment, "decided_at": approval.decided_at.isoformat()})
            link(nodes[version.external_id], "confirmed_by_human", hn)
    tasks = rows(ChannelTaskRecord)
    for batch in rows(ExecutionBatchRecord):
        version = next((v for v in versions if v.id == batch.campaign_version_id), None)
        if not version or version.external_id not in nodes:
            continue
        bn = node(batch.external_id, "ExecutionBatch", "执行 · " + batch.status, {"campaign_id": batch.campaign_id, "status": batch.status, "target_count": batch.target_size, "delivered_count": batch.delivered_count, "failed_count": batch.failed_count, "synthetic": True})
        link(nodes[version.external_id], "executes", bn)
        for task in [t for t in tasks if t.batch_id == batch.id]:
            channel = node("CHANNEL-" + task.channel, "Channel", task.channel, {"status": "模拟渠道", "channel_code": task.channel})
            link(bn, "uses_channel", channel)
            if task.sent_count or task.status == "失败":
                fn = node("FB-" + task.external_id, "Feedback", task.channel + "渠道回执", {"campaign_id": batch.campaign_id, "status": task.status, "target_count": task.target_count, "sent_count": task.sent_count, "delivered_count": task.delivered_count, "clicked_count": task.clicked_count, "converted_count": task.converted_count, "failed_count": task.failed_count, "counting_unit": "渠道事件，非去重旅客", "synthetic": True})
                link(bn, "produces_feedback", fn)
        if batch.delivered_count:
            rn = node("REVIEW-" + batch.external_id, "Review", "渠道效果复盘 · " + batch.campaign_id, {"campaign_id": batch.campaign_id, "status": "待人工确认", "conclusion": "对比送达、点击与转化事件；收入、ROI等待交易归因", "revenue_status": "待交易归因", "synthetic": True})
            link(nodes[batch.campaign_id], "reviewed_by", rn)
    # Remove only stale projection objects; tenant-authored knowledge is retained.
    stale = [e.id for e in rows(OntologyEntityRecord) if json.loads(e.attributes_json or "{}").get("business_projection") and e.external_id not in nodes]
    if stale:
        session.execute(delete(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == tenant_id, (OntologyRelationRecord.source_entity_id.in_(stale)) | (OntologyRelationRecord.target_entity_id.in_(stale))))
        session.execute(delete(OntologyEntityRecord).where(OntologyEntityRecord.id.in_(stale)))


BUSINESS_TYPES = (CampaignRecord, CampaignVersionRecord, AudienceSnapshotRecord, AudiencePackageRecord, ProductPackageRecord, ContentAssetRecord, ApprovalTaskRecord, ExecutionBatchRecord, ChannelTaskRecord, AgentRunRecord)


@event.listens_for(Session, "before_flush")
def remember_business_changes(session, *_):
    if not session.info.get("projecting"):
        session.info.setdefault("projection_tenants", set()).update(
            record.tenant_id for record in list(session.new) + list(session.dirty) + list(session.deleted)
            if isinstance(record, BUSINESS_TYPES) and record.tenant_id
        )


@event.listens_for(Session, "before_commit")
def project_business_changes(session):
    if session.info.get("projecting"):
        return
    tenant_ids = session.info.pop("projection_tenants", set()) | {record.tenant_id for record in list(session.new) + list(session.dirty) + list(session.deleted) if isinstance(record, BUSINESS_TYPES) and record.tenant_id}
    session.info["projecting"] = True
    try:
        for tenant_id in tenant_ids:
            sync_business_graph(session, tenant_id)
    finally:
        session.info.pop("projecting", None)


@event.listens_for(Session, "after_rollback")
@event.listens_for(Session, "after_commit")
def clear_projection_changes(session):
    session.info.pop("projection_tenants", None)
