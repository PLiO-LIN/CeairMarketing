#!/usr/bin/env bash
# Chain: finish w4 -> run the >=8h stage-2 continuation -> select the best
# checkpoint by validation loss -> re-export, re-table, re-verify, re-package.
set -uo pipefail
cd "$(dirname "$0")/.."
CEAIR=/d/venv/ceair/Scripts/python.exe
LOG=research/egchpn_torch/continue.log
: > "$LOG"
START=$(date +%s)

count() {  # count live python workers whose command line carries one of our tags
  powershell -NoProfile -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'tag ($1)' } | Measure-Object | Select-Object -ExpandProperty Count" 2>/dev/null | tr -d '\r'
}

echo "[$(date +%m-%d_%H:%M)] waiting for w4 (gap fill)" | tee -a "$LOG"
while [ "$(count 'w[0-9]')" != "0" ]; do sleep 60; done
echo "[$(date +%m-%d_%H:%M)] w4 done; launching stage 2" | tee -a "$LOG"
STAGE_START=$(date +%s)
bash research/egchpn_torch/launch_stage2.sh 2>&1 | tee -a "$LOG"

echo "[$(date +%m-%d_%H:%M)] stage 2 running (s1 s2 s3 l1 l2)" | tee -a "$LOG"
while [ "$(count 's[123]|l[12]')" != "0" ]; do sleep 120; done
STAGE_SECONDS=$(( $(date +%s) - STAGE_START ))
echo "[$(date +%m-%d_%H:%M)] stage 2 finished after ${STAGE_SECONDS}s wall" | tee -a "$LOG"

echo "[$(date +%m-%d_%H:%M)] ranking configs; stage 3 retrains the winner" | tee -a "$LOG"
"$CEAIR" -B scripts/select_best_checkpoint.py >> "$LOG" 2>&1
WINNER=research/egchpn_torch/winner_cfg.json
LR=$(sed -E 's/.*"lr": *([0-9.e-]+).*//' "$WINNER")
WD=$(sed -E 's/.*"wd": *([0-9.e-]+).*//' "$WINNER")
LP=$(sed -E 's/.*"lam_policy": *([0-9.e-]+).*//' "$WINNER")
echo "[$(date +%m-%d_%H:%M)] stage 3 config lr=$LR wd=$WD lam=$LP (hidden 192, 4 layers, 6000 epochs)" | tee -a "$LOG"
S10=13,29,41,53,67,83,97,101,113,127
EGCHPN=/d/venv/egchpn/Scripts/python.exe
# The final variant adds the admissibility term (measured: it drives the
# pre-filter invalid ranking to 0 and lifts policy value ~15%), together with a
# same-variant no-gate control so the 2x2 factorial stays valid.
nohup "$EGCHPN" -B research/egchpn_torch/train.py --dgps v1,v2 --ablations none --seeds $S10   --epochs 6000 --hidden 192 --layers 3 --n-customers 3000 --lr $LR --weight-decay $WD --lam-policy $LP   --gate-consistency 0.5 --dr-weight 1.0 --tag f1 --out research/egchpn_torch/runs_final > research/egchpn_torch/f1.log 2>&1 &
sleep 240
nohup "$EGCHPN" -B research/egchpn_torch/train.py --dgps v1,v2 --ablations no_gate --seeds $S10   --epochs 6000 --hidden 192 --layers 3 --n-customers 3000 --lr $LR --weight-decay $WD --lam-policy $LP   --gate-consistency 0.5 --dr-weight 1.0 --tag f2 --out research/egchpn_torch/runs_final > research/egchpn_torch/f2.log 2>&1 &
while [ "$(count 'f[12]')" != "0" ]; do sleep 120; done
echo "[$(date +%m-%d_%H:%M)] stage 3 finished" | tee -a "$LOG"
# Ship from the final variant only: validation losses across loss variants are
# not comparable, so the pool is restricted to runs_final.
"$CEAIR" -B scripts/select_best_checkpoint.py --tree runs_final --export --require-verified >> "$LOG" 2>&1

echo "[$(date +%m-%d_%H:%M)] rebuilding artifacts" | tee -a "$LOG"
"$CEAIR" -B scripts/run_eg_chpn_simulation_v2.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/build_marshecho_report.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/render_marshecho_report.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/verify_marshecho_v2.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/package_marshecho_bundle.py >> "$LOG" 2>&1
"$CEAIR" -m pytest -q >> "$LOG" 2>&1

TOTAL=$(( $(date +%s) - START ))
python - "$STAGE_SECONDS" "$TOTAL" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
stage, total = int(sys.argv[1]), int(sys.argv[2])
records = []
for manifest in sorted(Path("research/egchpn_torch").glob("runs*/manifest_*.jsonl")):
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
gpu_seconds = round(sum(float(record.get("wall_seconds") or 0) for record in records), 1)
Path("../docs/实验/marshecho-continuation-v2.0.json").write_text(json.dumps({
    "synthetic": True, "label": "流程验证（虚构）",
    "stage2_wall_seconds": stage, "chain_wall_seconds": total,
    "runs_total": len(records), "cumulative_gpu_seconds": gpu_seconds,
    "cumulative_gpu_hours": round(gpu_seconds / 3600, 2),
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"stage2_wall_seconds": stage, "cumulative_gpu_hours": round(gpu_seconds/3600, 2)}))
PY
echo "[$(date +%m-%d_%H:%M)] continuation chain done" | tee -a "$LOG"
