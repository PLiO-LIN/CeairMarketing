from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import OntologyEntityRecord, OntologyRelationRecord


LIFECYCLE_ENTITIES = [
    ("case-sanya-2026", "MarketingCase", "2026国庆上海—三亚增量经营事项", {"status": "active", "owner": "华东营销运营中心"}, "营销活动平台", 1.0),
    ("signal-sanya-social", "MarketSignal", "三亚目的地热度上升", {"signal_type": "social_trend", "markets": ["小红书", "抖音"]}, "市场数据接入智能体", 0.88),
    ("route-sha-syx", "Route", "上海—三亚航线", {"origin": "SHA", "destination": "SYX", "market": "国内"}, "航班运行平台", 1.0),
    ("metric-sha-syx-load-factor", "MetricObservation", "上海—三亚客座率观测", {"metric": "load_factor", "window": "departure_minus_15_days", "value": 0.62}, "经营数据平台", 0.99),
    ("opp-sanya", "Opportunity", "三亚国庆早鸟机会", {"window": "国庆前15天", "status": "human_confirmed", "score": 0.94}, "机会洞察智能域", 0.94),
    ("objective-sanya", "MarketingObjective", "提升上海—三亚航线增量收入", {"objective_type": "revenue_and_load_factor", "target_load_factor": 0.78, "target_ancillary_revenue_yuan": 480000}, "营销运营中心", 1.0),
    ("need-sanya-family", "CustomerNeed", "家庭旅客高性价比与省心出行需求", {"journey_stage": "搜索未购", "benefits": ["价格吸引力", "行李便利", "座位确定性"]}, "客群洞察智能域", 0.91),
    ("aud-sanya-v4", "AudienceSnapshot", "三亚高意向未购客群快照V4", {"size": 36420, "privacy": "aggregate_only", "tag_source_mode": "existing_profile_api_and_configurable"}, "用户画像平台", 0.96),
    ("product-sanya-ticket", "Product", "上海—三亚早鸟客票", {"category": "ticket", "delivery_mode": "ticketing"}, "产品管理平台", 1.0),
    ("product-sanya-baggage", "Product", "额外行李权益", {"category": "ancillary", "delivery_mode": "entitlement"}, "产品管理平台", 1.0),
    ("product-sanya-coupon", "Product", "目的地优惠券", {"category": "coupon", "delivery_mode": "coupon_issue"}, "产品管理平台", 1.0),
    ("pkg-sanya", "ProductPackage", "三亚国庆早鸟产品包", {"version": "V2", "status": "approved"}, "产品管理平台", 1.0),
    ("value-sanya-family", "ValueProposition", "一站式家庭早鸟出行更省心", {"functional_benefit": "客票与行李座位一次配置", "economic_benefit": "早鸟价格与权益组合", "reason_to_believe": "产品管理平台已审批产品包"}, "产品匹配智能域", 0.92),
    ("strategy-sanya-v3", "StrategyPlan", "三亚早鸟家庭客群策略方案V3", {"status": "approved", "budget_yuan": 320000, "kpis": ["增量出票", "辅营收入", "触达退订率"]}, "活动编排智能域", 0.95),
    ("touchpoint-sanya-app", "TouchpointPlan", "三亚早鸟App触点计划", {"journey_stage": "搜索未购", "trigger": "连续搜索未出票", "send_window": "19:00-21:00", "frequency_cap": "7天1次"}, "活动编排智能域", 0.95),
    ("ACT-2026-0921", "Campaign", "上海—三亚国庆早鸟", {"status": "planning", "current_version": "V3"}, "营销活动平台", 1.0),
    ("ACT-2026-0921-v3", "CampaignVersion", "上海—三亚国庆早鸟V3", {"status": "pending_compliance", "budget_yuan": 320000}, "营销活动平台", 1.0),
    ("content-app-v3", "ContentAsset", "东航App家庭出游内容V3", {"channel": "App", "status": "approved"}, "内容生成智能域", 0.98),
    ("approval-ACT-2026-0921-compliance", "ApprovalTask", "上海—三亚国庆早鸟合规审批", {"level": "compliance", "status": "pending"}, "审批中心", 1.0),
    ("channel-ceair-app", "Channel", "东航App", {"touchpoint": "B2C官方触点"}, "渠道平台", 1.0),
    ("exec-ACT-2026-0921-app", "ExecutionBatch", "上海—三亚国庆早鸟App执行批次", {"status": "scheduled", "channel": "App"}, "活动执行中心", 1.0),
    ("feedback-ACT-2026-0921", "Feedback", "上海—三亚国庆早鸟执行反馈", {"delivery_rate": 0.967, "ticket_count": 3572, "ancillary_orders": 1268}, "渠道与交易回传", 0.98),
    ("attribution-ACT-2026-0921", "AttributionResult", "上海—三亚国庆早鸟增量归因", {"status": "human_confirmed", "incremental_ticket_count": 1184, "incremental_revenue_yuan": 1368000, "attribution_window_days": 7}, "效果分析智能域", 0.89),
    ("review-ACT-2026-0921", "Review", "上海—三亚国庆早鸟复盘", {"roi": 4.3, "status": "draft"}, "效果分析智能域", 0.91),
    ("recommendation-ACT-2026-0921", "Recommendation", "扩大行李偏好子群并延后补触", {"status": "pending_human_review", "recommendation_type": "next_cycle_strategy"}, "效果分析智能域", 0.86),
    ("evidence-sanya-opportunity", "Evidence", "市场热度与客座率联合证据", {"sources": ["市场数据", "航班数据", "经营数据"]}, "数据接入智能体", 0.94),
]

LIFECYCLE_RELATIONS = [
    ("case-sanya-2026", "derived_from", "signal-sanya-social", "经营事项由市场信号触发", 0.88),
    ("case-sanya-2026", "concerns_route", "route-sha-syx", "经营事项对应上海—三亚航线", 1.0),
    ("route-sha-syx", "has_metric", "metric-sha-syx-load-factor", "航线客座率观测", 0.99),
    ("opp-sanya", "has_evidence", "evidence-sanya-opportunity", "机会由市场、航班和经营数据共同支撑", 0.94),
    ("opp-sanya", "concerns_route", "route-sha-syx", "机会涉及上海—三亚航线", 1.0),
    ("opp-sanya", "reveals_need", "need-sanya-family", "搜索未购与家庭出行行为揭示省心出行需求", 0.91),
    ("case-sanya-2026", "pursues_objective", "objective-sanya", "经营事项承接航线增收目标", 1.0),
    ("opp-sanya", "targets_audience", "aud-sanya-v4", "机会面向高意向未购客群快照", 0.96),
    ("aud-sanya-v4", "reveals_need", "need-sanya-family", "客群画像与旅程阶段支撑需求判断", 0.91),
    ("aud-sanya-v4", "uses_product_package", "pkg-sanya", "客群与产品包匹配", 0.916),
    ("pkg-sanya", "contains_product", "product-sanya-ticket", "产品包包含客票产品", 1.0),
    ("pkg-sanya", "contains_product", "product-sanya-baggage", "产品包包含辅营权益", 1.0),
    ("pkg-sanya", "contains_product", "product-sanya-coupon", "产品包包含目的地卡券", 1.0),
    ("pkg-sanya", "satisfies_need", "need-sanya-family", "客票、行李和座位权益满足家庭省心出行需求", 0.92),
    ("value-sanya-family", "satisfies_need", "need-sanya-family", "价值主张明确对应客户需求", 0.92),
    ("case-sanya-2026", "has_strategy_plan", "strategy-sanya-v3", "经营事项形成可审批策略方案", 1.0),
    ("strategy-sanya-v3", "addresses_opportunity", "opp-sanya", "策略方案响应已确认营销机会", 1.0),
    ("strategy-sanya-v3", "pursues_objective", "objective-sanya", "策略方案以增量收入和客座率为目标", 1.0),
    ("strategy-sanya-v3", "targets_audience", "aud-sanya-v4", "策略方案锁定客群快照V4", 1.0),
    ("strategy-sanya-v3", "uses_product_package", "pkg-sanya", "策略方案引用已审批产品包", 1.0),
    ("strategy-sanya-v3", "defines_value", "value-sanya-family", "策略方案定义家庭旅客价值主张", 0.95),
    ("strategy-sanya-v3", "uses_touchpoint_plan", "touchpoint-sanya-app", "策略方案包含App触点计划", 1.0),
    ("ACT-2026-0921", "addresses_opportunity", "opp-sanya", "活动响应营销机会", 1.0),
    ("ACT-2026-0921", "pursues_objective", "objective-sanya", "活动承接增量经营目标", 1.0),
    ("ACT-2026-0921", "has_strategy_plan", "strategy-sanya-v3", "活动执行策略方案V3", 1.0),
    ("ACT-2026-0921", "targets_audience", "aud-sanya-v4", "活动引用客群快照V4", 1.0),
    ("ACT-2026-0921", "uses_product_package", "pkg-sanya", "活动引用产品包", 1.0),
    ("ACT-2026-0921", "has_campaign_version", "ACT-2026-0921-v3", "当前执行方案版本", 1.0),
    ("ACT-2026-0921-v3", "generates_content", "content-app-v3", "活动版本生成渠道内容", 0.98),
    ("ACT-2026-0921-v3", "defines_value", "value-sanya-family", "活动版本使用已确认价值主张", 0.95),
    ("ACT-2026-0921-v3", "uses_touchpoint_plan", "touchpoint-sanya-app", "活动版本绑定App触点计划", 1.0),
    ("touchpoint-sanya-app", "uses_channel", "channel-ceair-app", "触点计划选择东航App", 1.0),
    ("touchpoint-sanya-app", "carries_content", "content-app-v3", "触点计划承载家庭出游内容V3", 0.98),
    ("ACT-2026-0921-v3", "requires_approval", "approval-ACT-2026-0921-compliance", "活动发布前需要合规审批", 1.0),
    ("ACT-2026-0921-v3", "executes", "exec-ACT-2026-0921-app", "审批通过后生成执行批次", 1.0),
    ("exec-ACT-2026-0921-app", "uses_channel", "channel-ceair-app", "通过东航App执行触达", 1.0),
    ("exec-ACT-2026-0921-app", "produces_feedback", "feedback-ACT-2026-0921", "渠道、交易和履约结果回传", 0.98),
    ("exec-ACT-2026-0921-app", "produces_attribution", "attribution-ACT-2026-0921", "执行反馈进入增量效果归因", 0.89),
    ("attribution-ACT-2026-0921", "attributes_to", "strategy-sanya-v3", "增量效果归因到策略方案V3", 0.89),
    ("attribution-ACT-2026-0921", "attributes_to", "aud-sanya-v4", "增量效果归因到客群快照V4", 0.86),
    ("attribution-ACT-2026-0921", "attributes_to", "pkg-sanya", "增量效果归因到产品包V2", 0.87),
    ("attribution-ACT-2026-0921", "attributes_to", "content-app-v3", "增量效果归因到内容版本V3", 0.84),
    ("attribution-ACT-2026-0921", "attributes_to", "channel-ceair-app", "增量效果归因到东航App渠道", 0.9),
    ("attribution-ACT-2026-0921", "reviewed_by", "review-ACT-2026-0921", "归因结果形成活动复盘输入", 0.91),
    ("ACT-2026-0921", "reviewed_by", "review-ACT-2026-0921", "活动结果进入效果复盘", 0.91),
    ("review-ACT-2026-0921", "generates_recommendation", "recommendation-ACT-2026-0921", "复盘形成下一轮策略建议", 0.86),
]


def seed_marketing_lifecycle(session: Session, tenant_id: int) -> None:
    records: dict[str, OntologyEntityRecord] = {}
    for external_id, entity_type, label, attributes, source, confidence in LIFECYCLE_ENTITIES:
        record = session.scalar(
            select(OntologyEntityRecord).where(
                OntologyEntityRecord.tenant_id == tenant_id,
                OntologyEntityRecord.external_id == external_id,
            )
        )
        if record is None:
            record = OntologyEntityRecord(
                tenant_id=tenant_id,
                external_id=external_id,
                entity_type=entity_type,
                label=label,
                attributes_json=json.dumps(attributes, ensure_ascii=False),
                source=source,
                confidence=confidence,
            )
            session.add(record)
            session.flush()
        records[external_id] = record

    required_ids = {item for relation in LIFECYCLE_RELATIONS for item in (relation[0], relation[2])}
    missing_ids = required_ids - records.keys()
    if missing_ids:
        existing = session.scalars(
            select(OntologyEntityRecord).where(
                OntologyEntityRecord.tenant_id == tenant_id,
                OntologyEntityRecord.external_id.in_(missing_ids),
            )
        )
        records.update({item.external_id: item for item in existing})

    for source_id, relation_type, target_id, evidence, confidence in LIFECYCLE_RELATIONS:
        source = records.get(source_id)
        target = records.get(target_id)
        if source is None or target is None:
            continue
        existing_relation = session.scalar(
            select(OntologyRelationRecord.id).where(
                OntologyRelationRecord.tenant_id == tenant_id,
                OntologyRelationRecord.source_entity_id == source.id,
                OntologyRelationRecord.relation_type == relation_type,
                OntologyRelationRecord.target_entity_id == target.id,
            )
        )
        if existing_relation is None:
            session.add(
                OntologyRelationRecord(
                    tenant_id=tenant_id,
                    source_entity_id=source.id,
                    relation_type=relation_type,
                    target_entity_id=target.id,
                    evidence=evidence,
                    source="本体初始化",
                    confidence=confidence,
                )
            )
    session.commit()
