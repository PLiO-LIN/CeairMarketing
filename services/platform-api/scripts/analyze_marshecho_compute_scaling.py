"""Was the extra compute actually worth it?  Paired validation-loss audit.

The continuation chain trained two larger/longer candidate configurations
(6000 epochs instead of 2000, hidden 192 x 4 layers and hidden 128 x 3) to
test the assumption that more GPU time gives a better Marsh-Echo model.  This
script compares every candidate against the shipped sweep configuration on the
seeds they share, so the comparison is paired rather than a mean over different
seed sets, and writes the result as a provenance artifact.

Validation loss is the training-window early-stopping criterion only; no test
metric is consulted here.  All trees use the same simulated audience size
(n_customers=3000) and the same dgp, so the two axes that move are capacity and
epoch budget.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[1] / "docs" / "实验" / "marshecho-compute-scaling-v2.0.json"
DIRS = {"runs": "research/egchpn_torch/runs", "runs_long": "research/egchpn_torch/runs_long"}
# worker -> (hidden, layers, epochs, lr) as launched by the chain scripts.
WORKERS = {
    "w4": {"hidden": 128, "layers": 3, "epochs": 2000, "lr": 0.003, "role": "shipped sweep (gap fill)"},
    "s1": {"hidden": 128, "layers": 3, "epochs": 2000, "lr": 0.003, "role": "shipped sweep (dgp v2)"},
    "l1": {"hidden": 192, "layers": 4, "epochs": 6000, "lr": 0.003, "role": "long/large candidate"},
    "l2": {"hidden": 128, "layers": 3, "epochs": 6000, "lr": 0.001, "role": "long candidate, lower lr"},
}
BASELINES = {"v1": "w4", "v2": "s1"}


def load() -> Dict[Tuple[str, str], Dict[int, float]]:
    out: Dict[Tuple[str, str], Dict[int, float]] = {}
    for tree, rel in DIRS.items():
        base = ROOT / rel
        if not base.is_dir():
            continue
        for manifest in sorted(base.glob("manifest_*.jsonl")):
            worker = manifest.stem.replace("manifest_", "")
            if worker not in WORKERS:
                continue
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("method") != "marshecho_none":
                    continue
                key = (worker, str(record.get("dgp")))
                out.setdefault(key, {})[int(record["seed"])] = float(record["best_val"])
    return out


def paired(data: Dict[Tuple[str, str], Dict[int, float]], dgp: str) -> List[dict]:
    baseline = BASELINES[dgp]
    ref = data.get((baseline, dgp), {})
    rows: List[dict] = []
    for worker in sorted(WORKERS):
        if worker == baseline:
            continue
        other = data.get((worker, dgp), {})
        shared = sorted(set(ref) & set(other))
        if not shared:
            continue
        deltas = [other[s] - ref[s] for s in shared]
        mean_delta = statistics.fmean(deltas)
        spread = statistics.pstdev(deltas) if len(deltas) > 1 else 0.0
        rows.append(
            {
                "dgp": dgp,
                "baseline_worker": baseline,
                "candidate_worker": worker,
                "candidate": WORKERS[worker],
                "baseline": WORKERS[baseline],
                "seeds_paired": len(shared),
                "baseline_mean_best_val": round(statistics.fmean(ref[s] for s in shared), 6),
                "candidate_mean_best_val": round(statistics.fmean(other[s] for s in shared), 6),
                "mean_delta": round(mean_delta, 6),
                "std_delta": round(spread, 6),
                "candidate_wins": int(sum(1 for d in deltas if d < 0.0)),
                "verdict": "improved" if mean_delta < 0.0 else "worse",
                "per_seed": {str(s): {"baseline": round(ref[s], 6), "candidate": round(other[s], 6)} for s in shared},
            }
        )
    return rows


def main() -> None:
    data = load()
    comparisons = paired(data, "v1") + paired(data, "v2")
    wall = {}
    for tree, rel in DIRS.items():
        base = ROOT / rel
        if not base.is_dir():
            continue
        for manifest in sorted(base.glob("manifest_*.jsonl")):
            worker = manifest.stem.replace("manifest_", "")
            if worker not in WORKERS:
                continue
            seconds = [float(json.loads(line).get("wall_seconds", 0.0)) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
            wall[worker] = round(sum(seconds) / 3600.0, 3)
    worse = [c for c in comparisons if c["verdict"] == "worse"]
    payload = {
        "synthetic": True,
        "label": "流程验证（虚构）",
        "question": "6000-epoch / higher-capacity candidates 是否优于已导出的 2000-epoch 配置",
        "decision_rule": "配对种子训练窗验证损失（早停判据），不读取任何测试窗指标",
        "constant_across_trees": {"n_customers": 3000, "ablation": "none", "method": "marshecho_none"},
        "comparisons": comparisons,
        "gpu_hours_per_worker": wall,
        "summary": {
            "comparisons": len(comparisons),
            "worse_than_shipped": len(worse),
            "mean_delta_best_val": round(statistics.fmean(c["mean_delta"] for c in comparisons), 6) if comparisons else None,
            "conclusion": (
                "延长 epoch 预算后配对验证损失升高。train.py 用 CosineAnnealingLR(T_max=epochs)，"
                "把 horizon 从 2000 拉到 6000 会同时抬高同一 epoch 处的学习率，"
                "所以更长预算并不包含更短预算的训练轨迹；在预注册配方下 2000 epoch 附近就是拐点，"
                "额外算力没有换来模型质量提升。"
                if len(worse) == len(comparisons) and comparisons
                else "候选配置在部分配对上优于基准，需以基准测试指标复核后再决定是否重导出。"
            ),
        },
        "lr_schedule_note": "CosineAnnealingLR(T_max=epochs) 使 epoch 预算与学习率轨迹耦合，"
        "因此本表比较的是两种完整配方而非同一配方多跑 3× epoch。",
        "limitation": "验证损失是早停判据的复合值（含反事实、平衡与策略项），只作相对排序；"
        "最终交付判定仍以下游基准测试的策略价值与 uplift RMSE 配对 A/B 为准。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(comparisons)} worse={len(worse)} -> {OUT.name}")
    for c in comparisons:
        print(f"  {c['dgp']} {c['candidate_worker']}({c['candidate']['epochs']}ep h{c['candidate']['hidden']}x{c['candidate']['layers']}) "
              f"vs {c['baseline_worker']}: n={c['seeds_paired']} delta={c['mean_delta']:+.6f} wins={c['candidate_wins']} -> {c['verdict']}")


if __name__ == "__main__":
    main()
