"""Assemble the Marsh-Echo (九皋) v2 experiment artifacts without torch.

Reads the per-run test-window scores written by the training sweep, re-derives
the identical simulated population from each run's own size, evaluates every
row through the shared ``policy_metrics_v2`` selector interface, and emits the
ablation table, the gate x selector factorial, the constraint report and the
runtime parity evidence.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("eg_chpn_v2", ROOT / "scripts" / "run_eg_chpn_simulation_v2.py")
_v2 = importlib.util.module_from_spec(_spec)
sys.modules["eg_chpn_v2"] = _v2
assert _spec.loader is not None
_spec.loader.exec_module(_v2)

TREES = {
    "runs": ROOT / "research" / "egchpn_torch" / "runs",
    "runs_final": ROOT / "research" / "egchpn_torch" / "runs_final",
    "runs_selq_gcdr": ROOT / "research" / "egchpn_torch" / "runs_selq_gcdr",
}
# The installed weights come from one particular tree, and that changes whenever
# a candidate wins a paired A/B, so the label is resolved from the environment
# instead of being hard-coded to a directory name.
SHIPPED_TREE = os.environ.get("MARSHECHO_SHIPPED_TREE", "runs_selq_gcdr")
TREE_LABEL = {"runs": "sweep", "runs_final": "criterion_ab", "runs_selq_gcdr": "recipe_ab", "runs_long": "long_ab"}


def variant_of(tree: str) -> str:
    return "shipped" if tree == SHIPPED_TREE else TREE_LABEL.get(tree, tree)


VARIANTS = TREE_LABEL
OUT = REPO / "docs" / "实验"
SELECTORS = ("none", "oracle_rule", "oracle_both")
UNLEARNED_GATE_TAGS = {"marshecho_no_gate"}


def _gate(tag: str) -> str:
    return "none" if tag in UNLEARNED_GATE_TAGS else "learned"


def discover() -> dict[tuple[str, str], dict[str, list[Path]]]:
    """Map (tree, dgp) -> tag -> score files.

    The shipped variant lives in ``runs_final``; if it were skipped, the tables
    would describe a model that is no longer the one being exported.
    """

    found: dict[tuple[str, str], dict[str, list[Path]]] = {}
    for tree, root in TREES.items():
        for dgp in ("v1", "v2"):
            directory = root / dgp
            if not directory.exists():
                continue
            by_tag: dict[str, list[Path]] = {}
            for path in sorted(directory.glob("scores_*_seed*.npz")):
                match = re.fullmatch(r"scores_(.+)_seed(\d+)\.npz", path.name)
                if not match:
                    continue
                by_tag.setdefault(match.group(1), []).append(path)
            if by_tag:
                found[(tree, dgp)] = by_tag
    return found


def evaluate(tree: str, dgp: str, tag: str, paths: list[Path]) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    for path in paths:
        seed = int(re.fullmatch(r"scores_(.+)_seed(\d+)\.npz", path.name).group(2))
        payload = np.load(path)
        n_customers = int(payload["tau"].shape[0])
        sim = _v2.simulate(seed, n_customers=n_customers, dgp=dgp)
        test = np.flatnonzero(sim.days >= _v2.TRAIN_DAYS)
        tau = payload["tau"][test]
        factual = payload["factual"][test]
        for selector in SELECTORS:
            metrics = _v2.policy_metrics_v2(sim, test, tau, selector=selector, factual_logit=factual)
            rows.append(
                {
                    "seed": seed,
                    "dgp": dgp,
                    "tree": tree,
                    "variant": variant_of(tree),
                    "method": tag,
                    "gate": _gate(tag),
                    "selector": selector,
                    "population": n_customers,
                    "test_n": len(test),
                    **metrics,
                }
            )
    return rows


def aggregate(rows: list[dict[str, float | int | str]]) -> list[dict[str, float | int | str]]:
    keys = sorted({(str(r["tree"]), str(r["dgp"]), str(r["method"]), str(r["gate"]), str(r["selector"])) for r in rows})
    summary = []
    for tree, dgp, method, gate, selector in keys:
        subset = [r for r in rows if (str(r["tree"]), str(r["dgp"]), str(r["method"]), str(r["gate"]), str(r["selector"])) == (tree, dgp, method, gate, selector)]
        item: dict[str, float | int | str] = {
            "tree": tree,
            "variant": variant_of(tree),
            "dgp": dgp,
            "method": method,
            "gate": gate,
            "selector": selector,
            "n_seeds": len(subset),
            "population": int(subset[0]["population"]),
        }
        for metric in ("policy_value", "uplift_rmse", "topk_true_uplift", "invalid_rule_rate_pre_filter", "invalid_latent_rate_pre_filter", "invalid_rule_rate_selected", "qini", "auuc"):
            values = np.asarray([float(r[metric]) for r in subset], dtype=float)
            item[f"{metric}_mean"] = float(values.mean())
            item[f"{metric}_ci95"] = float(1.96 * values.std(ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
        summary.append(item)
    return summary


FACTORIAL_TAGS = {"learned": "marshecho_none", "none": "marshecho_no_gate"}


def factorial(summary: list[dict[str, float | int | str]]) -> dict[str, object]:
    """2x2 {learned gate, no gate} x {selector} for the shipped variant if present."""

    cells: dict[str, object] = {}
    for tree in (SHIPPED_TREE, "runs_selq_gcdr", "runs_final", "runs"):
        if any(row["tree"] == tree for row in summary):
            break
    for gate, tag in FACTORIAL_TAGS.items():
        for selector in SELECTORS:
            match = [row for row in summary if row["gate"] == gate and row["selector"] == selector and row["dgp"] == "v1" and row["method"] == tag and row["tree"] == tree]
            if not match:
                continue
            row = match[0]
            cells[f"{gate}|{selector}"] = {
                "method": row["method"],
                "policy_value": row["policy_value_mean"],
                "policy_value_ci95": row["policy_value_ci95"],
                "invalid_rule_rate_pre_filter": row["invalid_rule_rate_pre_filter_mean"],
                "invalid_rule_rate_selected": row["invalid_rule_rate_selected_mean"],
                "invalid_latent_rate_pre_filter": row["invalid_latent_rate_pre_filter_mean"],
                "qini": row["qini_mean"],
                "tree": row["tree"],
                "variant": row["variant"],
            }
    return {
        "design": "gate {learned, none} x selector {none, oracle_rule, oracle_both}; invalid rates reported pre-filter",
        "cells": cells,
        "reading": "只有当 learned 门在 selector=none 时也压低非法选择率，证据门本身才算被证明；selector 打开时的差异来自过滤器的作用范围。",
    }


def constraints() -> dict[str, object]:
    runs: list[dict[str, object]] = []
    for root in TREES.values():
        for path in sorted(root.glob("manifest_*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                runs.append(
                    {
                        "worker": path.stem.replace("manifest_", ""),
                        "tree": root.name,
                        "seed": record.get("seed"),
                        "dgp": record.get("dgp"),
                        "method": record.get("method"),
                        "best_val": record.get("best_val"),
                        "wall_seconds": record.get("wall_seconds"),
                        "lambda_budget": record.get("lambda_budget"),
                        "lambda_group": record.get("lambda_group"),
                        "cfg": record.get("cfg"),
                        "gate_consistency": record.get("gate_consistency"),
                        "dr_weight": record.get("dr_weight"),
                    }
                )
    walls = [float(item["wall_seconds"] or 0) for item in runs]
    return {
        "runs_recorded": len(runs),
        "total_gpu_wall_seconds": round(sum(walls), 1),
        "mean_run_seconds": round(sum(walls) / len(walls), 1) if walls else 0.0,
        "max_lambda_budget": max((float(item["lambda_budget"] or 0) for item in runs), default=0.0),
        "runs": runs,
    }


def parity() -> dict[str, object]:
    from app.algorithms.eg_chpn_runtime import WEIGHTS_PATH, EGCHPNRuntime

    fixture_path = ROOT / "tests" / "fixtures" / "marshecho_v2_parity.npz"
    if not (WEIGHTS_PATH.exists() and fixture_path.exists()):
        return {"available": False}
    fixture = np.load(fixture_path)
    runtime = EGCHPNRuntime.load()
    got = runtime.forward_arrays(
        fixture["x"], fixture["type_ids"], fixture["H"], fixture["H_norm"], fixture["attrs"], fixture["hard_mask"], fixture["delta"], fixture["rel_ids"]
    )
    deltas = {key: float(np.max(np.abs(got[key] - fixture[key]))) for key in ("g_raw", "g", "h1", "h0", "tau", "y1", "y0", "score", "z")}
    manifest_path = WEIGHTS_PATH.parent / "marshecho_v2_0.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return {
        "available": True,
        "max_abs_difference": max(deltas.values()),
        "per_output": deltas,
        "tolerance": 1e-5,
        "weights_sha256": manifest.get("sha256", hashlib.sha256(WEIGHTS_PATH.read_bytes()).hexdigest()),
        "weights_bytes": WEIGHTS_PATH.stat().st_size,
        "parameters": manifest.get("parameters") or manifest.get("parameters_per_member"),
        "members": manifest.get("members", 1),
    }


REFERENCE_METHODS = {"eg_chpn_v1_frozen", "tarnet", "dragonnet", "random_feasible", "response_only", "tabular_t_learner"}


def write_image_summary(payload: dict, summary: list[dict], factor: dict, rows: list[dict]) -> str | None:
    """Ship the part of the experiment record that the platform endpoint serves.

    The full artifacts live under ``docs/``, which the Dockerfile never copies, so
    ``/api/algorithms/marshecho/experiments/v2`` would otherwise answer 503 in
    every deployed environment.
    """

    from app.algorithms.eg_chpn_runtime import WEIGHTS_PATH

    if not WEIGHTS_PATH.exists():
        return None
    manifest_path = WEIGHTS_PATH.parent / "marshecho_v2_0.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    body = {
        "experiment": payload["experiment"],
        "synthetic": True,
        "label": "流程验证（虚构）",
        "model": payload["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights": {
            "sha256": manifest.get("sha256") or hashlib.sha256(WEIGHTS_PATH.read_bytes()).hexdigest(),
            "bytes": manifest.get("bytes") or WEIGHTS_PATH.stat().st_size,
            "members": manifest.get("members", 1),
            "parameters_per_member": manifest.get("parameters_per_member") or manifest.get("parameters"),
        },
        "shipped_tree": SHIPPED_TREE,
        "seeds": sorted({int(row["seed"]) for row in rows}),
        "shipped_summary": [item for item in summary if item["tree"] == SHIPPED_TREE],
        "reference_methods": [
            item
            for item in summary
            if item["dgp"] == "v1" and item["selector"] == "oracle_rule" and item["method"] in REFERENCE_METHODS
        ],
        "gate_factorial": factor["cells"],
        "factorial_design": factor["design"],
        "note": "所有指标来自合成模拟器的流程验证（虚构），不代表真实航司经营提升。",
    }
    target = WEIGHTS_PATH.parent / "marshecho_v2_0.summary.json"
    target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(target)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    discovered = discover()
    rows = [
        row
        for (tree, dgp), tags in discovered.items()
        for tag, paths in tags.items()
        for row in evaluate(tree, dgp, tag, paths)
    ]
    summary = aggregate(rows)
    raw_path = OUT / "marshecho-ablation-v2.0.csv"
    if rows:
        with raw_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    payload = {
        "experiment": "Marsh-Echo (九皋) v2 训练模型消融与因子实验",
        "synthetic": True,
        "label": "流程验证（虚构）",
        "model": {"name": "marshecho", "name_zh": "九皋", "paper_name": "Marsh-Echo", "architecture": "EG-CHPN v2"},
        "trees": {f"{tree}/{dgp}": sorted(tags) for (tree, dgp), tags in discovered.items()},
        "summary": summary,
    }
    (OUT / "marshecho-ablation-v2.0.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "marshecho-gate-factorial-v2.0.json").write_text(json.dumps({"synthetic": True, "label": "流程验证（虚构）", **factorial(summary)}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "marshecho-policy-constraints-v2.0.json").write_text(json.dumps({"synthetic": True, "label": "流程验证（虚构）", **constraints()}, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "marshecho-runtime-parity-v2.0.json").write_text(json.dumps({"synthetic": True, "label": "流程验证（虚构）", **parity()}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["| tree | dgp | method | gate | selector | seeds | policy value | CI | invalid rule (pre) | qini |", "|---|---|---|---|---|---:|---:|---:|---:|---:|"]
    for item in summary:
        lines.append(
            f"| {item['tree']} | {item['dgp']} | {item['method']} | {item['gate']} | {item['selector']} | {item['n_seeds']} | {item['policy_value_mean']:.3f} | ±{item['policy_value_ci95']:.3f} | {item['invalid_rule_rate_pre_filter_mean']:.3f} | {item['qini_mean']:.3f} |"
        )
    (OUT / "marshecho-ablation-table-v2.0.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # ``docs/`` never enters the image, so the platform endpoint that serves the
    # experiment summary has to read a copy that ships next to the weights.
    write_image_summary(payload, summary, factorial(summary), rows)
    print(json.dumps({"rows": len(rows), "summary": len(summary), "raw": str(raw_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
