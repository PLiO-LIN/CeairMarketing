"""Live progress and elapsed-GPU accounting for the Marsh-Echo continuation.

Reports how many runs each tree/DGP/tag has produced against the expected
count, how much GPU time has accrued, and an ETA for the remaining work, so the
"train for at least eight more hours" requirement can be checked against
measured numbers instead of intent.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "research" / "egchpn_torch"
STAGE2_TAGS = {"s1": 50, "s2": 60, "s3": 30, "l1": 20, "l2": 20, "f1": 20, "f2": 20}


def records() -> list[dict]:
    out: list[dict] = []
    for manifest in sorted(DIR.glob("runs*/manifest_*.jsonl")):
        tree = manifest.parent.name
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                record["tree"] = tree
                record["worker"] = manifest.stem.replace("manifest_", "")
                out.append(record)
    return out


def main() -> int:
    rows = records()
    per_worker: dict[str, list[dict]] = {}
    for record in rows:
        per_worker.setdefault(str(record["worker"]), []).append(record)
    stage_rows = [row for worker, rows in per_worker.items() if worker in STAGE2_TAGS for row in rows]
    stage_gpu = sum(float(row.get("wall_seconds") or 0) for row in stage_rows)
    total_gpu = sum(float(row.get("wall_seconds") or 0) for row in rows)
    print(f"as_of                 : {datetime.now(timezone.utc).isoformat()}")
    print(f"runs_total(all)      : {len(rows)}")
    print(f"gpu_hours(all)       : {total_gpu / 3600:.2f}")
    print(f"gpu_hours(continuation workers) : {stage_gpu / 3600:.2f}")
    print()
    print("per-worker progress")
    for tag in sorted(per_worker):
        subset = per_worker[tag]
        hours = sum(float(row.get("wall_seconds") or 0) for row in subset) / 3600
        expected = STAGE2_TAGS.get(tag)
        mean = sum(float(row.get("wall_seconds") or 0) for row in subset) / len(subset)
        remaining = f" / {expected}" if expected else ""
        eta = ""
        if expected:
            left = max(0, expected - len(subset))
            eta = f" eta~{left * mean / 3600:.1f}h"
        print(f"  {tag:8} runs={len(subset)}{remaining}  gpu_h={hours:.2f}  mean_run={mean:.0f}s{eta}")
    print()
    for tree in sorted({row['tree'] for row in rows}):
        subset = [row for row in rows if row["tree"] == tree]
        dgps = sorted({str(row["dgp"]) for row in subset})
        print(f"  tree {tree}: {len(subset)} runs, dgps={dgps}")
    return 0


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
