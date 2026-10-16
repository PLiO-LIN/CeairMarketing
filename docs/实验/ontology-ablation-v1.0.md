# 本体约束消融实验 ontology-ablation-v1.0

- 生成时间：2026-10-14T10:30:24+00:00
- 输入：构造的东航航班与产品快照（四条 MU 航线），判定全部来自生产门禁函数
- 本体版本：`ceair-marketing-ontology-v1.2`｜41 对象类型｜46 关系类型｜209 注册属性

## 结论

- 用例 117 条，应拦截 66 条，实际拦截 66 条，拦截率 100.0%
- 误放行（不可售被判可推荐）：0；过度拦截（合法被判非法）：0
- 阻断原因可定位率：97.0%
- 单次判定耗时：平均 0.19 ms，p95 1.833 ms

## 分层结果

| 层 | 判定函数 | 用例 | 应拦截 | 拦截率 | 误放行 | 过度拦截 | 平均耗时 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A 注册表合法性 | `validate_relation_endpoints` | 92 | 46 | 100.0% | 0 | 0 | 0.001 |
| B 本体准入 | `apply_ontology_admission` | 18 | 14 | 100.0% | 0 | 0 | 0.18 |
| C 发布门禁 | `campaign_readiness` | 7 | 6 | 100.0% | 0 | 0 | 2.696 |

## 基线与语义完整度

- 基线准入 44 对象／84 关系，航班到产品资格路径可走通，遍历 3 跳（辅营 3 跳）
- 实体证据字段 44/44，关系证据字段 84/84，平均每实体来源引用 2.0 条
- 适配器幂等（两次解析指纹一致）：是，指纹 `0c60b32960118506`

## 用例明细

| 用例 | 族 | 名称 | 层 | 判定函数 | 应拦截 | 实际拦截 | 判定 | 耗时 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A-departs_from-ok | A | departs_from 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0082 |
| A-departs_from-rev | A | departs_from 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0046 |
| A-arrives_at-ok | A | arrives_at 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0014 |
| A-arrives_at-rev | A | arrives_at 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0014 |
| A-has_segment-ok | A | has_segment 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0006 |
| A-has_segment-rev | A | has_segment 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0011 |
| A-operates_on-ok | A | operates_on 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0006 |
| A-operates_on-rev | A | operates_on 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0009 |
| A-has_cabin-ok | A | has_cabin 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0006 |
| A-has_cabin-rev | A | has_cabin 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.001 |
| A-has_fare-ok | A | has_fare 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-has_fare-rev | A | has_fare 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0021 |
| A-uses_product-ok | A | uses_product 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0006 |
| A-uses_product-rev | A | uses_product 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0009 |
| A-has_product_label-ok | A | has_product_label 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0006 |
| A-has_product_label-rev | A | has_product_label 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-includes_ancillary-ok | A | includes_ancillary 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-includes_ancillary-rev | A | includes_ancillary 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.001 |
| A-derived_from-ok | A | derived_from 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-derived_from-rev | A | derived_from 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-concerns_route-ok | A | concerns_route 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-concerns_route-rev | A | concerns_route 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0011 |
| A-concerns_flight-ok | A | concerns_flight 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-concerns_flight-rev | A | concerns_flight 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0011 |
| A-has_metric-ok | A | has_metric 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-has_metric-rev | A | has_metric 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-identifies-ok | A | identifies 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-identifies-rev | A | identifies 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0011 |
| A-targets_audience-ok | A | targets_audience 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0007 |
| A-targets_audience-rev | A | targets_audience 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-reveals_need-ok | A | reveals_need 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0018 |
| A-reveals_need-rev | A | reveals_need 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-pursues_objective-ok | A | pursues_objective 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0008 |
| A-pursues_objective-rev | A | pursues_objective 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0011 |
| A-uses_product_package-ok | A | uses_product_package 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0008 |
| A-uses_product_package-rev | A | uses_product_package 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-contains_product-ok | A | contains_product 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0008 |
| A-contains_product-rev | A | contains_product 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0011 |
| A-belongs_to_product_group-ok | A | belongs_to_product_group 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0008 |
| A-belongs_to_product_group-rev | A | belongs_to_product_group 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.001 |
| A-addresses_opportunity-ok | A | addresses_opportunity 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0009 |
| A-addresses_opportunity-rev | A | addresses_opportunity 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-satisfies_need-ok | A | satisfies_need 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0009 |
| A-satisfies_need-rev | A | satisfies_need 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-defines_value-ok | A | defines_value 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0009 |
| A-defines_value-rev | A | defines_value 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-has_strategy_plan-ok | A | has_strategy_plan 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0009 |
| A-has_strategy_plan-rev | A | has_strategy_plan 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-uses_touchpoint_plan-ok | A | uses_touchpoint_plan 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0009 |
| A-uses_touchpoint_plan-rev | A | uses_touchpoint_plan 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0011 |
| A-generates_content-ok | A | generates_content 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.002 |
| A-generates_content-rev | A | generates_content 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0013 |
| A-has_campaign_version-ok | A | has_campaign_version 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0011 |
| A-has_campaign_version-rev | A | has_campaign_version 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0013 |
| A-requires_approval-ok | A | requires_approval 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0009 |
| A-requires_approval-rev | A | requires_approval 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-executes-ok | A | executes 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0009 |
| A-executes-rev | A | executes 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0013 |
| A-uses_channel-ok | A | uses_channel 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.001 |
| A-uses_channel-rev | A | uses_channel 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0014 |
| A-carries_content-ok | A | carries_content 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.001 |
| A-carries_content-rev | A | carries_content 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0013 |
| A-produces_feedback-ok | A | produces_feedback 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.001 |
| A-produces_feedback-rev | A | produces_feedback 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0015 |
| A-produces_attribution-ok | A | produces_attribution 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.001 |
| A-produces_attribution-rev | A | produces_attribution 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0014 |
| A-attributes_to-ok | A | attributes_to 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.001 |
| A-attributes_to-rev | A | attributes_to 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0012 |
| A-reviewed_by-ok | A | reviewed_by 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0011 |
| A-reviewed_by-rev | A | reviewed_by 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0023 |
| A-generates_recommendation-ok | A | generates_recommendation 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0011 |
| A-generates_recommendation-rev | A | generates_recommendation 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0014 |
| A-updates_rule-ok | A | updates_rule 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0011 |
| A-updates_rule-rev | A | updates_rule 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0014 |
| A-confirmed_by_human-ok | A | confirmed_by_human 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0011 |
| A-confirmed_by_human-rev | A | confirmed_by_human 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0018 |
| A-has_evidence-ok | A | has_evidence 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0011 |
| A-has_evidence-rev | A | has_evidence 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0018 |
| A-has_tag_attribute-ok | A | has_tag_attribute 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0012 |
| A-has_tag_attribute-rev | A | has_tag_attribute 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0018 |
| A-contains_chunk-ok | A | contains_chunk 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0012 |
| A-contains_chunk-rev | A | contains_chunk 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0015 |
| A-supports_claim-ok | A | supports_claim 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0012 |
| A-supports_claim-rev | A | supports_claim 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0014 |
| A-evidence_for-ok | A | evidence_for 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0012 |
| A-evidence_for-rev | A | evidence_for 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0032 |
| A-claims_about-ok | A | claims_about 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0012 |
| A-claims_about-rev | A | claims_about 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0016 |
| A-produces_object-ok | A | produces_object 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0023 |
| A-produces_object-rev | A | produces_object 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0016 |
| A-supports_campaign-ok | A | supports_campaign 正向合法 | A | `validate_relation_endpoints` | 否 | 否 | 放行正确 | 0.0013 |
| A-supports_campaign-rev | A | supports_campaign 反向越界 | A | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.0018 |
| B0 | B0 | 完整语义图基线 | B | `apply_ontology_admission` | 否 | 否 | 放行正确 | 0.351 |
| P1a | P1 | 删除全部舱位到运价关系 | B | `apply_ontology_admission` | 是 | 是 | 拦截正确 | 0.256 |
| P1b | P1 | 删除全部运价到产品关系 | B | `apply_ontology_admission` | 是 | 是 | 拦截正确 | 0.199 |
| P1c | P1 | 仅删除一条舱位到运价关系 | B | `apply_ontology_admission` | 否 | 否 | 放行正确 | 0.184 |
| P3a | P3 | 航班到航线方向反转 | B | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.171 |
| P3b | P3 | 舱位到运价方向反转 | B | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.161 |
| P3c | P3 | 运价到产品方向反转 | B | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.162 |
| P3d | P3 | 产品到产品组方向反转 | B | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.211 |
| P4a | P4 | 关系全部缺失来源证据 | B | `apply_ontology_admission` | 是 | 是 | 拦截正确 | 0.181 |
| P4b | P4 | 实体全部缺失来源证据 | B | `apply_ontology_admission` | 是 | 是 | 拦截正确 | 0.14 |
| P5a | P5 | 实体置信度低于阈值 0.64 | B | `apply_ontology_admission` | 是 | 是 | 拦截正确 | 0.097 |
| P5b | P5 | 实体置信度等于阈值 0.65 | B | `apply_ontology_admission` | 否 | 否 | 放行正确 | 0.17 |
| P5c | P5 | 关系置信度低于阈值 0.64 | B | `apply_ontology_admission` | 是 | 是 | 拦截正确 | 0.158 |
| P5d | P5 | 关系置信度等于阈值 0.65 | B | `apply_ontology_admission` | 否 | 否 | 放行正确 | 0.171 |
| P6a | P6 | 未注册对象类型 FakeFareClass | B | `object_type_ids` | 是 | 是 | 拦截正确 | 0.154 |
| P6b | P6 | 运价降级为知识文档类型 | B | `normalize_ontology_decision` | 是 | 是 | 拦截正确 | 0.147 |
| P6c | P6 | 关系端点指向非法对象 | B | `validate_relation_endpoints` | 是 | 是 | 拦截正确 | 0.169 |
| P6d | P6 | 模型门禁拒绝写入本体 | B | `normalize_ontology_decision` | 是 | 是 | 拦截正确 | 0.164 |
| C0 | C | 五门禁全通过基线 | C | `campaign_readiness` | 否 | 否 | 放行正确 | 2.889 |
| P2a | P2 | 产品包有效期已过 | C | `campaign_readiness` | 是 | 是 | 拦截正确 | 3.864 |
| P2b | P2 | 产品包未审批 | C | `campaign_readiness` | 是 | 是 | 拦截正确 | 2.394 |
| P2c | P2 | 客群快照未冻结 | C | `campaign_readiness` | 是 | 是 | 拦截正确 | 2.465 |
| P2d | P2 | 渠道缺少已审核内容 | C | `campaign_readiness` | 是 | 是 | 拦截正确 | 2.888 |
| P2e | P2 | 活动预算为零 | C | `campaign_readiness` | 是 | 是 | 拦截正确 | 2.542 |
| P2f | P2 | 内容未审核 | C | `campaign_readiness` | 是 | 是 | 拦截正确 | 1.833 |

## 指标定义

- **blocked**：按用例声明的观察面判定：gate=本体门禁不再放行写入；path=航班到产品的资格路径在已准入关系中不可达；relation_any=没有任何关系被准入；relation:<type>=该类型关系全部未被准入；publish=campaign_readiness 返回 ready=false
- **false_accept**：应当拦截却被放行的用例数，即不可售或非法语义仍进入可执行流程
- **over_block**：不应拦截却被拦截的用例数，即合法语义被误杀，衡量门禁是否过苛
- **localization_rate**：被拦截用例中，生产函数返回值同时给出可定位依据（逐条拒因、失败门禁项或门禁整体拒绝决策）的比例
- **eligibility_hops**：已准入关系图上从 Flight 到 Product 的最短跳数，即一次资格判定需要贯通的关系层数

## 扰动族覆盖

| 族 | 含义 | 用例 | 拦截 |
| --- | --- | --- | --- |
| A | 关系方向与端点类型合法性 | 92 | 46/46 |
| P1 | 删除必要关系 | 3 | 2/2 |
| P2 | 产品有效期与审批门禁 | 6 | 6/6 |
| P3 | 关系方向反转 | 4 | 4/4 |
| P4 | 缺失来源证据 | 2 | 2/2 |
| P5 | 置信度阈值边界 | 4 | 2/2 |
| P6 | 未注册类型与非法端点 | 4 | 4/4 |
| B0 | 完整语义图基线 | 1 | 0/0 |
| C | 发布门禁对照 | 1 | 0/0 |

## 口径与边界

- 输入为构造的东航航班与产品快照，用于验证语义门禁行为，不代表东航真实经营数据。
- P1a 与 P1b 属于整批删除必要关系，生产函数不产生逐条拒因，因此不计入可定位率分子；其拦截由路径不可达与发布门禁共同保证。
- 本实验不覆盖模型生成质量、并发容量与经营增量；三者分别见智能体稳健性报告与企业试点计划。
- 判定全部来自生产函数，harness 不重写规则。

## 代码出处

- `validate_relation_endpoints`：services/platform-api/app/ontology/semantic_model.py:230
- `apply_ontology_admission`：services/platform-api/app/data_pipeline.py:394
- `normalize_flight_product_payload`：services/platform-api/app/flight_product_pipeline.py:52
- `campaign_readiness`：services/platform-api/app/campaign_readiness.py:14
- `fixture`：services/platform-api/scripts/ontology_ablation_cases.py
