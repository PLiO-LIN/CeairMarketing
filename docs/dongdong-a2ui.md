# 东东对话与 A2UI

首页使用东航品牌栏、主视觉和轻量对话框。“进入智能空间”将同一对话面板移入空间，保留正在进行的请求及会话。空间提供历史对话、任务、记忆和可折叠执行过程。

## 界面协议

实现稳定版 **A2UI v0.9.1**。SSE `a2ui` 事件每次携带一个标准消息，按 `createSurface → updateDataModel → updateComponents` 创建结果界面；客户端支持局部更新及 `deleteSurface`。组件使用扁平 ID 引用和 RFC 6901 JSON Pointer，不执行模型提供的 HTML、脚本或远程代码。

平台目录 `ceair-marketing:assistant-v1` 采用标准 Text、Column、Row、Card、Button、Divider，并定义 Chart、DataTable、TaskCard 三个扩展组件。`/api/assistant/ui-catalog` 返回目录，`/api/assistant/capabilities` 声明版本与目录。图表数据来自 `query_statistics`，查询明细来自原有业务 API，任务来自后台待确认记录；工具观测转成协议消息之前经过官方 schema 与目录校验。

图表在对应助手消息中逐步渲染，支持柱状、占比、明细和 CSV。导航按钮发标准 `action` envelope 到 `/api/assistant/ui-action`，后端仅接受预定业务页面。任务卡仍使用现有鉴权、参数校验和原业务确认接口。

本项目使用与当前原生 JavaScript 前端一致的 DOM 渲染器，而非引入 Angular、Flutter 等完整框架。它实现上述目录及消息操作，是限定目录的渲染实现，不声称支持全部官方基础组件或函数。

## AgentScope 过程

AgentScope 2.0.8 `reply_stream` 的模型轮次、ToolCallStart/Delta/End、ToolResultStart/TextDelta/End 映射到公开过程。按 `tool_call_id` 合并工具输入、输出、成功或失败和耗时。公开行动说明来自模型面向用户的文本；`ThinkingBlockDeltaEvent` 始终忽略。工具参数及结果摘要限制长度、隐藏凭据字段，再经 SSE 展示并保存到会话详情。历史恢复过程、图表和最新任务状态；出错会保存已产生的步骤与界面。

资料：https://a2ui.org/specification/v0.9.1-a2ui/ ，https://a2ui.org/reference/renderers/ ，https://github.com/agentscope-ai/agentscope

## 验证

`tests/test_assistant_a2ui.py` 覆盖官方协议校验、未知组件拒绝、SSE 渐进界面、历史恢复、工具输入输出关联、错误状态、内部推理与凭据隔离，以及标准动作的鉴权和白名单。
