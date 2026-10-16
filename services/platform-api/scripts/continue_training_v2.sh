#!/usr/bin/env bash
# Self-healing continuation chain for Marsh-Echo (九皋).
#
# Waits for the gap-fill worker (w4), then runs:
#   stage 2  dgp=v2 matrix (main model, 11 ablations, 3 torch baselines)
#            plus larger / longer candidate models in runs_long
#   stage 3  the final variant (admissibility term + DR pseudo-outcome
#            supervision) at production scale in runs_final, with its no-gate
#            control so the 2x2 factorial stays valid
# and finally re-exports, re-tables, re-verifies, re-packages and runs pytest.
#
# Every worker is retried up to three times with --skip-existing, so a single
# CUDA crash can no longer silently remove hours of training.
set -uo pipefail
cd "$(dirname "$0")/.."
CEAIR=/d/venv/ceair/Scripts/python.exe
EGCHPN=/d/venv/egchpn/Scripts/python.exe
LOG=research/egchpn_torch/continue.log
DIR=research/egchpn_torch
S10=13,29,41,53,67,83,97,101,113,127

count() {
  powershell -NoProfile -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'tag ($1)' } | Measure-Object | Select-Object -ExpandProperty Count" 2>/dev/null | tr -d '\r'
}

# supervise TAG ATTEMPTS ARGS...
# A zero exit code from train.py means the worker walked its whole run list;
# a crash (e.g. a CUDA device assert) exits non-zero and is retried, resuming
# only the missing runs thanks to --skip-existing.
supervise() {
  local tag=$1 attempts=$2; shift 2
  for attempt in $(seq 1 "$attempts"); do
    echo "[$(date +%m-%d_%H:%M)] $tag attempt $attempt starting" | tee -a "$LOG"
    if "$EGCHPN" -B research/egchpn_torch/train.py --tag "$tag" "$@" >> "$DIR/$tag.log" 2>&1; then
      echo "[$(date +%m-%d_%H:%M)] $tag complete" | tee -a "$LOG"
      return 0
    fi
    echo "[$(date +%m-%d_%H:%M)] $tag attempt $attempt failed; retrying" | tee -a "$LOG"
    sleep 30
  done
  echo "[$(date +%m-%d_%H:%M)] $tag still failing after $attempts attempts" | tee -a "$LOG"
  return 1
}

START=$(date +%s)
echo "[$(date +%m-%d_%H:%M)] chain v2 up; waiting for w4" | tee -a "$LOG"
while [ "$(count 'w[0-9]')" != "0" ]; do sleep 60; done
echo "[$(date +%m-%d_%H:%M)] w4 done" | tee -a "$LOG"

STAGE_START=$(date +%s)
echo "[$(date +%m-%d_%H:%M)] stage 2: dgp v2 matrix + long candidates" | tee -a "$LOG"
supervise s1 3 --dgps v2 --ablations none,no_gate,no_dual_tower,no_temporal,no_balance --seeds $S10 --epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --skip-existing --out $DIR/runs &
supervise s2 3 --dgps v2 --ablations no_counterfactual,no_evidence_loss,no_lagrangian,no_policy_head,gate_deterministic_only,no_hypergraph --seeds $S10 --epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --skip-existing --out $DIR/runs &
supervise s3 3 --dgps v2 --skip-ablations --baselines tarnet,dragonnet,gat_trained --seeds $S10 --epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --skip-existing --out $DIR/runs &
wait
supervise l1 3 --dgps v1,v2 --ablations none --seeds $S10 --epochs 6000 --hidden 192 --layers 4 --n-customers 3000 --cfg-index 1 --skip-existing --out $DIR/runs_long &
supervise l2 3 --dgps v1,v2 --ablations none --seeds $S10 --epochs 6000 --hidden 128 --layers 3 --n-customers 3000 --cfg-index 0 --skip-existing --out $DIR/runs_long &
wait
STAGE_SECONDS=$(( $(date +%s) - STAGE_START ))
echo "[$(date +%m-%d_%H:%M)] stage 2 done in ${STAGE_SECONDS}s wall" | tee -a "$LOG"

"$CEAIR" -B scripts/select_best_checkpoint.py >> "$LOG" 2>&1
WINNER=$DIR/winner_cfg.json
LR=$(sed -E 's/.*"lr": *([0-9.e-]+).*/\1/' "$WINNER")
WD=$(sed -E 's/.*"wd": *([0-9.e-]+).*/\1/' "$WINNER")
LP=$(sed -E 's/.*"lam_policy": *([0-9.e-]+).*/\1/' "$WINNER")
echo "[$(date +%m-%d_%H:%M)] stage 3 final variant: lr=$LR wd=$WD lam=$LP, admissibility=0.5, dr=1.0" | tee -a "$LOG"
supervise f1 3 --dgps v1,v2 --ablations none --seeds $S10 --epochs 6000 --hidden 192 --layers 3 --n-customers 3000 --lr "$LR" --weight-decay "$WD" --lam-policy "$LP" --gate-consistency 0.5 --dr-weight 1.0 --skip-existing --out $DIR/runs_final &
supervise f2 3 --dgps v1,v2 --ablations no_gate --seeds $S10 --epochs 6000 --hidden 192 --layers 3 --n-customers 3000 --lr "$LR" --weight-decay "$WD" --lam-policy "$LP" --gate-consistency 0.5 --dr-weight 1.0 --skip-existing --out $DIR/runs_final &
wait
echo "[$(date +%m-%d_%H:%M)] stage 3 done" | tee -a "$LOG"

echo "[$(date +%m-%d_%H:%M)] exporting the shipped model" | tee -a "$LOG"
# 1. ranking-only selection: proves the winning configuration has tagged checkpoints
"$CEAIR" -B scripts/select_best_checkpoint.py --tree runs_final --require-verified >> "$LOG" 2>&1
# 2. ship the 10-member ensemble of the final variant (measured: value +11%, RMSE -14..-20%)
MEMBERS=$(ls research/egchpn_torch/runs_final/v1/checkpoint_seed*_h*_L*_e*.pt 2>/dev/null | wc -l | tr -d ' ')
if [ "${MEMBERS:-0}" -ge 2 ]; then
  echo "[$(date +%m-%d_%H:%M)] exporting ensemble from $MEMBERS members" | tee -a "$LOG"
  "$EGCHPN" -B research/egchpn_torch/export_ensemble.py     --checkpoints $(ls research/egchpn_torch/runs_final/v1/checkpoint_seed*_h*_L*_e*.pt | tr '
' ' ')     --weights-out app/algorithms/weights/marshecho_v2_0.npz     --fixture-out tests/fixtures/marshecho_v2_parity.npz >> "$LOG" 2>&1
else
  echo "[$(date +%m-%d_%H:%M)] only $MEMBERS tagged members; falling back to single-checkpoint export" | tee -a "$LOG"
  "$CEAIR" -B scripts/select_best_checkpoint.py --tree runs_final --require-verified --export >> "$LOG" 2>&1
fi

echo "[$(date +%m-%d_%H:%M)] rebuilding artifacts" | tee -a "$LOG"
"$CEAIR" -B scripts/run_eg_chpn_simulation_v2.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/build_marshecho_report.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/render_marshecho_report.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/verify_marshecho_v2.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/package_marshecho_bundle.py >> "$LOG" 2>&1
"$CEAIR" -m pytest -q >> "$LOG" 2>&1

TOTAL=$(( $(date +%s) - START ))
"$CEAIR" - "$STAGE_SECONDS" "$TOTAL" <<'PY' 2>&1 | tee -a "$LOG"
import json
from pathlib import Path
stage, total = int(__import__("sys").argv[1]), int(__import__("sys").argv[2])
records = []
for manifest in sorted(Path("research/egchpn_torch").glob("runs*/manifest_*.jsonl")):
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
continuation = []
for log in sorted(Path("research/egchpn_torch").glob("sweep_summary_*.json")):
    continuation.append(json.loads(log.read_text(encoding="utf-8")))
gpu_seconds = round(sum(float(record.get("wall_seconds") or 0) for record in records), 1)
payload = {
    "synthetic": True,
    "label": "流程验证（虚构）",
    "stage2_wall_seconds": stage,
    "chain_wall_seconds": total,
    "runs_total": len(records),
    "cumulative_gpu_seconds": gpu_seconds,
    "cumulative_gpu_hours": round(gpu_seconds / 3600, 2),
    "per_worker": continuation,
}
Path("../docs/实验/marshecho-continuation-v2.0.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"cumulative_gpu_hours": payload["cumulative_gpu_hours"], "runs_total": payload["runs_total"]}))
PY
echo "[$(date +%m-%d_%H:%M)] continuation chain complete" | tee -a "$LOG"
