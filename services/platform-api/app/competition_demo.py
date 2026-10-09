"""Idempotent, tenant-isolated competition fixtures and their visible evidence."""
import json
from datetime import datetime, timezone, timedelta
from hashlib import sha256

from sqlalchemy import select
from .db_models import (TenantRecord, CampaignRecord, CampaignVersionRecord, AudiencePackageRecord, AudienceSnapshotRecord, ProductPackageRecord, ContentAssetRecord, ApprovalTaskRecord, ExecutionBatchRecord, ChannelTaskRecord, KnowledgeDocumentRecord, KnowledgeChunkRecord, AgentRunRecord, RuntimeEventRecord, ModelProviderRecord, ImportJobRecord, OpportunityRecord, OpportunityInsightSourceRecord, OpportunityInsightRunRecord, DataPipelineJobRecord, OntologyEntityRecord)
from .ontology.projection import put_entity, put_relation, sync_business_graph
from .ontology.semantic_model import agent_contract

DEMO_DATE = datetime(2026, 9, 18, 10, tzinfo=timezone(timedelta(hours=8)))
DEMO_TIMESTAMP = DEMO_DATE.astimezone(timezone.utc)
DOMAIN_LABELS = {"opportunity-insight": "机会洞察", "audience-insight": "客群洞察", "product-match": "产品匹配", "activity-orchestration": "活动编排", "content-generation": "内容生成", "effect-analysis": "效果分析"}
SIGNALS = [
    {"id": "SIG-DEMO-SEARCH", "title": "三亚目的地搜索", "source": "模拟旅游搜索聚合接口", "window": "2026-09-04 至 2026-09-17", "previous": 10000, "current": 13200, "growth": 32, "unit": "搜索事件", "confidence": .88, "weight": .4},
    {"id": "SIG-DEMO-HOTEL", "title": "三亚酒店关注", "source": "模拟酒店浏览聚合接口", "window": "2026-09-04 至 2026-09-17", "previous": 8000, "current": 10000, "growth": 25, "unit": "浏览事件", "confidence": .85, "weight": .25},
    {"id": "SIG-DEMO-GUIDE", "title": "亲子攻略收藏", "source": "模拟文旅内容聚合接口", "window": "2026-09-04 至 2026-09-17", "previous": 5000, "current": 6500, "growth": 30, "unit": "收藏事件", "confidence": .83, "weight": .2},
    {"id": "SIG-DEMO-LOAD", "title": "SHA-SYX可经营窗口", "source": "模拟航线经营接口", "window": "出发前15天", "previous": 70, "current": 62, "growth": -8, "unit": "客座率%", "confidence": .98, "weight": .15},
]
PROFILE = {
    "name": "三亚高意向未购客群", "population": 36420,
    "regions": [{"label": "上海", "value": 18210}, {"label": "江苏", "value": 10926}, {"label": "浙江", "value": 7284}],
    "preferences": [{"label": "家庭同行", "value": 68}, {"label": "行李权益", "value": 43}, {"label": "优选座位", "value": 31}],
    "timeline": [
        {"date": "09-04", "event": "浏览目的地与旅游攻略", "intent": .42, "stage": "种草期"},
        {"date": "09-10", "event": "搜索三亚航班与酒店", "intent": .67, "stage": "比价期"},
        {"date": "09-17", "event": "多次搜索并收藏，尚未出票", "intent": .86, "stage": "决策期"},
        {"date": "09-18", "event": "授权与疲劳排除后冻结快照", "intent": .86, "stage": "可触达"},
    ],
    "funnel": [{"label": "有目的地关注", "value": 51200}, {"label": "近7天搜索≥2次", "value": 42000}, {"label": "尚未出票", "value": 36930}, {"label": "授权与保护排除后", "value": 36420}],
    "excluded": 510, "rule": "search_destination=三亚 AND search_frequency_7d>=2 AND decision_stage IN 比价期/决策期；上游排除已出票、未授权和营销疲劳客群",
}
TOUCHPOINTS = [
    {"channel": "App", "time": "19:00—20:00", "trigger": "近7天多次搜索但未出票", "reason": "客群App活跃占比高，能完整展示行李与座位权益", "frequency": "7天最多2次，跨渠道合计", "role": "首触"},
    {"channel": "微信", "time": "次日19:00—20:00", "trigger": "首触未点击，且微信已授权", "reason": "图文补充家庭出游信息；已响应客户不再补触", "frequency": "与App共享频控", "role": "条件补触"},
    {"channel": "短信", "time": "次日10:00—18:00", "trigger": "仅对已授权且偏好短信的客群", "reason": "用于辅营服务提醒；失败任务先核验后重试", "frequency": "7天最多1次", "role": "服务提醒"},
]
SCORE_COMPONENTS = [
    {"label": "需求热度", "weight": 40, "score": 96, "basis": "搜索、酒店、攻略共同增长"},
    {"label": "搜索未购", "weight": 25, "score": 92, "basis": "近7天多次搜索且处于比价或决策期"},
    {"label": "供给窗口", "weight": 20, "score": 88, "basis": "模拟客座率62%，真实库存待核验"},
    {"label": "产品适配", "weight": 15, "score": 86, "basis": "行李与座位权益适配家庭需求"},
]


def dump(value):
    return json.dumps(value, ensure_ascii=False)


def seed_extended_demo(session, tenant_id, user_id):
    tenant = session.get(TenantRecord, tenant_id)
    if not tenant or tenant.code != "CEA-COMPETITION":
        return
    def ensure(model, external_id, **values):
        field = model.id if model in {CampaignRecord, OpportunityRecord, AgentRunRecord, ImportJobRecord, DataPipelineJobRecord, OpportunityInsightRunRecord} else model.external_id
        record = session.scalar(select(model).where(model.tenant_id == tenant_id, field == external_id))
        if record is None:
            record = model(tenant_id=tenant_id, **{field.key: external_id}, **values)
            session.add(record)
            session.flush()
        return record
    main = session.get(CampaignRecord, (tenant_id, "ACT-2026-0921"))
    audience = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == tenant_id, AudiencePackageRecord.external_id == "AUD-DEMO-SANYA"))
    product = session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.tenant_id == tenant_id, ProductPackageRecord.external_id == "PKG-DEMO-SANYA"))
    version = session.scalar(select(CampaignVersionRecord).where(CampaignVersionRecord.tenant_id == tenant_id, CampaignVersionRecord.external_id == main.id + "-V3"))
    app_content = session.scalar(select(ContentAssetRecord).where(ContentAssetRecord.tenant_id == tenant_id, ContentAssetRecord.external_id == "CNT-DEMO-SANYA-APP-V3"))
    wechat = ensure(ContentAssetRecord, "CNT-DEMO-SANYA-WECHAT-V3", campaign_id=main.id, audience_package_id=audience.id, product_package_id=product.id, name="微信家庭出游图文V3", channel="微信", version="V3", title="带家人看海，提前安排三亚行程", body="上海—三亚出行方案，搭配行李与优选座位权益。适用航班、价格和库存以最终产品规则为准。", status="已审核", generated_by="demo-template", created_by=user_id, generation_context_json=dump({"synthetic": True, "visual": {"theme": "family", "headline": "带家人，看一片海", "destination": "三亚", "benefit": "行李 · 优选座位"}}))
    # Upgrade only the known original fixture, once; never reset an operated case.
    original = app_content.generation_context
    if not original.get("demo_extended_v1"):
        app_content.generation_context_json = dump({**original, "demo_extended_v1": True, "synthetic": True, "visual": {"theme": "family", "headline": "国庆去三亚，出行更从容", "destination": "三亚", "benefit": "行李 · 优选座位"}})
        if version.status == "待审批":
            app_content.status = "已审核"
            version.content_asset_ids_json = dump([app_content.id, wechat.id])
            snapshot_record = session.get(AudienceSnapshotRecord, version.audience_snapshot_id)
            if "conditions" not in json.loads(audience.expression_json):
                audience.expression_json = dump({"conditions": [{"field_code": "search_destination", "operator": "eq", "value": "三亚"}, {"field_code": "search_frequency_7d", "operator": "gte", "value": 2}, {"field_code": "decision_stage", "operator": "in", "value": ["比价期", "决策期"]}], "upstream_exclusions": ["已出票", "未授权", "营销疲劳"], "synthetic": True})
                snapshot_record.expression_json = audience.expression_json
            opportunity_record = session.get(OpportunityRecord, (tenant_id, "OPP-2026-0921"))
            if opportunity_record:
                opportunity_record.status = "已转活动"
                opportunity_record.signal_summary = "模拟目的地搜索热度上升32%，客座率62%；实际库存需上游核验。"
    examples = [
        ("ACT-DEMO-ANCILLARY", "上海—成都行李优享", "执行", "执行中", "辅营组合", "额外行李与优选座位", 12800, ["App", "短信"], "已通过"),
        ("ACT-DEMO-MEMBER", "会员秋季出游唤醒", "复盘", "已完成", "会员权益", "会员积分与出游权益提醒", 9840, ["App", "微信"], "已通过"),
        ("ACT-DEMO-BLOCKED", "三亚产品资格待核验", "内容", "待修改", "机票组合", "价格和库存待核验的候选方案", 6200, ["App"], "已退回"),
    ]
    for cid, name, stage, status, ptype, desc, population, channels, approval_status in examples:
        aud = ensure(AudiencePackageRecord, "AUD-" + cid, name=name + "客群", selection_mode="tag-combination", expression_json=dump({"conditions": [{"field_code": "decision_stage", "operator": "in", "value": ["比价期", "决策期"]}], "synthetic": True}), estimated_size=population, status="可用", created_by=user_id)
        snap = ensure(AudienceSnapshotRecord, "SNAP-" + cid, package_id=aud.id, version="V1", expression_json=aud.expression_json, estimated_size=population, source="竞赛虚构聚合客群", status="已冻结", created_by=user_id)
        pkg = ensure(ProductPackageRecord, "PKG-" + cid, name=name + "产品包", product_type=ptype, description=desc, eligibility="已授权触达；实际产品价格与库存需上游核验", status="草稿" if approval_status == "已退回" else "已审批", created_by=user_id)
        campaign = ensure(CampaignRecord, cid, name=name, stage=stage, status=status, version="V1", owner="竞赛运营", audience_size=population, product_package=pkg.name, budget_yuan=50000, roi_target=3.0)
        assets = [ensure(ContentAssetRecord, "CNT-" + cid + "-" + str(i), campaign_id=cid, audience_package_id=aud.id, product_package_id=pkg.id, name=name + "·" + channel, channel=channel, title=name, body=desc + "。适用规则以最终审核内容为准。", status="待审核" if approval_status == "已退回" else "已审核", created_by=user_id, generation_context_json=dump({"synthetic": True, "visual": {"theme": "business" if cid.endswith("MEMBER") else "family", "headline": name, "destination": "秋季出游", "benefit": desc}})) for i, channel in enumerate(channels)]
        ver = ensure(CampaignVersionRecord, cid + "-V1", campaign_id=cid, version="V1", audience_snapshot_id=snap.id, product_package_id=pkg.id, content_asset_ids_json=dump([a.id for a in assets]), channels_json=dump(channels), budget_yuan=50000, status=approval_status, created_by=user_id)
        ensure(ApprovalTaskRecord, "APR-" + cid, campaign_id=cid, campaign_version_id=ver.id, approver_role="营销经理", status=approval_status, comment="模拟业务审批；价格库存仍需上游核验" if approval_status == "已通过" else "产品未审批，补充资格规则与库存依据后重新提交", decided_by=user_id, decided_at=DEMO_TIMESTAMP)
        opp = ensure(OpportunityRecord, "OPP-" + cid, name=name, market_scope="会员运营" if cid.endswith("MEMBER") else "国内旅游", route="SHA-CTU" if cid.endswith("ANCILLARY") else "SHA-SYX", signal_summary=desc + "（虚构案例）", status="待评估" if approval_status == "已退回" else "已转活动", score=85, estimated_audience=population, owner="竞赛运营", estimated_revenue_yuan=0)
        on = put_entity(session, tenant_id, opp.id, "Opportunity", opp.name, {"campaign_id": cid, "status": opp.status, "synthetic": True, "score": opp.score})
        cn = put_entity(session, tenant_id, cid, "Campaign", campaign.name, {"campaign_id": cid, "status": campaign.status})
        put_relation(session, tenant_id, cn, "addresses_opportunity", on)
        if approval_status == "已退回":
            continue
        batch = ensure(ExecutionBatchRecord, "BATCH-" + cid, campaign_id=cid, campaign_version_id=ver.id, channels_json=dump(channels), target_size=population, status=status, created_by=user_id)
        for i, channel in enumerate(channels):
            target = population // len(channels)
            failed = target if cid.endswith("ANCILLARY") and channel == "短信" else int(target * .02)
            delivered = target - failed
            ensure(ChannelTaskRecord, "TASK-" + cid + "-" + str(i), batch_id=batch.id, campaign_id=cid, channel=channel, target_count=target, sent_count=target, delivered_count=delivered, clicked_count=int(delivered*.12), converted_count=int(delivered*.025), failed_count=failed, status="失败" if failed == target else "已完成", last_feedback_at=DEMO_TIMESTAMP)
        batch_tasks = list(session.scalars(select(ChannelTaskRecord).where(ChannelTaskRecord.tenant_id == tenant_id, ChannelTaskRecord.batch_id == batch.id)))
        batch.delivered_count = sum(t.delivered_count for t in batch_tasks)
        batch.failed_count = sum(t.failed_count for t in batch_tasks)
        batch.feedback_count = sum(t.clicked_count + t.converted_count for t in batch_tasks)
    for key, text in [("SIGNALS", "模拟搜索13200次，对比上期10000次，上升32%；酒店浏览10000次，攻略收藏6500次。统计窗口2026-09-04至2026-09-17。"), ("RULES", "渠道内容必须已审核；授权与保护排除后冻结客群；App首触，未响应才补触，跨渠道7天最多2次。库存和价格缺少上游证据时不得宣称已核验。")]:
        doc = ensure(KnowledgeDocumentRecord, "DOC-DEMO-" + key, title="竞赛模拟" + ("需求证据" if key == "SIGNALS" else "营销业务规则"), source_type="competition", source_name="竞赛虚构案例", content=text, content_hash=sha256(text.encode()).hexdigest())
        chunk = ensure(KnowledgeChunkRecord, "CHUNK-DEMO-" + key, document_id=doc.id, sequence=1, heading=doc.title, content=text, metadata_json=dump({"synthetic": True, "page_no": 1}))
        dn = put_entity(session, tenant_id, doc.external_id, "KnowledgeDocument", doc.title, {"synthetic": True, "source_name": doc.source_name})
        kn = put_entity(session, tenant_id, chunk.external_id, "KnowledgeChunk", chunk.heading, {"synthetic": True, "document_id": doc.external_id, "excerpt": text})
        put_relation(session, tenant_id, dn, "contains_chunk", kn, "模拟文档第1页")
    evidence = put_entity(session, tenant_id, "EVID-DEMO-SANYA", "Evidence", "需求与经营窗口联合证据", {"signals": SIGNALS, "synthetic": True, "captured_at": DEMO_DATE.isoformat(), "scoring": "需求热度40% + 搜索未购25% + 供给窗口20% + 产品适配15%；演示评分92，不代表预测准确率"}, "竞赛模拟聚合接口", .88)
    route = put_entity(session, tenant_id, "ROUTE-DEMO-SHA-SYX", "Route", "上海—三亚", {"origin": "SHA", "destination": "SYX", "synthetic": True})
    opportunity = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == "OPP-2026-0921"))
    put_relation(session, tenant_id, opportunity, "has_evidence", evidence)
    put_relation(session, tenant_id, opportunity, "concerns_route", route)
    for signal in SIGNALS:
        sn = put_entity(session, tenant_id, signal["id"], "MarketSignal", signal["title"], {**signal, "synthetic": True}, signal["source"], signal["confidence"])
        put_relation(session, tenant_id, sn, "derived_from", evidence)
        put_relation(session, tenant_id, opportunity, "derived_from", sn)
    chunk_node = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == "CHUNK-DEMO-SIGNALS"))
    put_relation(session, tenant_id, chunk_node, "evidence_for", evidence, "DOC-DEMO-SIGNALS 第1页")
    claim = put_entity(session, tenant_id, "CLAIM-DEMO-SEARCH", "KnowledgeClaim", "三亚搜索同比上期增长32%", {"claim_type": "聚合观测", "synthetic": True, "confidence": .88})
    put_relation(session, tenant_id, chunk_node, "supports_claim", claim, "模拟需求文档第1页")
    put_relation(session, tenant_id, claim, "claims_about", opportunity)
    need = put_entity(session, tenant_id, "NEED-DEMO-FAMILY", "CustomerNeed", "家庭出游省心与确定性", {"journey_stage": "搜索未购", "benefits": ["行李", "座位"], "synthetic": True})
    put_relation(session, tenant_id, opportunity, "reveals_need", need)
    snapshot = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == "AUD-SNAP-DEMO-SANYA-V4"))
    put_relation(session, tenant_id, snapshot, "reveals_need", need)
    strategy = put_entity(session, tenant_id, "STRATEGY-DEMO-SANYA", "StrategyPlan", "家庭出游跨渠道策略", {"campaign_id": main.id, "status": "待确认", "touchpoints": TOUCHPOINTS, "synthetic": True})
    campaign_node = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == main.id))
    put_relation(session, tenant_id, campaign_node, "has_strategy_plan", strategy)
    rule = put_entity(session, tenant_id, "RULE-DEMO-FREQUENCY", "BusinessRule", "跨渠道授权与频控保护", {"rule_type": "contact-frequency", "expression": "已授权 AND 跨渠道7天最多2次", "synthetic": True})
    rule_chunk = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == "CHUNK-DEMO-RULES"))
    put_relation(session, tenant_id, rule_chunk, "supports_claim", rule, "模拟规则文档第1页")
    put_relation(session, tenant_id, rule_chunk, "evidence_for", strategy, "策略采用文档频控规则")
    for i, plan in enumerate(TOUCHPOINTS[:2]):
        pn = put_entity(session, tenant_id, "TOUCH-DEMO-" + str(i), "TouchpointPlan", plan["channel"] + "·" + plan["role"], {**plan, "campaign_id": main.id, "status": "待审批", "synthetic": True})
        put_relation(session, tenant_id, strategy, "uses_touchpoint_plan", pn)
    provider = session.scalar(select(ModelProviderRecord).where(ModelProviderRecord.tenant_id == tenant_id, ModelProviderRecord.is_default.is_(True)))
    for index, (domain, label) in enumerate(DOMAIN_LABELS.items()):
        cid = "ACT-DEMO-MEMBER" if domain == "effect-analysis" else main.id
        run_campaign = session.get(CampaignRecord, (tenant_id, cid))
        run_audience = session.scalar(select(AudiencePackageRecord).where(AudiencePackageRecord.tenant_id == tenant_id, AudiencePackageRecord.external_id == ("AUD-" + cid if cid != main.id else "AUD-DEMO-SANYA"))) or audience
        run_product = session.scalar(select(ProductPackageRecord).where(ProductPackageRecord.tenant_id == tenant_id, ProductPackageRecord.external_id == ("PKG-" + cid if cid != main.id else "PKG-DEMO-SANYA"))) or product
        rid = "RUN-DEMO-" + str(index)
        if session.get(AgentRunRecord, rid):
            continue
        contract = agent_contract(domain)
        summary = label + "受控样例：依据聚合事实生成候选，业务人员确认后保存"
        object_type = {"opportunity-insight": "Recommendation", "audience-insight": "CustomerAggregate", "product-match": "ValueProposition", "activity-orchestration": "StrategyPlan", "content-generation": "ContentAsset", "effect-analysis": "Review"}[domain]
        output = {"text": summary, "title": label + "演示结果", "body": app_content.body if domain == "content-generation" else summary, "provider_type": "mock", "synthetic": True, "object_type": object_type, "context": {"campaign": {"id": cid, "name": run_campaign.name}, "audience": {"id": run_audience.id, "name": run_audience.name, "estimated_size": run_audience.estimated_size}, "product": {"id": run_product.id, "name": run_product.name}, "channel": "App", "evidence": "EVID-DEMO-SANYA"}, "structured": {"status": "待人工确认", "reason": "以冻结快照、产品版本和来源证据约束输出", "revenue_status": "待交易归因", "campaign_id": cid}}
        from types import SimpleNamespace
        from .agents.business_results import business_context, structured_result
        facts = business_context(session, tenant_id, run_campaign, SimpleNamespace(audience_package_id=run_audience.id, product_package_id=run_product.id, domain_id=domain, instruction="选择关注三亚的旅客" if domain == "audience-insight" else "按当前业务版本提出建议", channel="App", objective="提升转化"))
        output["context"] = facts
        output["execution"] = "governed-mock"
        if domain in {"opportunity-insight", "product-match", "activity-orchestration", "effect-analysis"}:
            output.update(structured_result(domain, facts, summary))
        if domain == "audience-insight":
            output["selection"] = {"conditions": [{"field_code": "search_destination", "operator": "eq", "value": "三亚"}, {"field_code": "search_frequency_7d", "operator": "gte", "value": 2}], "requires_calculation": True}
        if domain == "content-generation":
            output["visual"] = app_content.generation_context["visual"]
        run = ensure(AgentRunRecord, rid, campaign_id=cid, domain_id=domain, operator="竞赛运营（预置样例）", provider_id=provider.id, status="needs_approval", summary=summary, created_at=DEMO_TIMESTAMP + timedelta(minutes=index))
        for j, (kind, payload) in enumerate([("agent/run-started", {"detail": "预置受控流程样例，非真实模型推理"}), ("ontology/context-loaded", {**contract, "detail": "读取本体契约与已授权业务对象"}), ("business/context-loaded", {"detail": f"读取{run_campaign.name}：聚合客群{run_audience.estimated_size}人、产品{run_product.name}；库存待上游核验"}), ("business/result-generated", {"output": output}), ("governance/human-review", {"required": True, "detail": "人工确认后保存业务草稿"})]):
            session.add(RuntimeEventRecord(id=f"EVT-DEMO-{index}-{j}", run_id=rid, event_type=kind, payload_json=dump(payload), timestamp=DEMO_TIMESTAMP + timedelta(minutes=index, seconds=j)))
        rn = put_entity(session, tenant_id, rid, "AgentRun", label + "运行样例", {"campaign_id": cid, "domain_id": domain, "status": run.status, "synthetic": True})
        run_evidence = evidence
        if domain == "effect-analysis":
            run_evidence = put_entity(session, tenant_id, "EVID-DEMO-MEMBER-FEEDBACK", "Evidence", "会员活动渠道回执依据", {"campaign_id": cid, "feedback": facts["feedback"], "synthetic": True, "source_ref": "BATCH-ACT-DEMO-MEMBER"})
        put_relation(session, tenant_id, rn, "has_evidence", run_evidence)
        run_cn = put_entity(session, tenant_id, cid, "Campaign", run_campaign.name, {"campaign_id": cid, "status": run_campaign.status})
        put_relation(session, tenant_id, rn, "supports_campaign", run_cn)
        if domain in {"opportunity-insight", "product-match", "activity-orchestration", "effect-analysis"}:
            candidate = put_entity(session, tenant_id, "RESULT-" + rid, object_type, run_campaign.name + "·" + label + "候选", {**output["structured"], "campaign_id": cid, "status": "待人工确认", "synthetic": True, "confidence_status": "未评估"}, "受控预置样例", 0)
            put_relation(session, tenant_id, rn, "produces_object", candidate)
            put_relation(session, tenant_id, candidate, "has_evidence", run_evidence)
            if object_type == "ValueProposition":
                put_relation(session, tenant_id, candidate, "satisfies_need", need)
    failed = ensure(AgentRunRecord, "RUN-DEMO-BLOCKED", campaign_id="ACT-DEMO-BLOCKED", domain_id="product-match", operator="竞赛运营（预置样例）", provider_id=provider.id, status="failed", summary="阻断：产品尚未审批且库存未核验，不能进入活动执行")
    if not failed.events:
        session.add(RuntimeEventRecord(id="EVT-DEMO-BLOCKED", run_id=failed.id, event_type="governance/guard-checked", payload_json=dump({"accepted": False, "detail": failed.summary})))
    for source_name, focus in [("模拟旅游需求接口", "搜索、酒店、景区与攻略关注聚合证据"), ("模拟航线经营接口", "SHA-SYX客座率62%，可经营窗口；无真实库存结论")]:
        if not session.scalar(select(OpportunityInsightSourceRecord.id).where(OpportunityInsightSourceRecord.tenant_id == tenant_id, OpportunityInsightSourceRecord.name == source_name)):
            session.add(OpportunityInsightSourceRecord(tenant_id=tenant_id, name=source_name, source_type="manual", focus=focus, enabled=True, created_by=user_id))
    ensure(OpportunityInsightRunRecord, "INSIGHT-DEMO-SANYA", operator="竞赛运营", prompt="识别三亚家庭出游机会", status="completed", current_stage="synthesis", source_ids_json="[]", steps_json=dump([{"stage": "multi-agent", "status": "completed", "agent": role, "detail": detail} for role, detail in [("市场信号", "搜索增长32%，酒店与攻略关注共同支撑"), ("航线经营", "模拟客座率62%，需要核验可售库存"), ("产品商业化", "行李与座位满足家庭需求，形成候选产品组合")]]), result_json=dump({"synthetic": True, "opportunity_ids": ["OPP-2026-0921"], "execution": "受控预置样例"}), completed_at=DEMO_TIMESTAMP)
    for key, state, total, accepted, rejected in [("SUCCESS", "completed", 3, 3, 0), ("REPEAT", "completed", 3, 3, 0), ("FAIL", "failed", 1, 0, 1)]:
        ensure(ImportJobRecord, "IMPORT-DEMO-" + key, created_by=user_id, dataset_type="audience", file_name="竞赛接口样例·" + {"SUCCESS": "首次导入", "REPEAT": "重复导入（未变化3条）", "FAIL": "未注册字段校验失败"}[key], file_format="json", status=state, total_rows=total, accepted_rows=accepted, rejected_rows=rejected, errors_json=dump(["未注册字段 demo_unknown"] if rejected else []), completed_at=DEMO_TIMESTAMP)
    ensure(DataPipelineJobRecord, "PIPE-DEMO-RULES", created_by=user_id, file_name="竞赛模拟营销规则.txt", file_format="txt", source_type="competition", status="completed", current_stage="ontology-updated", total_entities=3, accepted_entities=3, total_relations=2, accepted_relations=2, completed_at=DEMO_TIMESTAMP, result_json=dump({"synthetic": True, "source_document": "DOC-DEMO-RULES"}))
    sync_business_graph(session, tenant_id)
    session.commit()
