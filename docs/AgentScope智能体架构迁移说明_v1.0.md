# 东方航空智能营销平台 AgentScope 智能体架构迁移说明 v1.0

文档日期：2026年9月22日

## 1. 迁移目标

平台底层智能体统一采用 AgentScope 2.0.8。每个智能体由同一套 AgentScope Agent 运行机制承载，再通过不同的 Skill、MCP 工具白名单、系统提示词和独立工作区形成职责隔离。

现有 FastAPI 接口、租户权限、业务数据库、人工审批、运行记录和前端事件格式保持兼容。迁移重点是替换智能体运行底座，不把业务事实迁移到工作区，也不允许智能体绕过平台 API 直接发布活动。

## 2. 总体运行结构

业务请求 / 文件处理任务 / 市场热点任务
→ AgentScope Agent
→ AgentScope Toolkit
→ Python Tool + MCP Tool + Skill
→ 本体、知识和业务查询
→ 模型推理与流式事件
→ 平台审批、业务写入和审计

其中：

- Agent：负责 ReAct 推理循环、模型调用、工具调用、流式事件和最大迭代控制。
- Toolkit：统一挂载 Python Tool、MCP Client 和 Skill。
- Skill：保存航空营销业务规则、输出边界和处理步骤，不是直接调用的工具。
- MCP：提供租户范围内的受控查询服务。本版本地 MCP 为只读服务，写入仍由平台服务完成。
- Workspace：保存上下文卸载文件、Skill 副本和智能体临时产物；不是业务数据库，也不承载租户主数据。
- 平台数据库：保存活动、审批、执行、知识、本体实体、关系和模型用量等正式业务记录。

## 3. 智能体配置

配置文件：services/platform-api/app/agents/profiles.json

| 智能体 | Skill | 工作区 | MCP | 主要工具范围 |
| --- | --- | --- | --- | --- |
| 数据处理智能体 | data-processing | data-processing | ontology-ingestion | 本体语义、知识检索 |
| 机会洞察智能域 | opportunity-insight | opportunity-insight | marketing-ontology-read | 知识、本体、产品 |
| 客群洞察智能域 | audience-insight | audience-insight | customer-profile-read | 知识、本体 |
| 产品匹配智能域 | product-match | product-match | product-management-read | 本体、产品 |
| 活动编排智能域 | activity-orchestration | activity-orchestration | marketing-activity-write | 本体、产品、活动、任务 |
| 内容生成智能域 | content-generation | content-generation | content-fact-check | 本体、产品、活动 |
| 效果分析智能域 | effect-analysis | effect-analysis | marketing-effect-read | 活动、任务、本体 |
| 营销协同助手 | marketing-copilot | marketing-copilot | marketing-copilot-tools | 知识、本体、活动、产品、任务 |

每个 MCP 都配置了 mcp_tools 白名单。智能体即使连接到同一个本地 MCP 服务进程，也只能发现自己配置中的工具。

## 4. Skill 设计

目录：services/platform-api/app/agents/skills/

Skill 不直接执行数据库写入，而是给 AgentScope Agent 提供业务语义和治理规则：

1. 数据处理 Skill：判断内容是否适合形成正式本体候选，保存证据和人工确认要求。
2. 机会洞察 Skill：结合市场信号、航线供需、客座率、航班正常率、价格和节假日识别机会。
3. 客群洞察 Skill：只使用聚合画像、可配置标签、客户关系和触达许可，不展示旅客个人明细。
4. 产品匹配 Skill：约束机票、运价、联运、辅营、卡券和会员权益的事实引用。
5. 活动编排 Skill：约束预算、频控、渠道、活动版本和审批状态。
6. 内容生成 Skill：约束产品事实、日期、价格、权益和渠道文案格式。
7. 效果分析 Skill：区分送达、点击、出票、领券、履约、收入和增量归因。
8. 营销协同助手 Skill：规定知识、本体、活动和任务的检索顺序，并禁止越权写入。

## 5. MCP 服务

文件：services/platform-api/app/agents/mcp_server.py

本地 MCP 通过 AgentScope MCPClient + StdioMCPConfig 启动，每次智能体运行建立短生命周期的独立进程。进程通过环境变量接收数据库路径和租户 ID，以只读 SQLite 连接访问当前租户数据。

提供的工具包括：

- search_marketing_knowledge：检索知识片段，并返回文档来源。
- query_marketing_ontology：检索本体实体及相关关系。
- list_available_products：查询产品、运价、辅营、产品包和权益类实例。
- inspect_campaign：查看活动当前生命周期状态。
- inspect_data_pipeline：查看文件或接口处理任务、当前阶段和最近事件。
- get_ontology_schema：向数据处理智能体提供本体语义注册表摘要。

MCP 目前不提供活动创建、活动发布、审批通过、删除实体等写工具。涉及业务变更的动作必须回到 FastAPI 业务接口，继续经过租户校验、角色校验、审批和审计。

## 6. 工作区隔离

默认目录：services/platform-api/.agent_workspaces/

运行时按租户和智能体划分：

- tenant-{tenant_id}/data-processing
- tenant-{tenant_id}/opportunity-insight
- tenant-{tenant_id}/audience-insight
- tenant-{tenant_id}/product-match
- tenant-{tenant_id}/activity-orchestration
- tenant-{tenant_id}/content-generation
- tenant-{tenant_id}/effect-analysis
- tenant-{tenant_id}/marketing-copilot

工作区使用 AgentScope LocalWorkspace 管理，平台已将运行目录加入 .gitignore。工作区文件不作为营销知识自动入库，也不作为本体实例来源；需要入库的内容仍然必须经过数据处理流水线。

## 7. 与现有平台链路的对应关系

### 7.1 数据处理流水线

文件或接口数据先保存任务、文档和片段，然后由数据处理智能体运行。AgentScope 负责模型调用、Skill 约束、MCP 语义查询和事件输出；现有代码负责候选准入、置信度判断、人工确认和本体写入。

### 7.2 市场热点

热点处理仍由确定性分类和航线业务启发式先生成候选，再通过 AgentScope 的机会洞察配置进行模型辅助。模型返回空的可选候选时保留确定性航空候选，防止本地测试模型覆盖有效结果。

### 7.3 六个营销智能域

活动运行接口继续使用 AgentRuntime。它通过 UnifiedHarness 进入 AgentScope，按照请求的 domain_id 选择对应 Skill、MCP 和工作区，读取语义契约，并保留原有 completed、needs_approval 和 failed 状态。

### 7.4 营销协同助手

对话助手改为直接运行 AgentScope ReAct Agent：MCP 提供知识、本体、活动、产品和处理任务查询；Python Tool 保留 run_marketing_domain，用于在用户指定活动后调用六个智能域；工具结果通过 AgentScope 事件流返回前端；文本、工具、模型调用和运行结束事件继续转换为原有 SSE trace/token/complete 事件。

## 8. 模型配置

真实模型使用 AgentScope OpenAIChatModel + OpenAICredential，兼容平台现有的 OpenAI 风格服务配置：

- base_url：模型服务的 OpenAI 兼容根地址。
- model_name：具体模型名称。
- encrypted_api_key：平台已有加密存储字段。
- temperature、max_tokens、超时时间：继续读取租户模型配置。

本地 mock 模型也通过 AgentScope 自定义 ChatModelBase 适配器运行，不再走旧的直接 HTTP 调用路径。因此测试、热点处理、数据处理和营销域调用都经过 AgentScope 事件链。

## 9. 事件和流式输出

平台旧事件和 AgentScope 事件的主要映射如下：

| AgentScope 事件 | 平台事件 |
| --- | --- |
| ModelCallStartEvent | harness/model-started |
| ModelCallEndEvent | harness/model-finished |
| TextBlockDeltaEvent | agent/text-delta 和 SSE token |
| ThinkingBlockDeltaEvent | agent/thinking-delta |
| ToolCallStartEvent | harness/tool-started |
| ToolResultStartEvent | harness/tool-result-started |
| ToolResultEndEvent | harness/tool-finished |
| ReplyEndEvent | agentscope/reply-finished |

模型用量仍写入 model_usage，运行事件仍写入 runtime_events 或活动运行记录。模型内部思考内容只作为事件流提供给既有调试界面，生产环境应按权限控制是否展示原文。

## 10. 权限和治理边界

AgentScope 的 Toolkit、MCP 和 Skill 负责工具暴露与行为约束，但它们不替代平台的租户权限。正式写入仍由平台服务执行以下检查：

1. 当前用户是否属于租户。
2. 当前角色是否具有写入、审批或发布权限。
3. 活动、产品包、客群快照是否属于当前租户。
4. 本体候选是否经过人工确认。
5. 内容、预算、频控、渠道和产品事实是否完成业务校验。
6. 删除、发布和审批是否记录审计信息。

## 11. 安装和启动

依赖已加入 services/platform-api/requirements.txt：agentscope==2.0.8 和 starlette==0.50.0。后者用于保持 FastAPI 0.124.2 与 AgentScope MCP 依赖的兼容。

安装后从 services/platform-api 启动原有 API 即可，AgentScope 智能体按请求按需创建，不需要单独启动 AgentScope 服务。

## 12. 当前已完成与后续边界

已完成：

- AgentScope 2.0.8 作为统一运行底座。
- 八个智能体配置、八套 Skill、八个独立工作区。
- 按智能体划分的 MCP 名称和工具白名单。
- 本地只读 MCP 查询服务。
- 数据处理、市场热点、六个营销智能域和对话助手接入 AgentScope。
- AgentScope 事件到现有 SSE 和运行记录的兼容映射。
- 本地 mock 模型也经过 AgentScope。

仍需后续建设：

- 将 MCP 从本地 stdio 服务替换为生产环境的独立多租户 MCP Gateway，并使用服务间认证。
- 将业务写操作封装成带权限和审批检查的 MCP Tool，而不是允许智能体直接写库。
- 将 Workspace 从本地文件系统切换为生产级隔离沙箱或对象存储。
- 为六个智能域补充真正的本体子图装载、结构化输出 schema 和业务结果投影。
- 增加 MCP 工具调用的细粒度审计、速率限制、超时和熔断。

## 13. 验证结果

本次迁移增加 AgentScope 专项回归测试，并验证：

- AgentScope 版本和八个智能体配置存在。
- Skill、MCP、工作区均按智能体隔离。
- mock 模型经过 AgentScope Agent 执行。
- MCP 连接、模型事件、文本流和关闭事件完整产生。
- 旧 UnifiedHarness 接口继续可用。
- 原有智能体接口和市场热点测试保持通过。

## 版本记录

| 版本 | 内容 |
| --- | --- |
| v1.0 | 首次将平台智能体运行底座迁移到 AgentScope 2.0.8 |

