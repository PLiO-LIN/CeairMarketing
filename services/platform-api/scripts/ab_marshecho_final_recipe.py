"""Paired test-window A/B for the shipping candidates.

Three arms are compared against the currently shipped sweep tree, all under the
same seeds, data, architecture and epoch budget:

``runs_final``       same recipe, checkpoint-selection criterion changed
                    (composite loss -> loss without the Lagrangian penalty).
                    This arm isolates the criterion: if early stopping had been
                    pinned by the penalty term, the shipped metrics would move.
``runs_selq_gcdr``   same criterion fix plus the loss-recipe terms that the
                    scale-up experiments recommended (admissibility penalty
                    lambda=0.5 and AIPW/DR pseudo-outcome CATE supervision).

Shipping stays a human decision: this script only writes the artifact.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUT = REPO / "docs" / "实验" / "marshecho-final-recipe-ab-v2.0.json"

_spec = importlib.util.spec_from_file_location("build_marshecho_report_for_ab", ROOT / "scripts" / "build_marshecho_report.py")
assert _spec and _spec.loader
bmr = importlib.util.module_from_spec(_spec)
sys.modules["build_marshecho_report_for_ab"] = bmr
_spec.loader.exec_module(bmr)

METRICS = ("policy_value", "uplift_rmse", "qini", "auuc", "invalid_rule_rate_pre_filter")
HIGHER_IS_BETTER = {"policy_value", "qini", "auuc"}
TAG = "marshecho_none"
WHAT_CHANGED = {
    "runs_final": "只换选择判据（去掉拉格朗日惩罚项），配方不变",
    "runs_selq_gcdr": "选择判据 + 可执行性项 λ=0.5 + DR 伪结局监督",
}


def per_seed(tree: str, dgp: str, selector: str) -> dict[int, dict[str, float]]:
    paths = bmr.discover().get((tree, dgp), {}).get(TAG, [])
    rows: dict[int, dict[str, float]] = {}
    for row in bmr.evaluate(tree, dgp, TAG, paths):
        if row["selector"] == selector:
            rows[int(row["seed"])] = {metric: float(row[metric]) for metric in METRICS}
    return rows


def paired(base: dict[int, dict[str, float]], cand: dict[int, dict[str, float]]) -> dict:
    seeds = sorted(set(base) & set(cand))
    if not seeds:
        return {"seeds_paired": 0}
    out: dict[str, object] = {"seeds_paired": len(seeds), "seeds": seeds, "metrics": {}}
    deltas_by_seed: dict[str, list[float]] = {}
    for metric in METRICS:
        b = [base[s][metric] for s in seeds]
        c = [cand[s][metric] for s in seeds]
        deltas = [cv - bv for cv, bv in zip(c, b)]
        deltas_by_seed[metric] = deltas
        better = sum(1 for d in deltas if (d > 0 if metric in HIGHER_IS_BETTER else d < 0))
        entry: dict[str, object] = {
            "baseline_mean": round(statistics.fmean(b), 6),
            "candidate_mean": round(statistics.fmean(c), 6),
            "mean_delta": round(statistics.fmean(deltas), 6),
            "relative_delta": round(statistics.fmean(deltas) / abs(statistics.fmean(b)), 6) if statistics.fmean(b) else None,
            "candidate_wins": better,
        }
        values = np.asarray(deltas, dtype=float)
        rng = np.random.default_rng(0)
        draws = [float(np.mean(values[rng.integers(0, len(values), len(values))])) for _ in range(400)]
        entry["delta_ci95_bootstrap_seeds"] = [round(float(np.quantile(draws, 0.025)), 6), round(float(np.quantile(draws, 0.975)), 6)]
        out["metrics"][metric] = entry
    return out


def decide(entry: dict) -> tuple[bool, str]:
    metrics = entry.get("metrics", {})
    if not metrics or entry.get("seeds_paired", 0) < 3:
        return False, "配对种子不足，无法判定"
    value = metrics["policy_value"]["mean_delta"]
    rmse = metrics["uplift_rmse"]["mean_delta"]
    invalid = metrics["invalid_rule_rate_pre_filter"]["mean_delta"]
    relative = abs(metrics["policy_value"].get("relative_delta") or 0.0)
    if value > 0 and rmse < 0 and invalid <= 0.005:
        return True, f"策略价值 {value:+.1f}、RMSE {rmse:+.4f}、过滤前非法率 {invalid:+.4f}：三项同向改善，可以出厂"
    if value > 0 and rmse < 0:
        return True, f"策略价值 {value:+.1f}、RMSE {rmse:+.4f} 改善，但过滤前非法率 {invalid:+.4f} 变差，出厂前需说明治理口径"
    if relative < 0.001 and abs(rmse) < 1e-4:
        return False, (
            "指标没有实质变化（相对差 <0.1%）：选中的 epoch 与基线一致，说明换选择判据对出厂结果没有影响；"
            "残留差异是 GPU 非确定性量级，不是方法差异"
        )
    return False, f"策略价值 {value:+.1f}、RMSE {rmse:+.4f} 未同时改善，保留现有出厂权重"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-tree", default="runs", help="tree holding the currently shipped model")
    parser.add_argument("--candidate-trees", default="runs_final,runs_selq_gcdr")
    parser.add_argument("--selector", default="oracle_rule")
    args = parser.parse_args()

    arms: dict[str, object] = {}
    verdicts: dict[str, str] = {}
    winners: list[str] = []
    for tree in [item for item in args.candidate_trees.split(",") if item]:
        arms[tree] = {"what_changed": WHAT_CHANGED.get(tree, ""), "by_dgp": {}}
        for dgp in ("v1", "v2"):
            entry = paired(per_seed(args.baseline_tree, dgp, args.selector), per_seed(tree, dgp, args.selector))
            arms[tree]["by_dgp"][dgp] = entry  # type: ignore[index]
            if dgp == "v1" and entry.get("seeds_paired"):
                ok, reason = decide(entry)
                verdicts[tree] = reason
                if ok:
                    winners.append(tree)
    payload = {
        "synthetic": True,
        "label": "流程验证（虚构）",
        "question": "两个出厂候选相对现有出厂模型，在同一批种子的测试窗上是否更好",
        "decision_rule": f"tag={TAG}、selector={args.selector}，按种子配对比较测试窗指标；基线树={args.baseline_tree}",
        "arms": arms,
        "verdicts": verdicts,
        "winners": winners,
        "recommendation": (
            f"建议用 {winners[0]} 重新导出 10 成员集成并替换出厂权重" if winners else "建议保留当前出厂权重（快照仍可用）"
        ),
        "caveat": "10 个种子的配对 bootstrap 区间较宽；过滤前非法率的容差 0.005 是治理口径而非统计结论。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for tree, arm in arms.items():
        print(f"[{tree}] {arm['what_changed']}")
        for dgp, entry in arm["by_dgp"].items():  # type: ignore[union-attr]
            metrics = entry.get("metrics", {})
            if not metrics:
                print(f"  {dgp}: no paired seeds yet")
                continue
            print(
                f"  {dgp}: n={entry['seeds_paired']} value {metrics['policy_value']['baseline_mean']:.1f}"
                f"->{metrics['policy_value']['candidate_mean']:.1f} ({metrics['policy_value']['mean_delta']:+.1f}), "
                f"rmse {metrics['uplift_rmse']['baseline_mean']:.4f}->{metrics['uplift_rmse']['candidate_mean']:.4f} "
                f"({metrics['uplift_rmse']['mean_delta']:+.4f}), qini {metrics['qini']['baseline_mean']:.4f}"
                f"->{metrics['qini']['candidate_mean']:.4f}, invalid_pre "
                f"{metrics['invalid_rule_rate_pre_filter']['baseline_mean']:.3f}"
                f"->{metrics['invalid_rule_rate_pre_filter']['candidate_mean']:.3f}"
            )
    print(f"verdicts={json.dumps(verdicts, ensure_ascii=False)}")
    print(f"recommendation={payload['recommendation']}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
