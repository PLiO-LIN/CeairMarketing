"""Invariant checks for the Marsh-Echo (九皋) v2 artifacts.

Runs in a NumPy-only environment (no torch): the deployed path must be
verifiable without the training stack.  Hard failures are limited to
properties that must hold regardless of sweep progress; rows that depend on a
still-running sweep are reported as PENDING.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUT = REPO / "docs" / "实验"
WEIGHTS = ROOT / "app" / "algorithms" / "weights" / "marshecho_v2_0.npz"
MANIFEST = ROOT / "app" / "algorithms" / "weights" / "marshecho_v2_0.manifest.json"
FIXTURE = ROOT / "tests" / "fixtures" / "marshecho_v2_parity.npz"
EXPECTED_SEEDS = {13, 29, 41, 53, 67, 83, 97, 101, 113, 127}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool | None, detail: str = "") -> None:
    status = "PASS" if ok else ("PENDING" if ok is None else "FAIL")
    results.append((status, name, detail))


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from app.algorithms.eg_chpn_runtime import EGCHPNRuntime

    if WEIGHTS.exists() and MANIFEST.exists() and FIXTURE.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        digest = hashlib.sha256(WEIGHTS.read_bytes()).hexdigest()
        check("weights sha256 matches manifest", digest == manifest.get("sha256"), digest[:16])
        check("manifest declares members and per-member parameter count", bool(manifest.get("parameters") or manifest.get("parameters_per_member")), f"members={manifest.get('members', 1)}")
        runtime = EGCHPNRuntime.load()
        fixture = np.load(FIXTURE)
        got = runtime.forward_arrays(
            fixture["x"], fixture["type_ids"], fixture["H"], fixture["H_norm"], fixture["attrs"], fixture["hard_mask"], fixture["delta"], fixture["rel_ids"]
        )
        worst = max(float(np.max(np.abs(got[key] - fixture[key]))) for key in ("g_raw", "g", "h1", "h0", "tau", "y1", "y0", "score", "z"))
        check("torch/numpy parity within 1e-5", worst <= 1e-5, f"max={worst:.3e}")
        blocked = np.flatnonzero(fixture["hard_mask"] == 0)
        check("semantic hard mask zeroes ineligible paths", bool(blocked.size) and bool((got["g"][blocked] == 0).all()), f"{blocked.size} masked")
        check("runtime pulls in no torch", "torch" not in sys.modules)
    else:
        check("weights artifact present", None, "export not run yet")

    ablation_path = OUT / "marshecho-ablation-v2.0.json"
    if ablation_path.exists():
        payload = json.loads(ablation_path.read_text(encoding="utf-8"))
        check("ablation artifact marked synthetic", payload.get("synthetic") is True and payload.get("label") == "流程验证（虚构）")
        seeds_seen = {int(row["seed"]) for row in csv_rows(OUT / "marshecho-ablation-v2.0.csv")}
        missing = EXPECTED_SEEDS - seeds_seen
        check("all 10 seeds present in ablation table", None if missing else True, f"missing={sorted(missing)}" if missing else f"{len(seeds_seen)} seeds")
    else:
        check("ablation artifact present", None)

    factorial_path = OUT / "marshecho-gate-factorial-v2.0.json"
    if factorial_path.exists():
        cells = json.loads(factorial_path.read_text(encoding="utf-8")).get("cells", {})
        needed = {f"{gate}|{selector}" for gate in ("learned", "none") for selector in ("none", "oracle_rule", "oracle_both")}
        check("gate × selector factorial complete", needed <= set(cells) or None, f"{len(set(cells))}/{len(needed)} cells")
    else:
        check("factorial artifact present", None)

    for suffix in ("", ".dgp2"):
        dgp_artifact = OUT / f"eg-chpn-simulation-v2.0{suffix}.json"
        if dgp_artifact.exists():
            payload = json.loads(dgp_artifact.read_text(encoding="utf-8"))
            check(
                f"benchmark artifact for dgp={payload.get('dgp')} complete",
                payload.get("synthetic") is True and len({int(row['seed']) for row in csv_rows(OUT / f'eg-chpn-simulation-v2.0{suffix}.csv')}) == len(EXPECTED_SEEDS),
                f"{payload.get('n_rows')} rows",
            )
        else:
            check(f"benchmark artifact{suffix} present", None)

    teacher_path = OUT / "marshecho-teacher-distill-v2.0.json"
    if teacher_path.exists():
        probe = json.loads(teacher_path.read_text(encoding="utf-8")).get("probe", {})
        accuracy = probe.get("flag_decision_accuracy", 0)
        check("teacher judge passes 0.8 agreement gate", accuracy >= 0.8, f"accuracy={accuracy}")
    else:
        check("teacher probe artifact present", False)

    ensemble_path = OUT / "marshecho-ensemble-ab-v2.0.json"
    if ensemble_path.exists():
        parity = json.loads(ensemble_path.read_text(encoding="utf-8")).get("runtime_parity", {})
        check(
            "ensemble runtime matches torch within tolerance",
            bool(parity) and float(parity.get("numpy_vs_torch_averaged_max_abs", 1)) <= float(parity.get("tolerance", 1e-5)),
            f"members={parity.get('members')}",
        )
    full_gate = OUT / "marshecho-gate-consistency-full.json"
    if full_gate.exists():
        verdict = json.loads(full_gate.read_text(encoding="utf-8")).get("verdict", "")
        check("admissibility term confirmed at production scale", verdict.startswith("采用"), verdict)
    else:
        check("admissibility term confirmed at production scale", None, "full-scale check pending")

    scaling_path = OUT / "marshecho-compute-scaling-v2.0.json"
    if scaling_path.exists():
        scaling = json.loads(scaling_path.read_text(encoding="utf-8"))
        summary = scaling.get("summary", {})
        check(
            "extra compute paired against the shipped config",
            scaling.get("synthetic") is True and summary.get("comparisons", 0) >= 4,
            f"{summary.get('worse_than_shipped')}/{summary.get('comparisons')} worse, mean delta={summary.get('mean_delta_best_val')}",
        )
    else:
        check("extra compute paired against the shipped config", None, "scaling audit not run")

    audit_path = OUT / "marshecho-early-stopping-audit-v2.0.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        rows = [row for row in audit.get("rows", []) if "argmin_epochs_agree" in row]
        agreed = sum(1 for row in rows if row["argmin_epochs_agree"])
        gap = max(float(row["mean_penalty_gap"]) for row in rows) if rows else 1.0
        check(
            "criterion change is a verified no-op on selection",
            audit.get("synthetic") is True and bool(rows) and agreed == len(rows) and gap < 0.05,
            f"{agreed}/{len(rows)} same epoch, worst penalty gap {gap:.6f}",
        )
    else:
        check("criterion change is a verified no-op on selection", None, "early-stopping audit not run")

    recipe_path = OUT / "marshecho-final-recipe-ab-v2.0.json"
    if recipe_path.exists():
        recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
        arm = ((recipe.get("arms") or {}).get("runs_selq_gcdr") or {}).get("by_dgp", {}).get("v1", {})
        metrics = arm.get("metrics", {})
        check(
            "shipping candidate beats shipped model on paired test window",
            bool(metrics)
            and metrics["policy_value"]["mean_delta"] > 0
            and metrics["uplift_rmse"]["mean_delta"] < 0,
            f"value {metrics.get('policy_value', {}).get('mean_delta', 0):+.1f}, "
            f"rmse {metrics.get('uplift_rmse', {}).get('mean_delta', 0):+.4f}, n={arm.get('seeds_paired')}",
        )
    else:
        check("shipping candidate beats shipped model on paired test window", None, "recipe A/B not run")

    for line in results:
        print(f"{line[0]:8} {line[1]}  {line[2]}")
    return 1 if any(status == "FAIL" for status, _, _ in results) else 0


def csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    raise SystemExit(main())
