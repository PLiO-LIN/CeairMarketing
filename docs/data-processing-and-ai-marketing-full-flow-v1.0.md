# China Eastern Data Processing and AI Marketing Full Flow v1.0

> Review document for the complete flow from data ingestion to ontology enrichment, agent execution, campaign approval, channel delivery, feedback and strategy learning. The Chinese business definitions below are copied from existing UTF-8 repository documents without transformation.

## 1. Review Scope

This document is a review baseline. It separates current implementation from partial implementation and recommended production work. Operators should drop business files or use approved connectors; they should not manually maintain ontology entities and relations.

## 2. Target End-to-end Flow

~~~text
Documents / APIs / Databases
  -> Unified ingestion
  -> Parsing, OCR, tables and structure recognition
  -> Cleaning, deduplication, standardization and quality checks
  -> Data Processing Agent
  -> Objects, relations, evidence and confidence
  -> Knowledge base + Ontology graph
  -> Six marketing agent domains
  -> Human review, compliance, campaign execution and callbacks
  -> Attribution, review and strategy learning
~~~

## 3. Current Implementation Assessment

### Implemented

- Multi-tenant access and tenant-scoped queries.
- Drag-and-drop multi-file ingestion UI with task queue and progress polling.
- Pipeline creation, list query and single-job query.
- Basic text, CSV and JSON handling.
- MinerU configuration with encrypted server-side key storage.
- Knowledge documents, chunks, ontology objects and relations.
- Data Processing Agent and shared Harness for context, tools, models, events and usage.
- Six agent-domain contracts with reads, writes and business functions.

### Partially Implemented

- Background processing still depends on the application process; durable queues and workers are not present.
- Progress is stage-based rather than item-level parser/model progress.
- Candidate persistence exists, but object/relation/evidence review and conflict resolution need a dedicated workbench.
- Not every marketing domain writes a complete business object chain back to the ontology.
- Real channel callbacks, transaction reconciliation and API/database connectors still need integration.

### Recommended Production Work

- Durable raw-file storage, virus scanning, hash deduplication, retention and ZIP parent/child batches.
- API/database connectors with read-only credentials, mapping, incremental sync and quality rules.
- Candidate review, ontology versioning, effective dates, conflict detection, merge and decision history.
- Campaign state machine, approval nodes, compliance execution, rollback and idempotent channel commands.
- App, SMS, WeChat, website, enterprise, OTA and NDC callbacks.
- Ticketing, refund, coupon, ancillary, fulfillment, complaint and revenue attribution.
- Agent evaluation sets, model/prompt versioning, quality scoring, cost controls and feedback learning.

## 4. Decisions Required

1. Which extracted objects may be auto-confirmed and which must wait for human review?
2. What versioned interfaces are available from the product management platform?
3. Does the profile platform return passenger-level data, aggregate audiences or label metrics?
4. Can external data become ontology instances, or only signals and evidence?
5. Does approval remain in OA or become a marketing-platform workflow?
6. Are channel, ticketing, coupon, ancillary and fulfillment callbacks available as one event contract?
7. What evidence must an operator see before approving content, product matching or attribution?
8. Is application background processing acceptable for phase one, or is a durable worker required immediately?


# 东航数据处理与知识底座 v1.0

## 定位

知识库和本体图谱共同组成平台知识底座。知识库保存文档原文、解析结果和可检索片段；本体保存市场、航线、航班、客户聚合、标签属性、产品、产品包、机会、活动、审批、执行、反馈和复盘等业务对象，以及对象之间可计算、可追溯的关系。两者通过知识文档、知识片段、知识事实和业务证据关联。

## 数据流水线

数据进入平台后按以下阶段处理：

1. 接收并记录租户、来源、文件类型、哈希和提交人。
2. 文本、CSV、JSON、Markdown 直接结构化；PDF、Office、图片等文档调用 MinerU 解析。
3. 文档写入知识文档，按内容位置切分为知识片段，保留来源和版本。
4. 数据处理智能体通过统一 Harness 读取原始文本、知识底座语义和允许的本体类型，抽取对象、候选事实、关系、证据和置信度。
5. 对抽取结果执行对象类型、关系端点、置信度和租户边界校验。
6. 合格结果以候选状态更新本体，保留来源、证据和处理批次；需要业务确认的结果不直接改变正式业务决策。
7. 六个智能域读取知识片段和本体关系，为机会识别、客群洞察、产品匹配、活动编排、内容生成和效果分析提供依据。

## 运行方式

数据处理智能体和六个营销智能域使用同一套 `app/agents/harness.py`。Harness 统一管理语义上下文、工具调用、模型调用、JSON 结构化输出、事件记录和失败回退。模型通过租户管理员配置的 OpenAI-compatible Provider 接入；没有可用模型时，数据处理流水线只执行受控的启发式兜底，不伪造业务事实。

## 管理接口

- `PUT /api/integrations/mineru`：管理员配置 MinerU 地址、API Key 和解析选项。
- `POST /api/data-pipelines`：上传数据文件并执行流水线。
- `GET /api/data-pipelines`：查看处理批次、阶段和落库统计。
- `GET /api/knowledge/search?q=...`：按关键词检索知识片段并返回关联本体对象。
- `GET /api/ontology/semantic-model`：查看本体语义契约。
- `GET /api/ontology/status`：查看租户本体对象、关系和扩展统计。

API Key 只保存为服务端加密值，响应只返回是否已配置，不返回密钥内容。文档解析和数据抽取均按租户隔离。

# 航司营销业务本体 v1.1

## 建设目标

本体不是标签字典，也不是把营销教材章节复制进知识库。它用于统一表达东航营销活动中可识别、可审批、可执行、可度量的业务对象，并让六个智能域在同一条业务主线上协同。

核心业务链为：

`经营信号 -> 营销机会 -> 客户需求 -> 营销目标 -> 客群快照 -> 价值主张 -> 产品包 -> 策略方案 -> 触点计划 -> 内容与活动 -> 审批 -> 执行 -> 反馈 -> 归因 -> 复盘学习`

## 营销管理方法映射

本版本参考《营销管理（第16版）》中以下方法，并将其转译为平台对象：

| 营销方法 | 平台本体对象 | 东航业务含义 |
| --- | --- | --- |
| G-STIC营销计划与控制 | `MarketingObjective`、`StrategyPlan`、`TouchpointPlan`、`AttributionResult` | 从目标设定、策略形成、战术执行到效果控制形成闭环 |
| 目标市场选择与细分 | `CustomerAggregate`、`CustomerNeed`、`AudienceSnapshot` | 使用聚合画像、旅程阶段和需求形成活动客群快照，不暴露旅客明细 |
| 顾客价值主张与定位 | `ValueProposition` | 说明特定客群为什么选择该产品包，以及差异化利益和事实依据 |
| 产品与服务组合 | `Product`、`ProductPackage` | 组合客票、运价、联运、辅营、卡券和会员权益 |
| 整合营销沟通 | `TouchpointPlan`、`ContentAsset`、`Channel` | 按旅程阶段统一触发条件、渠道、内容版本、时间窗口和频控 |
| 多渠道管理 | `Channel`、`ExecutionBatch`、`Feedback` | 协调App、微信、短信、官网、企业及分销渠道的执行与回传 |
| 获客、保留、忠诚和终身价值 | `MarketingObjective`、`MetricObservation`、`Review` | 同时衡量短期转化、会员活跃、客户保留和长期价值 |
| 营销绩效控制 | `AttributionResult`、`Review`、`BusinessRule` | 将增量效果归因到客群、产品、内容、渠道和策略，形成下一轮规则建议 |

参考材料位于：

- `竞赛/05_参考工程/营销管理/营销管理第16版_02_0101-0200页.../full.md`：营销计划、目标、战略、战术、执行与控制。
- `竞赛/05_参考工程/营销管理/营销管理第16版_04_0301-0400页.../full.md`：细分市场、目标客户、价值主张与定位。
- `竞赛/05_参考工程/营销管理/营销管理第16版_05_0401-0500页.../full.md`：产品组合、产品线及服务设计。
- `竞赛/05_参考工程/营销管理/营销管理第16版_07_0601-0700页.../full.md`：价格、促销和营销沟通。
- `竞赛/05_参考工程/营销管理/营销管理第16版_08_0701-0800页.../full.md`：数字时代的整合营销与直接营销。
- `竞赛/05_参考工程/营销管理/营销管理第16版_09_0801-0900页.../full.md`：多渠道、渠道合作与渠道评价。
- `竞赛/05_参考工程/营销管理/营销管理第16版_11_1001-1100页.../full.md`：获客、保留、忠诚、客户关系与顾客终身价值。

## 六智能域职责

### 机会洞察智能域

读取市场热度、搜索趋势、客座率、库存、价格和历史复盘，识别 `Opportunity`，同时生成候选 `CustomerNeed` 和可量化 `MarketingObjective`。机会和目标必须保留数据时间窗、来源、证据和人工确认状态。

### 客群洞察智能域

读取上游用户画像、客户关系、旅程阶段、历史反馈和可配置标签，评估目标客群吸引力、规模、长期价值和可触达性，输出版本化 `AudienceSnapshot`。标签是筛选属性，不替代客户需求和客群快照。

### 产品匹配智能域

围绕 `CustomerNeed` 和 `ValueProposition`，从产品管理平台提供的客票、辅营、联运、卡券和权益中选择 `ProductPackage`，校验库存、适用资格、MCT、价格和交付方式，输出待人工确认的匹配建议。

### 活动编排智能域

把 `MarketingObjective`、`AudienceSnapshot`、`ValueProposition` 和 `ProductPackage` 组织为 `StrategyPlan`，再形成 `TouchpointPlan`、活动版本、预算、频控、时间窗口和执行批次。它负责把策略转成可审批、可执行方案，不直接绕过审批触达客户。

### 内容生成智能域

读取客户需求、价值主张、产品事实、策略方案和渠道规范，为每个触点生成 `ContentAsset`。内容必须引用产品和规则证据，并经过事实、品牌、敏感词和合规审核。

### 效果分析智能域

合并渠道、交易、领券、辅营、履约、退订和投诉反馈，形成 `AttributionResult`，将增量效果关联到策略、客群、产品包、内容和渠道，再形成 `Review` 与下一轮规则建议。

## 人工治理边界

- 智能体可以创建候选机会、需求、价值主张、策略和归因结果，但不能自动发布活动。
- 营销目标、客群快照、产品匹配、策略方案、内容、审批和归因结果均保留人工确认记录。
- 事实、推断和人工决策分开存储，所有推荐必须能够回溯到知识片段、业务证据和源系统。
- 触达前必须执行客户授权、频控、保护名单、预算、库存、产品资格和渠道合规校验。
- 复盘结果只能形成规则更新建议，规则正式生效仍需业务人员确认。

## 航司业务示例

上海至三亚国庆航线在起飞前15天出现客座率偏低，同时外部目的地热度上升。机会洞察智能域形成营销机会和增量收入目标；客群洞察智能域生成“近期搜索但未出票、具有家庭出行特征”的聚合客群快照；产品匹配智能域将早鸟客票、额外行李、优选座位和目的地优惠券组合为产品包，并形成“一站式家庭早鸟出行更省心”的价值主张；活动编排智能域配置App触点、晚间发送窗口和七天一次频控；执行结果回传后，效果分析智能域把增量出票和辅营收入归因到客群、产品包、内容与渠道，最终形成下一轮策略建议。

# Architecture v1.0

## Agent runtime

The runtime uses plugin-like registration and append-only events. Each domain
declares responsibilities, inputs, outputs, and tools. The runtime owns
governance checks, human approval gates, event records, and failures.

## Marketing ontology

Initial classes include Opportunity, Audience, Customer, Journey,
ProductPackage, FareProduct, AncillaryProduct, BenefitCoupon, Campaign,
Content, Channel, Approval, and ConversionResult. Relations carry source,
evidence, confidence, and time so agents can explain recommendations and
result feedback.

## Domain boundaries

- Product module creates, approves, serves, and delivers activity products.
- Strategy module owns audience insight, snapshots, and protection rules.
- Activity module owns planning, matching, orchestration, content, approval,
  execution, feedback, and review.

# Reference Adoption

## DeepSeek Harness

Adopted patterns:

- Agent domains are registered capabilities rather than hard-coded UI actions.
- Runtime facts are append-only events that can be audited and replayed.
- Governance runs before tool execution and can reject a run.
- Human approval is an explicit run status for orchestration and content.

Primary reference areas:

- `docs/architecture.zh.md`
- `docs/agent-lifecycle.zh.md`
- `docs/tool-execution-pipeline.zh.md`
- `packages/core/session`
- `packages/core/tools`
- `packages/core/agent-loop`

The full Harness repository is not embedded because it is a developer-preview
general-purpose harness and would add unrelated shell, workspace, and coding
agent capabilities.

## Semantica

Adopted patterns:

- Graph nodes and edges carry provenance.
- Relationship assertions carry evidence and confidence.
- Campaign results feed back into audience entities.
- Ontology is a decision service, not only a visualization.

Primary reference areas:

- `ARCHITECTURE.md`
- `semantica/kg/graph_builder.py`
- `semantica/kg/entity_resolver.py`
- `semantica/ontology/ontology_validator.py`
- `semantica/provenance/manager.py`
- `semantica/context/decision_recorder.py`
- `semantica/context/policy_engine.py`

The full Semantica dependency set is not installed in the first vertical slice.
The platform keeps its ontology contracts small so Neo4j, RDF, SHACL, and
reasoning adapters can be introduced behind the service boundary later.