# 证据门控反事实超图策略网络

## 1 原创性边界

现有 OC-DRUP 和 OTH-GCT 使用了增量学习、双重稳健评价、图注意力等已有方法族，不能直接作为原创算法声称。本文件提出新的候选方法 **Evidence-Gated Counterfactual Hypergraph Policy Network（EG-CHPN）**。它的原创候选点不在于重新命名已有模型，而在于把航空营销本体中的多对象资格路径、证据可信度、反事实动作和资源约束放进同一个可训练决策网络。

在正式投稿前必须完成以下工作：

1. 检索 Web of Science、Scopus、IEEE Xplore、ACM Digital Library、Google Scholar 中的 ontology-aware uplift、hypergraph causal recommendation、constrained treatment policy 和 evidence-aware graph learning；
2. 对最接近的模型实现统一输入、统一时间切分和统一指标；
3. 把检索到的最接近方法写入 related work 和差异表；
4. 只有在差异经实验支持后，才能使用 “novel”“new” 或 “first” 一类表述。

## 2 核心研究问题

对一个冻结客群快照和候选营销动作，如何同时回答四个问题：该客群、航班、运价、产品和证据是否形成合法的多跳业务路径；采用动作相对于不触达会增加多少净贡献；替换产品、渠道或时间窗后增量效果如何变化；在预算、渠道容量和频控下哪些动作应被联合选择。

传统图神经网络通常把业务关系当作普通边；传统 uplift 模型通常看不到产品资格路径；传统策略优化通常在模型外部处理约束。EG-CHPN 的候选贡献是把三者合成一个可训练、可解释、可拒绝非法动作的反事实超图策略模型。

## 3 算法结构

### 3.1 资格超图

对每个候选动作构造局部超图 \(\mathcal H_a=(V_a,E_a)\)。节点来自 `AudienceSnapshot`、`Route`、`Flight`、`Cabin`、`Fare`、`ProductPackage`、`BusinessRule` 和 `Evidence`；超边可以同时连接客群快照、航线、航班、舱位、运价、产品包和证据。只有关系方向、对象类型、版本和生效时点都通过本体门禁时，超边才进入模型。非法路径在编码前被 mask，模型不能靠训练权重学会放行非法产品。

### 3.2 证据门控

对每条超边计算证据门：

\[
g_e=\sigma(w_g^T[c_e,f_e,r_e,s_e]),
\]

其中 \(c_e\) 是置信度，\(f_e\) 是时间新鲜度，\(r_e\) 是规则一致性，\(s_e\) 是来源稳定性。若门禁状态为 `pending` 或 `ineligible`，直接令 \(g_e=0\)；如果合法但证据陈旧，\(g_e\) 连续衰减。证据门参与消息传递，使不可靠证据无法通过邻居传播制造高质量表示。

### 3.3 反事实双塔

为每个动作建立两个共享参数的超图：

\[
\mathcal H_a^{(1)}=\mathcal H_a+\operatorname{intervention}(a),\qquad
\mathcal H_a^{(0)}=\mathcal H_a+\operatorname{no\text{-}intervention}.
\]

使用同一组超图注意层得到 \(h_a^{(1)}\) 和 \(h_a^{(0)}\)，再计算反事实差分：

\[
\Delta h_a=h_a^{(1)}-h_a^{(0)},\qquad
\hat\tau_a=f_\tau([h_a^{(1)},h_a^{(0)},\Delta h_a]).
\]

共享参数保证两个世界可比较；差分表示显式刻画触达动作改变了什么，而不是分别训练两个互不对齐的排序器。

### 3.4 可行域内的策略层

策略层不先预测、再事后过滤，而是把可行域写入目标：

\[
\max_\pi \sum_a z_a q_a\max(0,\hat\tau_a)m_a-c_a
-\lambda_B[\sum_a z_ac_a-B]_+
-\sum_k\lambda_k[\sum_{a\in k}z_a-C_k]_+
-\sum_g\lambda_g[\sum_{a\in g}z_a-F_g]_+.
\]

拉格朗日乘子使用投影梯度更新，策略网络输出动作分数，最终采用可行域投影得到触达计划。训练和推理都记录乘子、门控值、反事实差分和被拒绝路径，形成解释链。

## 4 训练目标

\[
\mathcal L=\mathcal L_{factual}+\lambda_1\mathcal L_{balance}+\lambda_2\mathcal L_{counterfactual}+\lambda_3\mathcal L_{evidence}+\lambda_4\mathcal L_{policy}.
\]

\(\mathcal L_{factual}\) 使用已触达和对照结果；\(\mathcal L_{balance}\) 使用处理组与对照组表示的 IPM/MMD 平衡项；\(\mathcal L_{counterfactual}\) 约束双塔差分与随机留出增量结果一致；\(\mathcal L_{evidence}\) 约束门控值与规则审核结果一致；\(\mathcal L_{policy}\) 使用预算、渠道和频控约束的拉格朗日损失。

## 5 可检验的论文贡献

最终论文只能在实验支持后采用以下表述：

1. 资格路径级建模：将多对象资格路径表示为超边，并在消息传递前执行语义 mask；
2. 证据门控反事实表示：让证据质量影响中间表示传播，而非只影响最终排序分数；
3. 反事实差分策略学习：同一超图编码器同时生成干预和不干预世界，并直接学习动作增量；
4. 可行域内联合训练：预算、渠道和频控通过拉格朗日策略层进入训练目标，避免预测最优但无法执行。

这些是方法设计上的原创候选点，不能替代系统文献检索和统计实验。

## 6 SCI 级实验协议

至少使用一个脱敏真实活动数据集，并保留活动版本、客群快照版本、产品版本、观测时间、渠道、处理变量、结果变量和倾向得分。没有随机留出时，不能把观察性 uplift 写成因果效果。

至少比较逻辑回归/GBDT 响应模型、T-learner、S-learner、X-learner、DR-learner、Causal Forest、TARNet/DragonNet、普通 GAT 或 HGT，以及不带证据门和不带超图 mask 的本方法变体。

按活动日期做滚动时间切分；所有特征只允许使用触达前数据；同一客户或聚合客群的未来回执不能进入过去窗口；产品失效和规则更新必须按版本冻结。

报告 AUUC/Qini、policy value、增量 PR-AUC、Brier、ECE、成本后增量收入、规则误放行率和约束违反率。每个主指标报告至少 5 个时间窗口的均值、标准差、95% 置信区间；使用配对 bootstrap 或时间窗口检验，并报告效应量。

必须分别移除超图结构、证据门、反事实双塔、策略层和时序编码，观察算法质量、证据覆盖、非法动作误放行和策略价值的变化。

## 7 当前状态

仓库中的 `oth_gct.py` 是上述 AI 编码器的依赖轻量原型，用于验证关系注意、时间和证据置信度确实改变表示；它不是最终论文实现，也不应被表述为已经完成的原创性证明。最终投稿版本应使用统一深度学习框架进行端到端训练，并补齐真实数据、基线、置信区间和文献差异分析。
