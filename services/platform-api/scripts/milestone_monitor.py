"""Timestamped evidence that the continuation training really ran >= 8 hours.

Parses the stage-2 start stamp from the chain log, then every five minutes
measures elapsed wall time and the GPU hours accrued by the continuation
workers.  When either eight hours of continued training have elapsed or the
chain has finished, it writes an artifact with the measured numbers and runs
the invariant verifier, then exits so the operator is notified.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
LOG = ROOT / "research" / "egchpn_torch" / "continue.log"
TARGET = REPO / "docs" / "实验" / "marshecho-continuation-milestone.json"
STAMP = re.compile(r"\[(\d{2}-\d{2})_(\d{2}):(\d{2})\]")
CONTINUATION_TAGS = {"s1", "s2", "s3", "l1", "l2", "f1", "f2"}
GOAL_SECONDS = 8 * 3600
WAIT_FOR_WALL = "--wall-only" in sys.argv
POLL_SECONDS = 300


def stage_start() -> datetime | None:
    if not LOG.exists():
        return None
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if "stage 2:" in line:
            match = STAMP.search(line)
            if match:
                month, day = map(int, match.group(1).split("-"))
                hour, minute = int(match.group(2)), int(match.group(3))
                # the log stamp is local wall time and carries no year
                now = datetime.now().astimezone()
                candidate = datetime(now.year, month, day, hour, minute, tzinfo=now.tzinfo)
                if candidate > now + timedelta(hours=1):
                    candidate = candidate.replace(year=now.year - 1)
                return candidate
    return None


def continuation_gpu_hours() -> tuple[float, int]:
    seconds = 0.0
    runs = 0
    for manifest in sorted((ROOT / "research" / "egchpn_torch").glob("runs*/manifest_*.jsonl")):
        worker = manifest.stem.replace("manifest_", "")
        if worker not in CONTINUATION_TAGS:
            continue
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seconds += float(json.loads(line).get("wall_seconds") or 0)
                runs += 1
    return seconds / 3600, runs


def verifier_lines() -> list[str]:
    result = subprocess.run(
        [r"D:/venv/ceair/Scripts/python.exe", "-B", "scripts/verify_marshecho_v2.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return [line for line in (result.stdout or "").splitlines() if line.strip()]


def main() -> int:
    started = stage_start()
    if started is None:
        print("stage 2 start stamp not found yet; waiting", flush=True)
        return 3
    print(f"stage 2 started at {started.isoformat()}", flush=True)
    while True:
        now = datetime.now().astimezone()
        elapsed = (now - started).total_seconds()
        gpu_hours, runs = continuation_gpu_hours()
        chain_done = "continuation chain complete" in LOG.read_text(encoding="utf-8", errors="replace")
        print(f"{now:%H:%M:%S} elapsed={elapsed/3600:.2f}h gpu_h={gpu_hours:.2f} runs={runs} chain_done={chain_done}", flush=True)
        if elapsed >= GOAL_SECONDS or ((not WAIT_FOR_WALL) and gpu_hours >= 8.0) or chain_done:
            payload = {
                "measured_at": now.isoformat(),
                "stage2_started_at": started.isoformat(),
                "continuation_wall_seconds": round(elapsed, 1),
                "continuation_wall_hours": round(elapsed / 3600, 3),
                "continuation_gpu_hours": round(gpu_hours, 3),
                "continuation_runs": runs,
                "goal_wall_hours": 8,
                "goal_gpu_hours": 8,
                "goal_met_by_wall": elapsed >= GOAL_SECONDS,
                "goal_met_by_gpu_hours": gpu_hours >= 8,
                "chain_complete": chain_done,
                "verifier": verifier_lines(),
                "note": "时间戳按本地墙钟解析（链日志无年份与时区标记）",
            }
            TARGET.parent.mkdir(parents=True, exist_ok=True)
            TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
