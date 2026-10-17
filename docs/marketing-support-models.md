# 营销参考模型

模型版本为 `holiday-20261017`。本体平台负责对象语义、关系校验、授权、产品资格与活动审批；本目录中的模型只补充候选优先级和客户价值分层，不替代现有画像或执行服务。

## 数据和验证结果

预订意向使用 [British Airways Forage 公开练习数据镜像](https://github.com/adityanaranje/British-airways-forage) 中的 `customer_booking.csv`。原始 50,000 行，整行去重后 49,281 行。该数据没有可追踪客户标识或完整事件时间，因此仅作匿名预订级预测验证，不能用于客户级归因或时间泛化论证。

固定种子 2026，按标签分层分为训练 34,496、验证 7,392、测试 7,393 行。测试正例 1,109 行。使用相同十个特征比较逻辑回归与 CatBoost，深度及阈值仅依验证集选择。特征排除标签、行号、分割标识和可能在附加服务选择后生成的行李、选座、餐食字段。

| 独立测试指标 | 逻辑回归 | CatBoost |
| --- | ---: | ---: |
| ROC-AUC | 0.7747 | 0.7871 |
| PR-AUC（average precision） | 0.3419 | 0.3660 |
| 前20%候选正例召回 | 47.34% | 49.41% |
| 前20%正例富集 | 2.37倍 | 2.47倍 |

配对自助采样 300 次，PR-AUC 差值的95%区间为 `[0.0049, 0.0441]`。另以航线哈希划分不相交航线测试，CatBoost ROC-AUC 为 0.7376、PR-AUC 为 0.3076，表明新航线泛化存在下降。富集倍数是相对随机筛选的离线结果，不能当作营销转化提升或东航购票概率。

价值分层使用 [天池航空公司客户价值分析](https://tianchi.aliyun.com/dataset/64977)。62,988 条记录经过完整性与合理区间过滤，保留 62,980 条，以入会天数、最近飞行间隔、飞行次数、累计里程和平均折扣训练 `log1p + StandardScaler + KMeans(k=5)`。5,000条抽样轮廓系数为0.2048，仅用于描述连续价值分层，不报告分群或流失“准确率”。

## 复现

请先从原发布页取得数据并遵守其许可。原始数据、处理中间表和运行环境不上传仓库。Python 3.12 环境运行：

```powershell
python -m pip install -r scripts/requirements-marketing-training.txt
python scripts/prepare_marketing_data.py --booking-source PATH/Forage.zip --profiles-source PATH/air_data.csv --output-dir PATH/processed
python scripts/train_marketing_models.py --data-dir PATH/processed --output-dir PATH/models
```

准备脚本保留来源文件校验值，在去重后固定分割，并另生成航线不相交分割。训练脚本只用验证集选择CatBoost深度与F1阈值，保存模型、标准化参数、聚类中心、八条公开测试样例及验证清单。训练过程不会覆盖线上文件。

平台发布模型位于 `services/platform-api/app/model_assets/`。更新时应一起发布权重、价值模型参数、样例与 `validation.json`，并重新运行API测试。清单登记三个文件的SHA-256，线上加载时校验，缺少文件或运行库时返回503。Docker构建通过 `COPY app` 打包模型，生产依赖已包含CatBoost。

```powershell
python -m pip install -r services/platform-api/requirements.txt pytest
python scripts/validate_ontology_marketing.py PATH/ontology_validation.json
# 在 services/platform-api 下运行
python -m pytest tests/test_marketing_models.py
```

本体工程验证为12种已定义情形各重复10次，每次重建数据库。完整检查保留10次正常方案并阻断110次无效方案；仅含预算、保护与授权的简化属性门控会放行其中80次关系或时点异常。这是受控规则回归验证，完整SQL或关系规则也可能达到相同结果，不是开放任务准确率或本体独占性的证据。

## 平台入口与接口

客群页面的“模型评估”弹窗读取后台结果，并可运行公开预订样例。东东通过只读工具 `analyze_marketing_model` 查看评估或调用评分，返回A2UI图表、表格和参考结果。缺少特征时应补齐数据，不能让大模型编造输入。

以下接口均要求登录，只读推理不产生营销写操作：

| 接口 | 用途 |
| --- | --- |
| `GET /api/marketing-models/evaluation` | 验证结果、模型版本及A2UI卡片 |
| `GET /api/marketing-models/examples` | 八条匿名公开测试样例 |
| `POST /api/marketing-models/booking-intent/score` | 十个完整来源特征的预订参考评分 |
| `POST /api/marketing-models/customer-value/score` | 五维客户价值分层 |

评分请求拒绝额外字段、标签、缺项、NaN和越界值。返回值保留“待本体校验”状态；产品有效期、渠道授权、频控及审批继续由平台服务检查。客户数据和业务资格不会因参考分数被改写。
