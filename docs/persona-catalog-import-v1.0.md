# 东航旅客画像目录导入说明 v1.0

## 导入范围

读取 `画像维度及类型(1).xlsx` 的 `旅客画像维度` 和 `画像类型` 两个工作表，分别写入画像维度定义、画像分群及分群判定规则，并同步为可用于客群圈选的租户标签。文件只包含目录和规则，不导入旅客个人记录或身份证号、手机号、邮箱等个人值。

## 平台映射

画像维度使用 `field_code` 作为稳定编码，例如 `preferred_route`、`member_tier`；画像类型使用 `segment_code`，并同步为 `persona_A1` 等运营标签。画像类型多行规则继承上一条有效的主画像、子类型和代码，规则保留判定字段、条件、数据来源、推荐产品和触达渠道，便于客群识别智能域解释。

## 幂等执行

默认按“租户 + 字段代码/分群代码”去重，重复运行不会产生重复记录；需要覆盖目录属性时增加 `--upsert`。

```powershell
python services/platform-api/scripts/import_persona_catalog_v1.py
python services/platform-api/scripts/import_persona_catalog_v1.py --upsert
```

## 业务使用

营销人员可在客群画像页面复用画像维度标签，将多个标签组合成客群包；AI 客群识别读取分群规则与来源，生成可解释的圈选建议，人工确认后进入活动创建和触达流程。
