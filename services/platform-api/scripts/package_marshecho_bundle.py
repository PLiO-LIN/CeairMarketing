"""Package Marsh-Echo (九皋) as a self-contained, copyable model bundle.

The bundle runs on NumPy alone: weights, the torch-free runtime, the parity
fixture, a verifier, the model card and the licence.  It is written with
``zipfile`` so entry names keep their UTF-8 form on Windows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
WEIGHTS = ROOT / "app" / "algorithms" / "weights"
EXPERIMENTS = REPO / "docs" / "实验"

VERIFY_SOURCE = '''"""One-command verification of the Marsh-Echo (九皋) bundle.

Usage:  python verify_bundle.py
Requires only numpy>=2.0; no torch, no GPU, no network.
"""

from pathlib import Path
import hashlib
import json
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "runtime"))


def main() -> int:
    from eg_chpn_runtime import EGCHPNRuntime

    manifest = json.loads((HERE / "marshecho_v2_0.manifest.json").read_text(encoding="utf-8"))
    weights = HERE / "marshecho_v2_0.npz"
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    if digest != manifest["sha256"]:
        print(f"FAIL sha256 mismatch: {digest} != {manifest['sha256']}")
        return 1
    runtime = EGCHPNRuntime.load(weights)
    fixture = np.load(HERE / "marshecho_v2_parity.npz")
    got = runtime.forward_arrays(
        fixture["x"], fixture["type_ids"], fixture["H"], fixture["H_norm"],
        fixture["attrs"], fixture["hard_mask"], fixture["delta"], fixture["rel_ids"],
    )
    worst = 0.0
    for key in ("g_raw", "g", "h1", "h0", "tau", "y1", "y0", "score", "z"):
        if not np.isfinite(got[key]).all():
            print(f"FAIL {key} contains non-finite values")
            return 1
        worst = max(worst, float(np.max(np.abs(got[key] - fixture[key]))))
    if worst > 1e-5:
        print(f"FAIL parity difference {worst:.3e} exceeds 1e-5")
        return 1
    blocked = np.flatnonzero(fixture["hard_mask"] == 0)
    if blocked.size and not (got["g"][blocked] == 0).all():
        print("FAIL semantic hard mask did not zero ineligible paths")
        return 1
    meta = runtime.meta
    print("PASS marshecho bundle verified")
    print(f"  model      : {meta['model']['name_zh']} ({meta['model']['name']} / {meta['model']['paper_name']})")
    print(f"  schema     : {meta['schema_version']}")
    parameters = manifest.get("parameters") or manifest.get("parameters_per_member")
    members = manifest.get("members", 1)
    print(f"  parameters : {parameters} per member x {members} members")
    print(f"  sha256     : {digest[:16]}...")
    print(f"  parity max : {worst:.3e} (tolerance 1e-5)")
    print(f"  masked     : {blocked.size} ineligible paths gated to exactly 0")
    print(f"  evidence   : {meta['label']} / synthetic={meta['synthetic']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

README = """# Marsh-Echo（九皋）可复制模型包

架构：EG-CHPN v2（证据门控反事实超图策略网络）。推理只需 `numpy>=2.0`，
不需要 torch、GPU 或网络。

```bash
pip install "numpy>=2.0"
python verify_bundle.py
```

加载并打分：

```python
import sys; sys.path.insert(0, "runtime")
from eg_chpn_runtime import EGCHPNRuntime
runtime = EGCHPNRuntime.load("marshecho_v2_0.npz")
# forward_arrays(x, type_ids, H, H_norm, attrs, hard_mask, delta, rel_ids)
```

## 数据与结论边界

- 本体实体与业务规则口径来自真实民航营销业务资料；
- **结果变量（潜在结果、处理分配、回执、收入）全部由模拟器生成**；
- 因此包内所有指标口径为【流程验证（虚构）】，不构成真实经营提升证据。

许可证：Apache-2.0（代码与权重）、CC-BY-4.0（教师冻存缓存文本），见 LICENSE 与 NOTICE。
"""


def model_card() -> str:
    manifest = json.loads((WEIGHTS / "marshecho_v2_0.manifest.json").read_text(encoding="utf-8"))
    parity = {}
    parity_path = EXPERIMENTS / "marshecho-runtime-parity-v2.0.json"
    if parity_path.exists():
        parity = json.loads(parity_path.read_text(encoding="utf-8"))
    teacher = {}
    teacher_path = EXPERIMENTS / "marshecho-teacher-distill-v2.0.json"
    if teacher_path.exists():
        teacher = json.loads(teacher_path.read_text(encoding="utf-8"))
    sweep = {}
    summary_path = ROOT / "research" / "egchpn_torch" / "runs" / "sweep_summary_w1.json"
    if summary_path.exists():
        sweep = json.loads(summary_path.read_text(encoding="utf-8"))
    lines = [
        "# Marsh-Echo（九皋）模型卡",
        "",
        f"- 模型标识：marshecho（中文：九皋）；论文英文名：Marsh-Echo",
        f"- 架构：EG-CHPN v2 — 证据门控反事实超图策略网络",
        f"- schema：{manifest.get('schema_version')}",
        f"- 参数量：{manifest.get('parameters_per_member') or manifest.get('parameters')}（成员数 {manifest.get('members', 1)}，同配置多种子 τ̂ 平均）",
        f"- 权重 sha256：`{manifest.get('sha256')}`",
        f"- 权重体积：{manifest.get('bytes')} 字节（开放格式 .npz，allow_pickle=False）",
        f"- 运行时：纯 NumPy（`app/algorithms/eg_chpn_runtime.py`），镜像内无 torch",
        f"- 许可证：Apache-2.0（代码与权重）；教师冻存缓存 CC-BY-4.0",
        "",
        "## 训练与复现",
        "",
        f"- 训练栈：torch {sweep.get('torch', '2.9.1+cu128')} / CUDA {sweep.get('cuda', True)}，RTX 5070 Ti Laptop 12GB",
        "- 确定性：固定种子、`use_deterministic_algorithms(True, warn_only=True)`、`CUBLAS_WORKSPACE_CONFIG=:4096:8`、全批量、`num_workers=0`",
        f"- 扫描总 GPU 时长：{sweep.get('total_wall_seconds', '见 runs/sweep_summary_*.json')} 秒（w1 工作线程）",
        "- 复现：`python scripts/reproduce_marshecho.py`（同机同版本应得同一 sha256）",
        "",
        "## 数值一致性",
        "",
        f"- torch↔NumPy 前向最大绝对误差：{parity.get('max_abs_difference', 'pending')}（容差 1e-5）",
        f"- 语义硬掩码：pending/ineligible 路径的门控值精确为 0（不可由分数补偿）",
        "",
        "## 数据与结论边界",
        "",
        "- 本体实体与业务规则口径来自真实民航营销业务资料；**结果变量（潜在结果、处理分配、回执、收入）全部由模拟器生成**。",
        "- 因此所有指标口径为【流程验证（虚构）】，不构成真实航司经营提升证据；论文中的置信区间为种子级/测试客群配对 bootstrap，不是线上用户级因果区间。",
        "",
        "## 教师蒸馏（证据门 rule_agreement）",
        "",
        f"- 来源：{teacher.get('cache', {}).get('sha256') and '云端编码代理单次离线生成并冻存' or 'pending'}；缓存 sha256 `{teacher.get('cache', {}).get('sha256', 'pending')[:16]}`；行数 {teacher.get('cache', {}).get('rows', 0)}",
        f"- 探针：判旗准确率 {teacher.get('probe', {}).get('flag_decision_accuracy', 'pending')}，Spearman {teacher.get('probe', {}).get('spearman_vs_reference', 'pending')}，MAE {teacher.get('probe', {}).get('mean_abs_error', 'pending')}",
        "- 用途：仅作为证据门 r_e 的先验与解释文案，不作为增量效应标签。",
        "",
        "## 已知局限",
        "",
        "- 未做系统文献检索与最近方法对照前，不使用 novel/first 表述。",
        "- 模拟器已知潜在结果函数，无法处理未测混淆、策略干扰、延迟转化、库存截断与渠道送达失败。",
        "- causal forest 与完整 HGT 未实现（依赖不可用），已在实验报告与论文中明示。",
        f"- 打包时间：{datetime.now(timezone.utc).isoformat()}",
    ]
    return "\n".join(lines) + "\n"


NOTICE = """Marsh-Echo (九皋) — EG-CHPN v2 research artefacts
Copyright 2026 丽娃谷风队 (YanYan / CeairMarketing research track)

This product includes research software and model weights developed for the
ontology-constrained airline marketing policy study, licensed under the
Apache License, Version 2.0.

The distilled teacher cache (research/egchpn_torch/cache/teacher_cloud_frozen.json)
is redistributed under CC-BY-4.0; it was produced in a single offline pass by a
cloud coding agent and is therefore not reproducible by re-calling a model.
Reproducibility is preserved by shipping the frozen cache together with its
SHA-256 digest.

All outcome variables used to train the shipped weights are simulated; see
MODEL_CARD.md for the evidence boundary and the required labelling convention.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(REPO.parent / "答辩材料" / "marshecho_v2_0_bundle.zip"))
    args = parser.parse_args()
    stage = ROOT / "research" / "egchpn_torch" / "marshecho_v2_0"
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "runtime").mkdir(parents=True)
    shutil.copy2(WEIGHTS / "marshecho_v2_0.npz", stage / "marshecho_v2_0.npz")
    shutil.copy2(WEIGHTS / "marshecho_v2_0.manifest.json", stage / "marshecho_v2_0.manifest.json")
    shutil.copy2(ROOT / "tests" / "fixtures" / "marshecho_v2_parity.npz", stage / "marshecho_v2_parity.npz")
    for name in ("eg_chpn_runtime.py", "hypergraph_spec.py", "oth_gct.py", "eg_chpn.py"):
        shutil.copy2(ROOT / "app" / "algorithms" / name, stage / "runtime" / name)
    (stage / "runtime" / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "app" / "ontology" / "semantic_model.py", stage / "runtime" / "semantic_model_shim.py")
    (stage / "verify_bundle.py").write_text(VERIFY_SOURCE, encoding="utf-8")
    (stage / "MODEL_CARD.md").write_text(model_card(), encoding="utf-8")
    (stage / "README.md").write_text(README, encoding="utf-8")
    (stage / "NOTICE").write_text(NOTICE, encoding="utf-8")
    shutil.copy2(ROOT / "research" / "egchpn_torch" / "APACHE-2.0.txt", stage / "LICENSE")
    (stage / "requirements-min.txt").write_text("numpy>=2.0\n", encoding="utf-8")
    provenance = stage / "provenance"
    provenance.mkdir()
    research = ROOT / "research" / "egchpn_torch"
    shutil.copy2(research / "cache" / "teacher_cloud_frozen.json", provenance / "teacher_cloud_frozen.json")
    shutil.copy2(research / "rule_catalog.py", provenance / "rule_catalog.py")
    shutil.copy2(research / "teacher_cloud.py", provenance / "teacher_cloud.py")
    shutil.copy2(EXPERIMENTS / "marshecho-teacher-distill-v2.0.json", provenance / "marshecho-teacher-distill-v2.0.json")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage.parent).as_posix())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({"bundle": str(out), "sha256": digest, "bytes": out.stat().st_size}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
