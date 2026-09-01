# 画像目录数据库开发说明

## 1. 这次功能解决什么问题

项目已将《画像维度及类型.xlsx》整理为可被程序读取的标准数据，并在 PostgreSQL 中保存为三张关联表：

| 数据内容 | 表名 | 当前数量 |
| --- | --- | ---: |
| 画像字段定义 | `persona_dimension_definitions` | 98 条 |
| 画像细分类型 | `persona_segments` | 17 条 |
| 细分判定规则 | `persona_segment_rules` | 68 条 |

目标是让画像字段、客群细分和判定条件不再只存在于 Excel，而是成为可查询、可追溯、可供后续接口和营销规则使用的数据库数据。

## 2. 文件位置和职责

| 文件 | 职责 |
| --- | --- |
| `services/platform-api/app/db_models.py` | 定义三张数据库表的字段、唯一性规则和关联关系。 |
| `services/platform-api/app/persona_catalog_seed.json` | 已标准化的目录数据，是首次导入的直接来源。 |
| `services/platform-api/app/seed.py` | 读取 JSON，并将数据写入数据库。 |
| `services/platform-api/app/main.py` | 应用启动时建表，并调用导入函数。 |
| `tools/build_persona_catalog_seed.py` | 将后续更新的 Excel 转为 JSON 的工具。 |

数据流如下：

```text
Excel 原始文件
  -> tools/build_persona_catalog_seed.py
  -> persona_catalog_seed.json
  -> seed.py
  -> PostgreSQL 三张画像表
```

## 3. 三张表如何关联

```text
persona_dimension_definitions
  保存“有哪些可用画像字段”

persona_segments
  保存“有哪些细分人群”
       1
       |
       | 一个细分类型可拥有多条规则
       v
persona_segment_rules
  保存“进入该细分需要满足什么条件”
```

规则表中的 `segment_id` 指向 `persona_segments.id`。这是一对多关系：一个细分类型可配置多条规则。

## 4. 表结构说明

### 4.1 `persona_dimension_definitions`

该表记录画像字段的“字典”。一条记录代表一个可用于画像或规则判断的字段，例如年龄段、常用航线、近一年飞行次数。

| 字段组 | 主要字段 | 含义 |
| --- | --- | --- |
| 主键和租户 | `id`, `tenant_id` | `id` 是数据库内部编号；`tenant_id` 用于区分不同业务租户的数据。 |
| 字段标识 | `field_name`, `field_code` | 前者给业务人员阅读，后者给程序、接口和规则稳定引用。 |
| 归属和类型 | `module_key`, `module_name`, `data_type`, `source_data_type` | 描述字段属于哪个模块，以及字段本身和源数据的类型。 |
| 数据治理 | `collection_method`, `required_mode`, `allowed_values`, `update_frequency` | 描述采集方式、是否必填、允许取值和更新频率。 |
| 画像适用范围 | `applicable_personas_json`, `is_supplemental` | 哪些画像可使用该字段，以及该字段是否为补充字段。 |
| 来源追溯 | `source_file`, `source_version`, `source_row` | 可回溯到原始文件、版本和 Excel 行号。 |

同一个租户内，`field_code` 不能重复。这由唯一约束 `(tenant_id, field_code)` 保证。

### 4.2 `persona_segments`

该表记录“要识别的客群是什么”，不保存具体判断条件。

| 字段 | 含义 |
| --- | --- |
| `segment_code` | 程序使用的细分代码，同一租户内唯一。 |
| `primary_persona_code`, `primary_persona_name` | 所属一级画像类型。 |
| `segment_name` | 细分人群名称。 |
| `belongs_to`, `within_persona_share` | 归属信息和在一级画像中的占比。 |
| `recommended_products`, `recommended_channels` | 推荐产品和推荐触达渠道。 |
| `source_file`, `source_version`, `source_row` | 该细分的来源追溯信息。 |

模型中的 `rules` 属性不是数据库额外字段，而是 SQLAlchemy 提供的关联入口。程序拿到一个细分对象后，可以通过 `segment.rules` 读取它的多条规则。

### 4.3 `persona_segment_rules`

该表记录“为什么一个旅客会进入这个细分”。

| 字段 | 含义 |
| --- | --- |
| `segment_id` | 所属细分类型的数据库编号，关联 `persona_segments.id`。 |
| `dimension_name`, `field_code`, `field_variant` | 规则使用的画像维度、字段代码和字段变体。 |
| `condition_expression` | 原始业务条件表达式，保留便于人工复核。 |
| `condition_operator`, `condition_value` | 程序可执行或转换为程序逻辑的运算符和比较值。 |
| `data_source` | 判断该字段所依赖的数据来源。 |
| `field_registered` | 该规则字段是否已在字段定义表登记。 |
| `rule_order` | 规则顺序。 |
| `source_row` | 原 Excel 行号。 |

同一细分内，原文件同一行不能重复导入。这由唯一约束 `(segment_id, source_row)` 保证。

## 5. `seed.py` 如何导入数据

### 5.1 找到 JSON 文件

```python
PERSONA_CATALOG_PATH = Path(__file__).with_name("persona_catalog_seed.json")
```

这句会找到与 `seed.py` 放在同一目录的 JSON 文件，不依赖某台电脑的绝对路径，因此在 Docker、开发机和服务器上都可使用。

### 5.2 防止重复导入

`seed_persona_catalog(session, tenant_id)` 首先检查当前租户是否已经存在一条 `persona_segments` 数据。若存在则直接返回。

这使首次初始化具备幂等性：正常情况下重启项目不会把 17 个细分和 68 条规则重复插入数据库。

### 5.3 实际导入顺序

1. 读取 `persona_catalog_seed.json`。
2. 循环写入 98 条画像字段定义。
3. 循环写入 17 条细分类型。
4. 每写入一个细分后执行 `flush()`，让数据库生成该细分的 `id`。
5. 根据 `segment_code` 找到对应细分的 `id`，写入 68 条规则的 `segment_id`。
6. 最后执行 `session.commit()`，将本次导入正式提交。

`flush()` 不是最终保存，它只是让当前事务中的数据先获得数据库编号；`commit()` 才是最终提交。

## 6. 项目启动时发生什么

`main.py` 中的 `lifespan()` 会在 API 服务启动时按以下顺序执行：

1. `Base.metadata.create_all(bind=engine)`：创建尚不存在的表。
2. 执行现有数据库迁移和租户约束处理。
3. 创建或确认 `CEA-HQ` 租户和管理员。
4. 初始化模型配置、MinerU 等租户基础数据。
5. 调用 `seed_persona_catalog(session, tenant_id)` 导入画像目录。
6. API 服务开始接收请求。

因此，对一个全新数据库，只要项目能正常启动，三张画像表和目录数据会自动出现。

## 7. 如何验证数据是否已经导入

在 Chat2DB 中连接项目 PostgreSQL 后，执行：

```sql
SELECT 'persona_dimension_definitions' AS table_name, COUNT(*) AS row_count
FROM persona_dimension_definitions
UNION ALL
SELECT 'persona_segments', COUNT(*)
FROM persona_segments
UNION ALL
SELECT 'persona_segment_rules', COUNT(*)
FROM persona_segment_rules;
```

正常结果应为 98、17、68。

要查看某个细分及其规则，可执行：

```sql
SELECT
  s.segment_name,
  r.field_code,
  r.condition_operator,
  r.condition_value
FROM persona_segments AS s
JOIN persona_segment_rules AS r ON r.segment_id = s.id
ORDER BY s.segment_code, r.rule_order;
```

## 8. 后续开发怎么改

### 修改或新增画像数据

推荐流程：

1. 修改 Excel 源文件，并保留版本信息。
2. 使用 `tools/build_persona_catalog_seed.py` 重新生成 JSON。
3. 检查 JSON 的维度、细分和规则数量，以及未登记字段。
4. 提交 Excel 变化说明、JSON 和必要的代码修改。
5. 为已经存在的数据库设计更新策略后再发布。

当前 `seed_persona_catalog()` 只负责首次初始化。已有细分数据时会直接跳过，因此更新 GitHub 中的 JSON 不会自动更新一套已经运行过的数据库。

若后续需要同步更新生产或本地既有数据，应新增一段明确的迁移或“目录版本同步”逻辑，而不是删除数据库表后重建。

### 新增接口或营销规则

目前本次提交已完成数据建模和启动导入，但没有单独提供画像目录的读取、编辑 API。

后续如需在前端展示或由营销引擎使用，可在 `services/platform-api/app/main.py` 中增加只读接口，例如：

- 查询全部画像维度。
- 按一级画像查询细分类型。
- 查询某个细分对应的全部规则。

编辑接口应限制为管理员，并保留 `source_file`、`source_version` 和变更审计信息。

## 9. 开发注意事项

1. 不要只改数据库而不改 JSON 或 Excel 来源，否则以后无法追溯数据来源。
2. 不要随意修改 `field_code` 或 `segment_code`。它们是程序关联、规则引用和后续接口的稳定标识。
3. 新增规则前先确认 `field_code` 已在 `persona_dimension_definitions` 登记。
4. 不要依赖重启服务来更新已有目录数据。当前逻辑仅做首次初始化。
5. 若删除一个细分，关联规则会因外键 `ondelete="CASCADE"` 一同删除，应先备份并评估影响。

## 10. 当前版本

本说明对应主分支中通过 Pull Request #1 合并的画像目录功能。主分支合并提交为 `d4f58fe`。
