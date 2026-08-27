"""Business semantic model for the China Eastern marketing ontology.

This registry describes stable business meaning, not a fixed tag dictionary. Tag
values remain configurable and can come from existing source systems, operator
configuration, or agent suggestions.
"""

SEMANTIC_MODEL_VERSION = "ceair-marketing-ontology-v1.1"

OBJECT_TYPES = [
    {"id": "MarketSignal", "name": "市场信号", "description": "来自舆情、搜索热度、节假日和市场趋势的可追溯信号。", "module": "data"},
    {"id": "Market", "name": "市场", "description": "国内、国际及地区、区域和目的地市场。", "module": "aviation"},
    {"id": "Airport", "name": "机场", "description": "起降、中转和地面服务相关的机场对象。", "module": "aviation"},
    {"id": "Route", "name": "航线", "description": "由出发地、目的地和市场范围定义的航线经营对象。", "module": "aviation"},
    {"id": "Flight", "name": "航班", "description": "具体航班、航段、航班计划和运行状态。", "module": "aviation"},
    {"id": "MetricObservation", "name": "经营指标观测", "description": "客座率、正常率、库存、价格和营销指标的带时间观测值。", "module": "aviation"},
    {"id": "Opportunity", "name": "营销机会", "description": "基于事实、信号和规则形成的可经营机会候选或确认机会。", "module": "marketing"},
    {"id": "MarketingObjective", "name": "营销目标", "description": "将航线增收、客座率提升、辅营增长、会员活跃或客户保留转化为可衡量目标。", "module": "marketing"},
    {"id": "CustomerNeed", "name": "客户需求", "description": "客户在搜索、预订、出行和服务阶段需要解决的价格、便捷、确定性、舒适或权益诉求。", "module": "customer"},
    {"id": "CustomerAggregate", "name": "客户聚合", "description": "不暴露个人明细的ToB或ToC聚合客户对象。", "module": "customer"},
    {"id": "ConfigurableAttribute", "name": "可配置业务属性", "description": "可复用源系统标签、运营属性或智能体建议，不预置具体标签值。", "module": "semantic"},
    {"id": "AudienceSnapshot", "name": "客群快照", "description": "用于一次活动的可计算、可触达客群版本。", "module": "customer"},
    {"id": "Product", "name": "活动产品", "description": "机票、运价、联运、辅营、卡券和会员权益等营销可用产品。", "module": "product"},
    {"id": "ProductPackage", "name": "产品包", "description": "可被活动引用的产品和权益组合版本。", "module": "product"},
    {"id": "ValueProposition", "name": "价值主张", "description": "针对目标客群和具体出行需求，说明产品包能够提供的核心利益和差异化理由。", "module": "strategy"},
    {"id": "StrategyPlan", "name": "营销策略方案", "description": "连接机会、目标、客群、价值主张、产品包、预算、节奏和衡量指标的可审批方案。", "module": "strategy"},
    {"id": "TouchpointPlan", "name": "触点计划", "description": "按旅程阶段定义渠道、触发条件、时间窗口、频次和内容版本的执行计划。", "module": "strategy"},
    {"id": "ContentAsset", "name": "营销内容", "description": "面向不同渠道的内容草稿、版本和事实依据。", "module": "marketing"},
    {"id": "MarketingCase", "name": "营销经营事项", "description": "贯穿机会、客群、产品、活动、执行和复盘的业务主线。", "module": "marketing"},
    {"id": "Campaign", "name": "营销活动", "description": "面向执行的营销活动及其业务目标、预算和状态。", "module": "marketing"},
    {"id": "CampaignVersion", "name": "活动版本", "description": "活动方案在客群、产品、内容、渠道或预算变化后的可追溯版本。", "module": "marketing"},
    {"id": "ApprovalTask", "name": "审批任务", "description": "营销运营、预算、产品和合规等多级审批节点。", "module": "governance"},
    {"id": "ExecutionBatch", "name": "执行批次", "description": "按渠道、时间窗口和客群快照生成的触达执行批次。", "module": "execution"},
    {"id": "Channel", "name": "触达渠道", "description": "东航App、微信、短信、官网、企业和分销触点。", "module": "execution"},
    {"id": "Feedback", "name": "营销反馈", "description": "送达、打开、点击、出票、辅营、退订和投诉等反馈。", "module": "execution"},
    {"id": "AttributionResult", "name": "营销归因结果", "description": "将增量出票、辅营收入、会员活跃和服务反馈归因到客群、产品、内容、渠道及策略。", "module": "measurement"},
    {"id": "Review", "name": "效果复盘", "description": "对活动目标、渠道、客群、产品和内容效果的复盘结论。", "module": "marketing"},
    {"id": "Recommendation", "name": "营销建议", "description": "由智能体基于事实和关系生成、等待人工确认的业务建议。", "module": "agent"},
    {"id": "BusinessRule", "name": "业务规则", "description": "MCT、库存、频控、保护、资格、预算和合规规则。", "module": "governance"},
    {"id": "Evidence", "name": "业务证据", "description": "支撑事实、推断、建议和人工决策的来源记录。", "module": "governance"},
    {"id": "HumanDecision", "name": "人工决策", "description": "对智能体建议、活动版本和审批节点的确认、修改或驳回。", "module": "governance"},
    {"id": "AgentRun", "name": "智能体运行", "description": "智能域读取本体、调用函数并产生候选结果的运行记录。", "module": "agent"},
    {"id": "KnowledgeDocument", "name": "知识文档", "description": "经授权接入的航班、运价、产品、营销和运营文档原文。", "module": "knowledge"},
    {"id": "KnowledgeChunk", "name": "知识片段", "description": "文档切分后的可检索片段，保留页码、段落和来源定位。", "module": "knowledge"},
    {"id": "KnowledgeClaim", "name": "知识事实", "description": "从文档或数据中提取的待核验事实，连接原文证据与本体对象。", "module": "knowledge"},
]

RELATION_TYPES = [
    {"id": "derived_from", "name": "来源于", "from_types": ["MarketSignal", "MetricObservation", "Opportunity", "Recommendation", "MarketingCase"], "to_types": ["Evidence", "MarketSignal", "MetricObservation", "Review"]},
    {"id": "concerns_route", "name": "涉及航线", "from_types": ["MarketSignal", "Opportunity", "Campaign", "MarketingCase"], "to_types": ["Route"]},
    {"id": "concerns_flight", "name": "涉及航班", "from_types": ["Opportunity", "Campaign", "MarketingCase"], "to_types": ["Flight"]},
    {"id": "has_metric", "name": "具有指标", "from_types": ["Route", "Flight", "Campaign", "ExecutionBatch", "ProductPackage"], "to_types": ["MetricObservation"]},
    {"id": "identifies", "name": "识别出", "from_types": ["AgentRun", "MarketingCase"], "to_types": ["Opportunity", "Recommendation"]},
    {"id": "targets_audience", "name": "面向客群", "from_types": ["Opportunity", "Campaign", "MarketingCase", "ProductPackage", "StrategyPlan"], "to_types": ["AudienceSnapshot", "CustomerAggregate"]},
    {"id": "reveals_need", "name": "揭示需求", "from_types": ["Opportunity", "AudienceSnapshot", "CustomerAggregate"], "to_types": ["CustomerNeed"]},
    {"id": "pursues_objective", "name": "承接目标", "from_types": ["MarketingCase", "Campaign", "StrategyPlan"], "to_types": ["MarketingObjective"]},
    {"id": "uses_product_package", "name": "使用产品包", "from_types": ["Campaign", "MarketingCase", "AudienceSnapshot", "StrategyPlan"], "to_types": ["ProductPackage"]},
    {"id": "contains_product", "name": "包含产品", "from_types": ["ProductPackage"], "to_types": ["Product"]},
    {"id": "addresses_opportunity", "name": "响应机会", "from_types": ["Campaign", "MarketingCase", "ProductPackage", "StrategyPlan"], "to_types": ["Opportunity"]},
    {"id": "satisfies_need", "name": "满足需求", "from_types": ["ValueProposition", "ProductPackage"], "to_types": ["CustomerNeed"]},
    {"id": "defines_value", "name": "定义价值主张", "from_types": ["StrategyPlan", "CampaignVersion"], "to_types": ["ValueProposition"]},
    {"id": "has_strategy_plan", "name": "包含策略方案", "from_types": ["MarketingCase", "Campaign"], "to_types": ["StrategyPlan"]},
    {"id": "uses_touchpoint_plan", "name": "使用触点计划", "from_types": ["StrategyPlan", "CampaignVersion"], "to_types": ["TouchpointPlan"]},
    {"id": "generates_content", "name": "生成内容", "from_types": ["CampaignVersion", "AgentRun", "MarketingCase"], "to_types": ["ContentAsset"]},
    {"id": "has_campaign_version", "name": "包含活动版本", "from_types": ["Campaign", "MarketingCase"], "to_types": ["CampaignVersion"]},
    {"id": "requires_approval", "name": "需要审批", "from_types": ["CampaignVersion", "Campaign"], "to_types": ["ApprovalTask"]},
    {"id": "executes", "name": "产生执行", "from_types": ["Campaign", "CampaignVersion", "MarketingCase"], "to_types": ["ExecutionBatch"]},
    {"id": "uses_channel", "name": "使用渠道", "from_types": ["ExecutionBatch", "CampaignVersion", "TouchpointPlan"], "to_types": ["Channel"]},
    {"id": "carries_content", "name": "承载内容", "from_types": ["TouchpointPlan", "ExecutionBatch"], "to_types": ["ContentAsset"]},
    {"id": "produces_feedback", "name": "产生反馈", "from_types": ["ExecutionBatch", "Campaign"], "to_types": ["Feedback"]},
    {"id": "produces_attribution", "name": "形成归因", "from_types": ["Campaign", "ExecutionBatch", "StrategyPlan"], "to_types": ["AttributionResult"]},
    {"id": "attributes_to", "name": "归因到", "from_types": ["AttributionResult"], "to_types": ["Campaign", "StrategyPlan", "AudienceSnapshot", "ProductPackage", "ContentAsset", "Channel"]},
    {"id": "reviewed_by", "name": "由复盘形成", "from_types": ["Campaign", "MarketingCase", "AttributionResult"], "to_types": ["Review"]},
    {"id": "generates_recommendation", "name": "形成建议", "from_types": ["Review", "AgentRun"], "to_types": ["Recommendation"]},
    {"id": "updates_rule", "name": "更新规则建议", "from_types": ["Review", "Recommendation"], "to_types": ["BusinessRule"]},
    {"id": "confirmed_by_human", "name": "经人工确认", "from_types": ["Recommendation", "Opportunity", "CampaignVersion", "AudienceSnapshot"], "to_types": ["HumanDecision"]},
    {"id": "has_evidence", "name": "具有证据", "from_types": ["Opportunity", "Recommendation", "HumanDecision", "MetricObservation"], "to_types": ["Evidence"]},
    {"id": "has_tag_attribute", "name": "具有可配置属性", "from_types": ["CustomerAggregate", "AudienceSnapshot", "Route", "Flight", "Product", "ProductPackage", "Campaign"], "to_types": ["ConfigurableAttribute"]},
    {"id": "contains_chunk", "name": "包含片段", "from_types": ["KnowledgeDocument"], "to_types": ["KnowledgeChunk"]},
    {"id": "supports_claim", "name": "支撑事实", "from_types": ["KnowledgeChunk", "Evidence"], "to_types": ["KnowledgeClaim", "Opportunity", "Recommendation", "BusinessRule"]},
    {"id": "evidence_for", "name": "提供业务证据", "from_types": ["KnowledgeChunk", "Evidence"], "to_types": ["Evidence", "MarketSignal", "Market", "Airport", "Route", "Flight", "MetricObservation", "Opportunity", "MarketingObjective", "CustomerNeed", "CustomerAggregate", "AudienceSnapshot", "Product", "ProductPackage", "ValueProposition", "StrategyPlan", "TouchpointPlan", "ContentAsset", "MarketingCase", "Campaign", "CampaignVersion", "ApprovalTask", "ExecutionBatch", "Feedback", "AttributionResult", "Review", "Recommendation", "BusinessRule"]},
    {"id": "claims_about", "name": "描述对象", "from_types": ["KnowledgeClaim"], "to_types": ["Market", "Airport", "Route", "Flight", "MetricObservation", "Product", "ProductPackage", "BusinessRule", "Opportunity", "MarketingObjective", "CustomerNeed", "ValueProposition", "StrategyPlan", "TouchpointPlan", "AttributionResult"]},
]

ACTIONS = [
    {"id": "confirm_opportunity", "name": "确认营销机会", "requires": ["Opportunity", "Evidence"], "changes": ["Opportunity.status", "HumanDecision"]},
    {"id": "set_marketing_objective", "name": "设定营销目标", "requires": ["Opportunity", "MetricObservation"], "changes": ["MarketingObjective", "HumanDecision"]},
    {"id": "create_audience_snapshot", "name": "创建客群快照", "requires": ["CustomerAggregate"], "changes": ["AudienceSnapshot"]},
    {"id": "accept_product_match", "name": "确认产品匹配", "requires": ["AudienceSnapshot", "ProductPackage"], "changes": ["Recommendation.status", "HumanDecision"]},
    {"id": "approve_strategy_plan", "name": "确认营销策略方案", "requires": ["MarketingObjective", "AudienceSnapshot", "ValueProposition", "ProductPackage"], "changes": ["StrategyPlan.status", "HumanDecision"]},
    {"id": "publish_touchpoint_plan", "name": "发布触点计划", "requires": ["StrategyPlan", "BusinessRule"], "changes": ["TouchpointPlan.status"]},
    {"id": "generate_content_draft", "name": "生成内容草稿", "requires": ["CampaignVersion", "ProductPackage", "AudienceSnapshot"], "changes": ["ContentAsset"]},
    {"id": "submit_campaign_approval", "name": "提交活动审批", "requires": ["CampaignVersion", "ContentAsset"], "changes": ["ApprovalTask.status"]},
    {"id": "approve_campaign", "name": "审批活动版本", "requires": ["ApprovalTask", "Evidence"], "changes": ["CampaignVersion.status", "HumanDecision"]},
    {"id": "schedule_execution", "name": "安排渠道执行", "requires": ["CampaignVersion", "AudienceSnapshot"], "changes": ["ExecutionBatch"]},
    {"id": "pause_execution", "name": "暂停触达执行", "requires": ["ExecutionBatch"], "changes": ["ExecutionBatch.status"]},
    {"id": "complete_review", "name": "完成效果复盘", "requires": ["Campaign", "Feedback"], "changes": ["Review.status", "Recommendation"]},
    {"id": "confirm_attribution", "name": "确认营销归因", "requires": ["AttributionResult", "Evidence"], "changes": ["AttributionResult.status", "HumanDecision"]},
    {"id": "accept_agent_recommendation", "name": "采纳智能体建议", "requires": ["Recommendation", "Evidence"], "changes": ["HumanDecision", "BusinessRule"]},
]

FUNCTIONS = [
    {"id": "calculate_opportunity_score", "name": "计算机会评分", "reads": ["MarketSignal", "MetricObservation", "Route", "Review"], "returns": "Opportunity"},
    {"id": "evaluate_target_attractiveness", "name": "评估目标客群吸引力", "reads": ["CustomerAggregate", "CustomerNeed", "MetricObservation", "Review"], "returns": "Recommendation"},
    {"id": "calculate_customer_value", "name": "计算客户长期价值", "reads": ["CustomerAggregate", "Feedback", "MetricObservation"], "returns": "MetricObservation"},
    {"id": "compose_value_proposition", "name": "生成价值主张", "reads": ["CustomerNeed", "AudienceSnapshot", "ProductPackage", "Opportunity"], "returns": "ValueProposition"},
    {"id": "calculate_audience_size", "name": "计算客群规模", "reads": ["CustomerAggregate", "AudienceSnapshot"], "returns": "MetricObservation"},
    {"id": "evaluate_product_eligibility", "name": "校验产品资格", "reads": ["AudienceSnapshot", "ProductPackage", "BusinessRule"], "returns": "Recommendation"},
    {"id": "validate_connection_time", "name": "校验中转衔接时间", "reads": ["Flight", "Airport", "BusinessRule"], "returns": "Recommendation"},
    {"id": "check_contact_frequency", "name": "校验触达频控", "reads": ["AudienceSnapshot", "ExecutionBatch", "BusinessRule"], "returns": "Recommendation"},
    {"id": "optimize_touchpoint_mix", "name": "优化触点组合", "reads": ["StrategyPlan", "TouchpointPlan", "Channel", "Feedback", "BusinessRule"], "returns": "Recommendation"},
    {"id": "check_content_facts", "name": "校验内容事实", "reads": ["ContentAsset", "ProductPackage", "BusinessRule"], "returns": "Recommendation"},
    {"id": "calculate_campaign_effect", "name": "计算活动效果", "reads": ["Campaign", "ExecutionBatch", "Feedback", "MetricObservation"], "returns": "Review"},
    {"id": "calculate_incremental_effect", "name": "计算增量效果与归因", "reads": ["StrategyPlan", "Campaign", "ExecutionBatch", "Feedback", "MetricObservation"], "returns": "AttributionResult"},
    {"id": "detect_business_anomaly", "name": "识别经营异常", "reads": ["MetricObservation", "Route", "Flight", "Review"], "returns": "Recommendation"},
]


AGENT_CONTRACTS = {
    "opportunity-insight": {
        "reads": ["MarketSignal", "MetricObservation", "Route", "Flight", "Review", "BusinessRule", "KnowledgeChunk", "KnowledgeClaim"],
        "writes": ["Opportunity", "MarketingObjective", "CustomerNeed", "Recommendation", "Evidence"],
        "functions": ["calculate_opportunity_score", "detect_business_anomaly"],
    },
    "audience-insight": {
        "reads": ["CustomerAggregate", "CustomerNeed", "ConfigurableAttribute", "Feedback", "MetricObservation", "HumanDecision", "KnowledgeChunk", "KnowledgeClaim"],
        "writes": ["AudienceSnapshot", "Recommendation", "Evidence"],
        "functions": ["calculate_audience_size", "evaluate_target_attractiveness", "calculate_customer_value", "check_contact_frequency"],
    },
    "product-match": {
        "reads": ["Opportunity", "CustomerNeed", "AudienceSnapshot", "Product", "ProductPackage", "ValueProposition", "Flight", "BusinessRule", "KnowledgeChunk", "KnowledgeClaim"],
        "writes": ["ValueProposition", "Recommendation", "Evidence"],
        "functions": ["compose_value_proposition", "evaluate_product_eligibility", "validate_connection_time"],
    },
    "activity-orchestration": {
        "reads": ["Opportunity", "MarketingObjective", "CustomerNeed", "AudienceSnapshot", "ValueProposition", "ProductPackage", "BusinessRule", "HumanDecision", "KnowledgeChunk", "KnowledgeClaim"],
        "writes": ["MarketingCase", "StrategyPlan", "TouchpointPlan", "Campaign", "CampaignVersion", "ExecutionBatch", "Recommendation"],
        "functions": ["optimize_touchpoint_mix", "check_contact_frequency"],
    },
    "content-generation": {
        "reads": ["CustomerNeed", "AudienceSnapshot", "ValueProposition", "ProductPackage", "StrategyPlan", "TouchpointPlan", "CampaignVersion", "BusinessRule", "KnowledgeChunk", "KnowledgeClaim"],
        "writes": ["ContentAsset", "Recommendation", "Evidence"],
        "functions": ["check_content_facts"],
    },
    "effect-analysis": {
        "reads": ["MarketingObjective", "StrategyPlan", "TouchpointPlan", "Campaign", "ExecutionBatch", "Feedback", "AttributionResult", "MetricObservation", "HumanDecision", "KnowledgeChunk", "KnowledgeClaim"],
        "writes": ["AttributionResult", "Review", "Recommendation", "Evidence"],
        "functions": ["calculate_incremental_effect", "calculate_campaign_effect", "detect_business_anomaly"],
    },
}


def object_type_ids() -> set[str]:
    return {item["id"] for item in OBJECT_TYPES}


def relation_type_ids() -> set[str]:
    return {item["id"] for item in RELATION_TYPES}


def relation_type_definition(relation_type: str) -> dict | None:
    return next((item for item in RELATION_TYPES if item["id"] == relation_type), None)


def validate_relation_endpoints(relation_type: str, source_type: str, target_type: str) -> str | None:
    """Validate registered relations while allowing tenant-defined extensions."""
    definition = relation_type_definition(relation_type)
    if definition is None:
        return None
    if source_type not in definition["from_types"]:
        allowed = ", ".join(definition["from_types"])
        return f"Relation {relation_type} requires source type in [{allowed}], got {source_type}"
    if target_type not in definition["to_types"]:
        allowed = ", ".join(definition["to_types"])
        return f"Relation {relation_type} requires target type in [{allowed}], got {target_type}"
    return None


def agent_contract(domain_id: str) -> dict:
    return AGENT_CONTRACTS.get(domain_id, {"reads": [], "writes": [], "functions": []})


def semantic_model() -> dict:
    return {
        "version": SEMANTIC_MODEL_VERSION,
        "principles": [
            "本体建模真实航空营销业务对象，不复制源系统表结构。",
            "标签作为对象的可配置业务属性，可复用已有系统标签，也可由运营或智能体产生。",
            "智能体输出先形成候选事实、推断或建议，人工通过业务动作确认后再进入正式流程。",
            "每个判断保留来源、证据、置信度、有效期、版本和人工决策状态。",
            "知识文档和本体图谱共同构成知识底座：文档保存可追溯内容，本体表达可计算关系。",
        ],
        "lifecycle": ["data", "opportunity", "objective", "audience", "value", "product", "strategy", "content", "approval", "execution", "feedback", "attribution", "review"],
        "object_types": OBJECT_TYPES,
        "relation_types": RELATION_TYPES,
        "actions": ACTIONS,
        "functions": FUNCTIONS,
        "agent_contracts": AGENT_CONTRACTS,
    }
