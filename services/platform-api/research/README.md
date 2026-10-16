# Marsh-Echo（九皋）研究线运行手册

架构：**EG-CHPN v2**（证据门控反事实超图策略网络）。模型实例名 **marshecho / 九皋**，
论文英文名 **Marsh-Echo**。本目录是训练侧代码，**不进 Docker 镜像、不被 `app/` 或
`tests/` 导入**（镜像与 CI 都没有 torch）。

## 目录

```
research/egchpn_torch/
  model.py            超图注意力 + 证据门 + 反事实双塔 + 策略头（可端到端训练）
  losses.py           五项损失：factual / balance / counterfactual / evidence / policy
  data.py             模拟器 → 张量适配（超图模式与二元 clique 展开模式）
  train.py            训练编排：超参网格、消融、基线、断点落盘、manifest
  baselines.py        TARNet / DragonNet / 训练版 GAT（HGT 与 causal forest 明确排除）
  export_weights.py   导出 app/algorithms/weights/marshecho_v2_0.npz + parity fixture
  teacher_cloud.py    云端教师冻存缓存与 rule_agreement 蒸馏探针
  rule_catalog.py     业务规则文本目录（教师判定的输入与文本可判定 oracle）
  launch_sweep.sh     三 worker 并行扫描启动脚本
```

配套：`scripts/run_eg_chpn_simulation_v2.py`（numpy 基线与 2×2 因子）、
`scripts/build_marshecho_report.py`（出表）、`scripts/verify_marshecho_v2.py`（不变量）、
`scripts/reproduce_marshecho.py`（复现）、`scripts/package_marshecho_bundle.py`（可复制包）。

## 环境

```bash
python -m venv D:/venv/egchpn
D:/venv/egchpn/Scripts/python.exe -m pip install torch==2.9.1+cu128 \
  --index-url https://mirror.sjtu.edu.cn/pytorch-wheels/cu128 \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple/
D:/venv/egchpn/Scripts/python.exe -c "import torch;print(torch.cuda.is_available())"
```

推理侧只需 `numpy>=2.0`（`D:/venv/ceair` 或任意 numpy 环境）。**不要**把 torch 写进
`requirements.txt`：CI 与镜像必须保持无 torch。

## 训练

```bash
cd services/platform-api
bash research/egchpn_torch/launch_sweep.sh      # 3 worker，日志 w1/w2/w3.log
```

规模：10 种子 × 2 DGP ×（7 组预注册超参网格 + 11 个消融 + 3 个 torch 基线）。
每个 run 独立落盘（`runs/<dgp>/scores_*.npz`、`progress_*.jsonl`、`manifest_<worker>.jsonl`），
中断后可继续，已完成部分仍可用于出表。

确定性设置：固定种子、`CUBLAS_WORKSPACE_CONFIG=:4096:8`、`PYTHONHASHSEED=0`、
`use_deterministic_algorithms(True, warn_only=True)`、全批量、`num_workers=0`。

## 导出与验证

```bash
D:/venv/egchpn/Scripts/python.exe -B research/egchpn_torch/export_weights.py
D:/venv/ceair/Scripts/python.exe -B scripts/build_marshecho_report.py
D:/venv/ceair/Scripts/python.exe -B scripts/verify_marshecho_v2.py
D:/venv/ceair/Scripts/python.exe -B scripts/run_eg_chpn_simulation_v2.py
D:/venv/ceair/Scripts/python.exe -m pytest -q          # 与 CI 等价（无 torch）
D:/venv/egchpn/Scripts/python.exe -B scripts/reproduce_marshecho.py
```

`export_weights.py` 同时写 `tests/fixtures/marshecho_v2_parity.npz`：CI 里没有 torch，
靠这份 fixture 证明 `app/algorithms/eg_chpn_runtime.py` 的纯 numpy 前向与训练时同函数
（容差 1e-5）。

## 可复制交付

```bash
D:/venv/ceair/Scripts/python.exe -B scripts/package_marshecho_bundle.py
# → D:/企业管理创新大赛/答辩材料/marshecho_v2_0_bundle.zip
# 解压后：pip install "numpy>=2.0" && python verify_bundle.py
```

## 证据口径

- 本体实体与业务规则口径来自真实民航营销业务资料；**结果变量全部由模拟器生成**。
- 所有 v2 工件带 `"synthetic": true`，引用数字必须标【流程验证（虚构）】。
- 教师蒸馏缓存为云端代理单次离线生成，不可复跑，故以冻存文件 + SHA-256 形式发布。
- 未完成系统文献检索与最近方法对照前，不使用 novel / first 表述。

## 许可证

代码与权重 Apache-2.0（见 `LICENSE`、`NOTICE`）；教师冻存缓存文本 CC-BY-4.0。
