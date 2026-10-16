"""Pick the shipped Marsh-Echo checkpoint by validation loss only.

Compares the standard sweep tree and the longer/larger candidate tree on the
seeds they share, ranks configurations by mean training-window validation
loss, and writes the ranking plus the chosen checkpoint into an artifact.
Test-window metrics are never used for this decision.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
TREES = {
    "runs": ROOT / "research/egchpn_torch/runs",
    "runs_long": ROOT / "research/egchpn_torch/runs_long",
    "runs_final": ROOT / "research/egchpn_torch/runs_final",
}


def load_records() -> list[dict]:
    records: list[dict] = []
    for tree, directory in TREES.items():
        for manifest in sorted(directory.glob("manifest_*.jsonl")):
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("method") != "marshecho_none":
                    continue
                record["tree"] = tree
                record["worker"] = manifest.stem.replace("manifest_", "")
                records.append(record)
    return records


def rank(records: list[dict], dgp: str) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for record in records:
        if record.get("dgp") != dgp:
            continue
        cfg = record.get("cfg") or {}
        key = (record["tree"], cfg.get("lr"), cfg.get("wd"), cfg.get("lam_policy"), record.get("wall_seconds") and None)
        groups.setdefault(key[:4], []).append(record)
    per_seed: dict[int, list[float]] = {}
    for items in groups.values():
        for record in items:
            per_seed.setdefault(int(record["seed"]), []).append(float(record["best_val"]))
    common = {seed for seed, values in per_seed.items() if len(values) == len(groups)} or set(per_seed)
    table = []
    for key, items in groups.items():
        subset = [record for record in items if int(record["seed"]) in common]
        if not subset:
            continue
        values = [float(record["best_val"]) for record in subset]
        table.append(
            {
                "tree": key[0],
                "lr": key[1],
                "wd": key[2],
                "lam_policy": key[3],
                "worker": sorted({record["worker"] for record in subset}),
                "seeds": len(values),
                "mean_best_val": round(statistics.fmean(values), 6),
                "std_best_val": round(statistics.pstdev(values), 6) if len(values) > 1 else 0.0,
                "mean_wall_seconds": round(statistics.fmean(float(record["wall_seconds"]) for record in subset), 1),
            }
        )
    table.sort(key=lambda item: item["mean_best_val"])
    return table


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dgp", default="v1", help="data-generating process used for the decision")
    parser.add_argument("--export", action="store_true", help="run export_weights.py with the winning checkpoint")
    parser.add_argument("--seed", type=int, default=13, help="seed whose checkpoint is shipped")
    parser.add_argument("--require-verified", action="store_true", help="fail unless the shipped checkpoint is config-tagged")
    parser.add_argument("--tree", default=None, help="restrict candidates to one run tree (loss variants are not comparable)")
    args = parser.parse_args()
    records = load_records()
    if args.tree:
        records = [record for record in records if record["tree"] == args.tree]
    if not records:
        print("no marshecho_none records found")
        return 1
    table = rank(records, args.dgp)
    if not table:
        print(f"no candidate records for tree={args.tree}")
        return 1
    winner = table[0]
    group = [
        record
        for record in records
        if record.get("dgp") == args.dgp
        and record["tree"] == winner["tree"]
        and (record.get("cfg") or {}).get("lr") == winner["lr"]
        and (record.get("cfg") or {}).get("wd") == winner["wd"]
        and (record.get("cfg") or {}).get("lam_policy") == winner["lam_policy"]
    ]
    def tagged_path(record: dict) -> Path:
        cfg = record.get("cfg") or {}
        suffix = f"lr{cfg.get('lr')}_wd{cfg.get('wd')}_lp{cfg.get('lam_policy')}_h{record.get('hidden')}_L{record.get('layers')}_e{record.get('epochs')}"
        return TREES[record["tree"]] / str(record.get("dgp")) / f"checkpoint_seed{record.get('seed')}_{suffix}.pt"

    verified = [record for record in group if tagged_path(record).exists()] if group else []
    if verified:
        best_record = min(verified, key=lambda record: float(record["best_val"]))
        checkpoint = tagged_path(best_record)
        args.seed = int(best_record["seed"])
        winner["shipped_seed_reason"] = f"lowest validation loss among config-tagged checkpoints: {best_record['best_val']}"
        winner["checkpoint_verified"] = True
    else:
        # Legacy runs predate config-tagged checkpoint names, so the file on disk
        # may have been overwritten by a later configuration.  Never ship one of
        # those blindly: fall back to the plain name but flag it unverified.
        checkpoint = TREES[winner["tree"]] / args.dgp / f"checkpoint_seed{args.seed}.pt"
        winner["checkpoint_verified"] = False
    if not checkpoint.exists():
        seeds_available = sorted(
            int(re.search(r"checkpoint_seed(\d+)", path.name).group(1)) for path in (TREES[winner["tree"]] / args.dgp).glob("checkpoint_seed*.pt")
        )
        checkpoint = TREES[winner["tree"]] / args.dgp / f"checkpoint_seed{seeds_available[0]}.pt"
    payload = {
        "decision_rule": "lowest mean training-window validation loss across shared seeds; test metrics never consulted",
        "dgp_for_decision": args.dgp,
        "ranking": table,
        "winner": winner,
        "shipped_checkpoint": str(checkpoint),
        "shipped_seed": int(re.search(r"checkpoint_seed(\d+)", checkpoint.name).group(1)),
        "cross_check_v2": rank(records, "v2")[:3] if any(record["dgp"] == "v2" for record in records) else [],
    }
    out = REPO / "docs" / "实验" / "marshecho-checkpoint-selection-v2.0.json"
    out.write_text(json.dumps({"synthetic": True, "label": "流程验证（虚构）", **payload}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"winner": winner, "checkpoint": str(checkpoint), "ranking": table}, ensure_ascii=False, indent=2))
    (ROOT / "research/egchpn_torch/winner_cfg.json").write_text(
        json.dumps({"lr": winner["lr"], "wd": winner["wd"], "lam_policy": winner["lam_policy"], "tree": winner["tree"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    if args.require_verified and not winner.get("checkpoint_verified"):
        print("REFUSING to ship: the winning configuration has no config-tagged checkpoint on disk "
              "(legacy runs overwrote each other). Re-run the winning config before exporting.")
        return 2
    if args.export:
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "research/egchpn_torch/export_weights.py"),
                "--checkpoint",
                str(checkpoint),
                "--expect-wd",
                str(winner["wd"]),
            ],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
