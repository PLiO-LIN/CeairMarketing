# 数据集导入与本体映射

本次版本将完整源记录保存到 `datasets`、`dataset_rows`，并将业务对象写入现有工作台及注册本体。源明细与图谱在同一事务内写入；主键、外键、金额和本体关系校验失败时整体回滚。

## 导入命令

在 `services/platform-api` 中执行，明确指定数据库、工作区、操作者及版本前缀：

```powershell
python -m app.dataset_import --input <dataset.json> --database-url <DATABASE_URL> --tenant-code CEA-COMPETITION --username competition --namespace CE26 --report <report.json>
```

导入前用 SQLite backup API 备份活动库。不要以复制正在写入的 `.db` 文件代替一致性备份。程序不接收凭据；操作者必须是目标工作区内具备写入权限的现有账号。相同版本和内容重复运行不产生重复记录；同版本内容变化会拒绝写入。

`dataset.json` 包含 metadata、sheets、statistics 和 checks。每个 sheet 定义 name、fields（code/label/type）、pk、fks、rows、grain、source、use。29 个支持的表名及固定数据集编码见 `app/dataset_import.py:SHEET_KEYS`。

## 当前本地入库

- 工作区 `CEA-COMPETITION`，版本 `CE26`。
- 29 个数据集，429,996 条源记录。合计含原始层、标准层和本体映射输入，不代表独立旅客数。
- 10,000 个模拟客户形成 6 个互斥业务分群与快照。另有 19 个历史触达范围和快照，历史范围含排除/失败事件，可能相互重叠。
- 12 个模拟辅营产品包、19 个模拟历史活动、57 个历史内容。产品包保持草稿和待上游核验，历史活动不恢复为可执行状态。
- 产品目录展示 12 个模拟产品与 30 个爬取票价产品。模拟报价的 4 个票价品种只在本体中建模。
- 新增 271,502 个本体对象、410,417 条关系。既有 84 个对象、84 条关系保留；工作区合计 271,586 个对象、410,501 条关系。

客户、订单、搜索、曝光、交易和训练样本保存在数据层。图谱不创建个人旅客对象，采用 CustomerAggregate / AudienceSnapshot。航班、航段、机场、航线、舱位和报价通过 typed relations 连接；库存形成 MetricObservation，触达与归因形成按活动聚合的 Feedback / AttributionResult。

## 查询与界面

- 数据接入页“数据目录”：数据量、来源、字段定义、明细分页、完整记录及 ID 查询。
- 本体实例页“检索本体对象”，或数据目录“检索本体”：检索所有已入库对象，查看属性、邻接关系和来源明细。
- `GET /api/datasets` 返回当前工作区目录。
- `GET /api/datasets/{dataset_key}/rows` 支持 offset、limit（1–100）与 exact record_key / route_id / flight_id / customer_id。
- `GET /api/datasets/{dataset_key}/summary` 返回相应数据集的统计；group_by 仅支持 source_id / data_mode / route_id，最多100组。
- `GET /api/ontology/entities` 支持 q、entity_type、offset 和 limit。
- `GET /api/ontology/entities/{external_id}/neighbors` 支持 offset 和 limit（1–100）。

东东通过 API catalog / query_platform 读取上述接口。query_statistics 新增 datasets 和 customer_segments，后者读取互斥模拟分群人数，输出 A2UI 图表。全图概览最多300对象，活动图按局部关系读取，图谱统计在 SQL 中聚合，避免每次加载全量本体。

## 数据口径

爬取 15 个 CSV、90,714 条原始行，保留原值和来源文件。1,665 条完全重复及 8 条缺价记录只在标准报价中排除。18,396 条中转行保留在原始层，不拆成航段票价。72,310 条标准报价仅表示有效单航段来源报价，未经在线核验，不表示已成交订单。

查询日期不能代替抓取时间；captured_at 未知保留 null。爬取资料没有真实座位数、实际乘机人数或客座率，相关字段保持未知。CNY 是国内报价场景假设；共享航班不能直接累计为独立运力。模拟报价与爬取报价分别标识。

实付减退款为含税净实付，不等同会计收入、利润或营销增量。末次点击归因为规则归因，causal_effect=false。实验按随机分配 ITT 分析，不按送达筛选；未成熟训练标签保留空值。本次导入未训练或上线算法模型。

## 验证

API 测试覆盖导入幂等、数据保真、金额/外键校验、语义失败整体回滚、权限及租户隔离。全量本地验收逐表核对行数和明细读取，核对产品、活动关系、报价邻接及图谱统计，SQLite integrity_check 为 ok；总部租户业务、图谱和模型配置与备份逐行一致。

导入报告、源数据和 Excel 属于交付数据，不提交 Git；数据库、登录 token 和模型凭据也不提交。
