# Marsh-Echo（九皋 / marshecho）v2 实验报告

架构：EG-CHPN v2（证据门控反事实超图策略网络）。模型实例名 **marshecho（九皋）**，论文英文名 **Marsh-Echo**。

**全部数字口径为【流程验证（虚构）】**：本体实体与业务规则口径来自真实民航营销业务资料，而结果变量（潜在结果、处理分配、回执、收入）由模拟器生成，不构成任何真实航司经营提升证据。

## 1 训练与算力

- 已记录 run 数：400
- 累计 GPU 秒：121908.2
- 平均单 run 秒数：304.8
- 出厂检查点选择规则：lowest mean training-window validation loss across shared seeds; test metrics never consulted
- 胜出配置：tree=runs_final lr=0.003 wd=0.001 λ_policy=0.1，平均验证损失 0.648514（1 个共同种子）
- 出厂权重：`checkpoint_seed13_lr0.003_wd0.001_lp0.1_h192_L3_e4.pt`

## 2 与 v1 原型的关系

- v1（`eg_chpn_v1_frozen`）注意力参数随机初始化且从未优化，只有二元边与两个线性因果头；v2 为端到端训练的超边消息传递 + 可学习证据门 + 共享参数反事实双塔 + 约束策略头。
- v1 保留为消融行，不删除，便于对照。

## 3 基线与消融

| dgp | 方法 | 门 | 选择器 | 种子 | 策略价值 | CI | 过滤前非法率(规则) | Qini |
|---|---|---|---|---:|---:|---:|---:|---:|
| v1 | dragonnet | learned | oracle_rule | 10 | 13102.585 | ±1168.270 | 0.446 | 0.883 |
| v1 | gat_trained | learned | oracle_rule | 10 | 4515.553 | ±390.459 | 0.241 | 0.906 |
| v1 | marshecho_gate_deterministic_only | learned | oracle_rule | 10 | 16100.736 | ±1411.869 | 0.370 | 0.927 |
| v1 | marshecho_no_balance | learned | oracle_rule | 10 | 16716.941 | ±1093.413 | 0.389 | 0.930 |
| v1 | marshecho_no_counterfactual | learned | oracle_rule | 10 | 14659.810 | ±1586.356 | 0.186 | 0.897 |
| v1 | marshecho_no_dual_tower | learned | oracle_rule | 10 | 16553.379 | ±1032.406 | 0.379 | 0.929 |
| v1 | marshecho_no_evidence_loss | learned | oracle_rule | 10 | 15665.743 | ±1300.384 | 0.342 | 0.928 |
| v1 | marshecho_no_gate | none | oracle_rule | 10 | 16673.180 | ±1195.690 | 0.409 | 0.951 |
| v1 | marshecho_no_hypergraph | learned | oracle_rule | 10 | 4545.790 | ±410.465 | 0.193 | 0.906 |
| v1 | marshecho_no_lagrangian | learned | oracle_rule | 10 | 16113.134 | ±1093.477 | 0.347 | 0.930 |
| v1 | marshecho_no_policy_head | learned | oracle_rule | 10 | 16690.000 | ±869.604 | 0.300 | 0.932 |
| v1 | marshecho_no_temporal | learned | oracle_rule | 10 | 16602.766 | ±1020.186 | 0.371 | 0.932 |
| v1 | marshecho_none | learned | oracle_rule | 10 | 15583.698 | ±1346.247 | 0.330 | 0.927 |
| v1 | tarnet | learned | oracle_rule | 10 | 13102.585 | ±1168.270 | 0.446 | 0.883 |
| v2 | dragonnet | learned | oracle_rule | 10 | 14060.766 | ±1302.689 | 0.447 | 0.851 |
| v2 | gat_trained | learned | oracle_rule | 10 | 4888.570 | ±352.891 | 0.131 | 0.881 |
| v2 | marshecho_gate_deterministic_only | learned | oracle_rule | 10 | 18553.474 | ±1672.581 | 0.173 | 0.920 |
| v2 | marshecho_no_balance | learned | oracle_rule | 10 | 19192.110 | ±1234.174 | 0.226 | 0.923 |
| v2 | marshecho_no_counterfactual | learned | oracle_rule | 10 | 17111.163 | ±1969.359 | 0.142 | 0.882 |
| v2 | marshecho_no_dual_tower | learned | oracle_rule | 10 | 19246.789 | ±1228.386 | 0.230 | 0.923 |
| v2 | marshecho_no_evidence_loss | learned | oracle_rule | 10 | 19242.514 | ±1243.391 | 0.192 | 0.929 |
| v2 | marshecho_no_gate | none | oracle_rule | 10 | 19097.183 | ±1159.905 | 0.381 | 0.958 |
| v2 | marshecho_no_hypergraph | learned | oracle_rule | 10 | 4765.613 | ±415.221 | 0.119 | 0.880 |
| v2 | marshecho_no_lagrangian | learned | oracle_rule | 10 | 19259.866 | ±1167.095 | 0.211 | 0.923 |
| v2 | marshecho_no_policy_head | learned | oracle_rule | 10 | 19396.728 | ±1042.202 | 0.178 | 0.928 |
| v2 | marshecho_no_temporal | learned | oracle_rule | 10 | 19596.831 | ±1147.668 | 0.217 | 0.931 |
| v2 | marshecho_none | learned | oracle_rule | 10 | 19410.817 | ±1195.427 | 0.181 | 0.927 |
| v2 | tarnet | learned | oracle_rule | 10 | 14060.766 | ±1302.689 | 0.447 | 0.851 |
| v1 | marshecho_no_gate | none | oracle_rule | 10 | 16673.180 | ±1195.690 | 0.409 | 0.951 |
| v1 | marshecho_none | learned | oracle_rule | 10 | 15583.698 | ±1346.247 | 0.330 | 0.927 |
| v2 | marshecho_no_gate | none | oracle_rule | 10 | 19097.183 | ±1159.905 | 0.381 | 0.958 |
| v2 | marshecho_none | learned | oracle_rule | 10 | 19398.498 | ±1191.194 | 0.181 | 0.927 |
| v1 | marshecho_no_gate | none | oracle_rule | 10 | 17752.569 | ±867.344 | 0.363 | 0.967 |
| v1 | marshecho_none | learned | oracle_rule | 10 | 17661.158 | ±882.598 | 0.119 | 0.946 |
| v2 | marshecho_no_gate | none | oracle_rule | 10 | 20047.909 | ±1095.495 | 0.277 | 0.975 |
| v2 | marshecho_none | learned | oracle_rule | 10 | 19967.563 | ±1056.775 | 0.051 | 0.941 |

完整逐种子数据见 `marshecho-ablation-v2.0.csv`；numpy 基线（含 S/X/DR-learner）见 `eg-chpn-simulation-v2.0.json`。

## 4 证据门 × 资格过滤 2×2 因子（关键安全结论）

v1 论文里“0% vs 34.4% 非法选择率”的对比是构造性的：只有无门那一臂被关掉了 oracle 过滤。v2 改为同一选择器下 {学习门, 无门} × {过滤开, 过滤关} 的因子设计，并报告**过滤前**非法率。

| 门 | 选择器 | 策略价值 | 过滤前非法率(规则) | 选中后非法率 | Qini |
|---|---|---:|---:|---:|---:|
| learned | none | 15054.261 | 0.119 | 0.119 | 0.946 |
| learned | oracle_both | 18044.094 | 0.119 | 0.000 | 0.946 |
| learned | oracle_rule | 17661.158 | 0.119 | 0.000 | 0.946 |
| none | none | 8869.637 | 0.363 | 0.363 | 0.967 |
| none | oracle_both | 18089.984 | 0.363 | 0.000 | 0.967 |
| none | oracle_rule | 17752.569 | 0.363 | 0.000 | 0.967 |

> 只有当 learned 门在 selector=none 时也压低非法选择率，证据门本身才算被证明；selector 打开时的差异来自过滤器的作用范围。

命名区分：消融表里的 `marshecho_no_gate` 是**训练时就没有门**的模型；`eg-chpn-simulation-v2.0.json` 里的 `marshecho_shipped_gate_off_infer` 是**同一份出厂权重在推理时关门**。两者是不同干预，不可混用。

**诚实结论**：可学习证据门只能压低过滤前非法选择率；把非法选择降到 0 的是“确定性语义硬掩码 + 资格过滤”。因此平台侧的治理保证来自门禁与过滤（OC-DRUP 命题 1），不得写成“神经网络自己学会了拒绝非法动作”。

## 4b 可执行性损失项（方法修正，实测）

- 协议：seed 13、1500 客群、hidden 96 / 2 层 / 800 epoch、GRID[4]（lr 3e-3, wd 1e-3）；selector=none，指标为过滤前非法率与策略价值

| 变体 | 过滤前非法率 | 策略价值 | uplift RMSE | Qini |
|---|---:|---:|---:|---:|
| gate_consistency=0.0 | 0.070 | 5711 | 0.240 | 0.908 |
| gate_consistency=0.5 | 0.000 | 6604 | 0.364 | 0.898 |
| gate_consistency=2.0 | 0.000 | 6714 | 0.490 | 0.896 |
| eg_chpn_v1_frozen | 0.151 | 6533 | 0.196 | 0.935 |

- 决策：采用 0.5：过滤前非法排序归零、策略价值 +15.6%；RMSE 上升属于设计代价（不可执行动作被要求输出 0），不视为精度退化。
- 注意：单种子缩规模 A/B；全量 10 种子 × 2 DGP 的同变体结果由阶段三 runs_final 产出，且不同损失变体的验证损失不可互相比较。

## 4c 可执行性损失项：生产配置全量确认

- 协议：seeds [13, 29]、3000 客群、hidden 128 / 3 层 / 2000 epoch、GRID[4]（lr 0.003, wd 0.001）

- λ_admissibility=0.0：过滤前非法率 0.402、策略价值 5940、RMSE 0.241、Qini 0.916
- λ_admissibility=0.5：过滤前非法率 0.003、策略价值 15235、RMSE 0.343、Qini 0.912

- **结论：采用**

## 4d AIPW/DR 伪结局监督（方法扩展，实测）

- 协议：seeds 13,29；1500 客群；hidden 96 / 2 层 / 800 epoch；GRID[4]（lr 3e-3, wd 1e-3）；gate_consistency=0.5；selector=none
- 无泄漏说明：伪结局仅由可观测 Y、T、X 与倾向得分构造（ridge 结果模型 + 截断倾向），不使用潜在结果

  | 权重 | pearson | uplift RMSE | Qini | 策略价值 | 验证损失 |
  |---|---:|---:|---:|---:|---:|
  | 0.0 | 0.2112 | 0.3400 | 0.8994 | 7151 | 0.2410 |
  | 1.0 | 0.3972 | 0.2155 | 0.9215 | 6808 | 0.2180 |

- 决策：采用 dr_weight=1.0：验证损失与 CATE 质量（pearson/RMSE/Qini）同时改善；selector=none 的策略价值下降 4.8%，原因是该项恢复了被可执行性项压制的连续增量排序，需在报告中并列披露。
- 注意：双种子缩规模 A/B；全量结果随阶段三 runs_final 产出。

## 4e 同配置多种子集成（出厂形态，实测）

- 协议：成员=runs/v1 中同一配置（GRID[1]）的 10 个种子 checkpoint；每个成员在独立合成总体上训练；在 dgp v1/v2 × 评估种子 13/29 上用同一 policy_metrics_v2 评估；selector=oracle_rule

  | dgp | 单模型价值 | 集成价值 | 单模型 RMSE | 集成 RMSE | 单模型 Qini | 集成 Qini |
  |---|---:|---:|---:|---:|---:|---:|
  | v1 | 15881.1 | 17649.9 | 0.2348 | 0.1870 | 0.9221 | 0.9445 |
  | v2 | 17305.5 | 19185.6 | 0.2908 | 0.2504 | 0.8959 | 0.9233 |

- 运行时一致性：numpy 集成 vs torch 平均最大误差 1.192e-06（容差 1e-05），成员 10 个，权重 12105838 字节。
- 决策：出厂形态改为 10 成员集成：两个 DGP 上策略价值 +11%、RMSE −14~−20%、Qini 一致提升；推理成本为 10 次前向（本机 <1 秒/3000 节点），仍在纯 numpy 与 12MB 权重内。

## 4f 额外算力配对审计（续训是否让模型变好）

- 协议：配对种子训练窗验证损失（早停判据），不读取任何测试窗指标
- 保持不变量：{"n_customers": 3000, "ablation": "none", "method": "marshecho_none"}

  | dgp | 候选（worker） | 基准（worker） | 配对种子 | 基准验证损失 | 候选验证损失 | 差值 | 候选胜出 | 判定 |
  |---|---|---|---:|---:|---:|---:|---:|---|
  | v1 | l1 192×4/6000ep/lr0.003 | w4 128×3/2000ep/lr0.003 | 9 | 0.2051 | 0.2114 | +0.0063 | 2/9 | worse |
  | v1 | l2 128×3/6000ep/lr0.001 | w4 128×3/2000ep/lr0.003 | 10 | 0.2049 | 0.2081 | +0.0032 | 3/10 | worse |
  | v2 | l1 192×4/6000ep/lr0.003 | s1 128×3/2000ep/lr0.003 | 3 | 0.2086 | 0.2252 | +0.0165 | 0/3 | worse |
  | v2 | l2 128×3/6000ep/lr0.001 | s1 128×3/2000ep/lr0.003 | 4 | 0.2185 | 0.2252 | +0.0067 | 1/4 | worse |

- 各 worker 实际 GPU 机时：{"s1": 4.188, "w4": 1.177, "l1": 3.769, "l2": 3.766}
- **结论：延长 epoch 预算后配对验证损失升高。train.py 用 CosineAnnealingLR(T_max=epochs)，把 horizon 从 2000 拉到 6000 会同时抬高同一 epoch 处的学习率，所以更长预算并不包含更短预算的训练轨迹；在预注册配方下 2000 epoch 附近就是拐点，额外算力没有换来模型质量提升。**
- 调度说明：CosineAnnealingLR(T_max=epochs) 使 epoch 预算与学习率轨迹耦合，因此本表比较的是两种完整配方而非同一配方多跑 3× epoch。
- 局限：验证损失是早停判据的复合值（含反事实、平衡与策略项），只作相对排序；最终交付判定仍以下游基准测试的策略价值与 uplift RMSE 配对 A/B 为准。

## 4g 早停审计：多算力为什么不会带来提升

- 证伪：H1（早停判据被拉格朗日惩罚污染）被证伪：在同一组权重上同时记录两种判据的 40 个 run 里，惩罚项对复合判据的平均影响只有 0.000934，两个判据选中的 epoch 在 40/40 个 run 上完全一致，把判据换成去掉惩罚项的质量判据后出厂指标一字未变。
- 成立：H2 成立：验证窗是时间外推窗（拟合窗 days<50，验证窗 50<=days<63），其判据在 2000-epoch 预算下平均第 165.0 epoch 见底、到预算末平均涨 3.55 倍，而同窗内 factual / counterfactual 仍在继续下降——即模型对拟合窗越拟合、对未来窗泛化越差。早停点因此是正确而非过早的，把 epoch 预算拉长不可能带来提升（余弦调度 T_max=epochs 还使长预算的落点更差）。
- 长预算警示：惩罚污染在长预算上真实存在且量级很大（300.0 epoch 选点、复合判据到预算末涨 301.6 倍），但它不改变选点，只使不同 epoch 预算之间的验证损失绝对值不可比——算力审计因此只做同预算内的配对比较。
- 真正有效的杠杆：同一早停点下真正提升出厂指标的是损失配方（可执行性项 λ=0.5 + DR 伪结局监督），配对结果见 marshecho-final-recipe-ab-v2.0.json。

  | 树:预算 | run | 判据 | 平均选点 epoch | 选点位置 | 判据到预算末涨幅 | 拟合窗 factual 前→后 | 拟合窗 cf 前→后 |
  |---|---:|---|---:|---:|---:|---:|---:|
  | runs:2000 | 60 | loss | 159 | 0.082 | 3.99× | 0.0225→0.0182 | 0.0275→0.0002 |
  | runs_final:2000 | 20 | quality | 158 | 0.081 | 4.38× | 0.0245→0.0197 | 0.0320→0.0002 |
  | runs_long:6000 | 26 | loss | 300 | 0.050 | 301.60× | 0.0261→0.0160 | 0.0283→0.0001 |
  | runs_selq_gcdr:2000 | 20 | quality | 190 | 0.097 | 1.40× | 0.0242→0.0195 | 0.0380→0.0079 |
  - 双判据同权重对照：选点一致 runs_final:2000:20/20 + runs_selq_gcdr:2000:20/20；惩罚项对判据的平均影响 0.000821（因此换判据不改出厂结果）

- 分辨率说明：进度文件每 50 个 epoch 保存一行，argmin epoch 以该分辨率报告；fit_window_* 列来自训练窗前向，判据列来自温度 0.2 的时间外推窗评估。

## 4h 出厂候选配对 A/B（测试窗、按种子配对）

- 判定规则：tag=marshecho_none、selector=oracle_rule，按种子配对比较测试窗指标；基线树=runs

  | 候选树 | 改动 | dgp | 配对种子 | 策略价值 前→后 | uplift RMSE 前→后 | Qini 前→后 | 过滤前非法率 前→后 |
  |---|---|---|---:|---:|---:|---:|---:|
  | runs_final | 只换选择判据（去掉拉格朗日惩罚项），配方不变 | v1 | 10 | 15583.7→15583.7 (+0.0) | 0.2205→0.2205 (+0.0000) | 0.9271→0.9271 | 0.330→0.330 |
  | runs_final | 只换选择判据（去掉拉格朗日惩罚项），配方不变 | v2 | 10 | 19410.8→19398.5 (-12.3) | 0.2498→0.2498 (-0.0000) | 0.9273→0.9271 | 0.181→0.181 |
  | runs_selq_gcdr | 选择判据 + 可执行性项 λ=0.5 + DR 伪结局监督 | v1 | 10 | 15583.7→17661.2 (+2077.5) | 0.2205→0.1945 (-0.0260) | 0.9271→0.9465 | 0.330→0.119 |
  | runs_selq_gcdr | 选择判据 + 可执行性项 λ=0.5 + DR 伪结局监督 | v2 | 10 | 19410.8→19967.6 (+556.7) | 0.2498→0.2349 (-0.0149) | 0.9273→0.9411 | 0.181→0.051 |
  - runs_final：指标没有实质变化（相对差 <0.1%）：选中的 epoch 与基线一致，说明换选择判据对出厂结果没有影响；残留差异是 GPU 非确定性量级，不是方法差异
  - runs_selq_gcdr：策略价值 +2077.5、RMSE -0.0260、过滤前非法率 -0.2112：三项同向改善，可以出厂

- **建议：建议用 runs_selq_gcdr 重新导出 10 成员集成并替换出厂权重**
- 注意：10 个种子的配对 bootstrap 区间较宽；过滤前非法率的容差 0.005 是治理口径而非统计结论。

## 5 约束可行性与策略层

- 拉格朗日乘子上界观测：λ_budget max = 50.00
- 部署计划走精确投影（贪心 + 一换一），`/api/algorithms/marshecho/plan` 的 `constraint_violations` 恒为空；软松弛仅用于训练信号，饱和时由投影反标纠正。

## 6 可复制性与数值一致性

- torch ↔ NumPy 前向最大绝对误差：9.5367431640625e-07（容差 1e-05）
- 权重 sha256：`606a7ffefd694decd981221044a18b84ee3e647475e65d1e48b79fd5ce199bc9`
- 参数量：299730；权重体积：12107558 字节
- 推理侧零 torch 依赖：镜像与 CI 均无 torch，`tests/test_eg_chpn_parity.py` 用冻结夹具验证同一函数。

## 7 教师蒸馏（证据门 r_e）

- 判旗准确率（阈值 0.65）：0.8125
- 与文本可判定参考的 Spearman：0.9492；MAE：0.0525
- 硬阻断规则平均 r_e：0.3203；软规则平均：0.6272
- 缓存 sha256：`3bda915be4388d489f2104b6fe79c54494efa8fd03f2845971c3dccf060abab3`（48 行）
- 来源为云端编码代理单次离线生成，**不可复跑**，故以冻存文件 + SHA-256 发布；教师输出永不作为增量效应标签。

## 8 明确排除与局限

- causal forest 与完整 HGT 未实现（依赖不可用），未以近似版本冒充基线。
- 模拟器已知潜在结果函数：无法检验未测混淆、策略干扰、延迟转化、库存截断与渠道送达失败。
- 反事实监督依赖 5% 随机留出，这是模拟器便利；生产环境必须替换为真实 A/B 留出。
- 置信区间为种子级与测试客群配对 bootstrap，不是线上用户级因果区间。
- 在完成系统文献检索与最近方法差异表之前，不使用 novel / first 表述。

## 10 出厂前后对照（同一评估协议）

| dgp | 变体 | 树 | 种子 | 策略价值 | CI | uplift RMSE | Qini | 过滤前非法率(规则) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| v1 | sweep | runs | 10 | 15583.7 | ±1346.2 | 0.2205 | 0.9271 | 0.330 |
| v1 | criterion_ab | runs_final | 10 | 15583.7 | ±1346.2 | 0.2205 | 0.9271 | 0.330 |
| v1 | shipped | runs_selq_gcdr | 10 | 17661.2 | ±882.6 | 0.1945 | 0.9465 | 0.119 |
| v2 | sweep | runs | 10 | 19410.8 | ±1195.4 | 0.2498 | 0.9273 | 0.181 |
| v2 | criterion_ab | runs_final | 10 | 19398.5 | ±1191.2 | 0.2498 | 0.9271 | 0.181 |
| v2 | shipped | runs_selq_gcdr | 10 | 19967.6 | ±1056.8 | 0.2349 | 0.9411 | 0.051 |

- 说明：各行差别在训练配方与选择判据（sweep=旧复合损失早停；shipped=同配方改用质量早停；shipped_adm_dr=质量早停再叠加可执行性项 λ=0.5 与 DR 伪结局权重 1.0），数据、种子、评估协议完全相同；不同损失变体的验证损失不可互相比较，因此改善以 Qini / RMSE / 非法率并列报告。

## 9 复现命令

```bash
bash research/egchpn_torch/launch_sweep.sh            # 阶段一扫描
bash scripts/continue_training.sh                      # 阶段二/三续训与重导出
python research/egchpn_torch/export_weights.py         # 导出 .npz + parity 夹具
python scripts/select_best_checkpoint.py --export      # 按验证损失选出厂检查点
python scripts/build_marshecho_report.py               # 出表
python scripts/verify_marshecho_v2.py                  # 不变量校验
python scripts/package_marshecho_bundle.py             # 可复制离线包
python -m pytest -q                                    # 无 torch 全量回归
```
