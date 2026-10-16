#!/usr/bin/env bash
# Corrected-selection continuation for Marsh-Echo (九皋).
#
# The audit in scripts/analyze_marshecho_compute_scaling.py showed that every
# shipped checkpoint was early-stopped at ~epoch 180 of 2000: the selection
# criterion was the full composite loss, whose Lagrangian penalty
# (lambda_budget x budget_violation) explodes as the policy head gets more
# aggressive, so the criterion rose while every causal term kept improving.
#
# This chain changes exactly one thing -- the checkpoint-selection criterion --
# and keeps the shipped recipe (GRID[1]: lr 3e-3, wd 0, lam_policy 0.1, hidden
# 128, 3 layers, 2000 epochs) so the comparison against the shipped ensemble is
# paired by seed and single-variable.  A second worker trains the same corrected
# criterion on top of the admissibility + DR recipe, so both candidates land at
# the same time.  Nothing here re-exports or overwrites the shipped weights;
# that decision is made afterwards by scripts/ab_marshecho_selection.py.
set -uo pipefail
cd "$(dirname "$0")/.."
EGCHPN=/d/venv/egchpn/Scripts/python.exe
LOG=research/egchpn_torch/continue_v3.log
DIR=research/egchpn_torch
S10=13,29,41,53,67,83,97,101,113,127
RECIPE="--epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --lr 0.003 --weight-decay 0 --lam-policy 0.1"

export CUBLAS_WORKSPACE_CONFIG=:4096:8
export PYTHONHASHSEED=0

# supervise TAG ATTEMPTS OUT ARGS...
supervise() {
  local tag=$1 attempts=$2 out=$3; shift 3
  for attempt in $(seq 1 "$attempts"); do
    echo "[$(date +%m-%d_%H:%M)] $tag attempt $attempt starting" | tee -a "$LOG"
    if "$EGCHPN" -B research/egchpn_torch/train.py --tag "$tag" --out "$out" "$@" >> "$DIR/$tag.log" 2>&1; then
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
echo "[$(date +%m-%d_%H:%M)] chain v3 up: corrected selection criterion" | tee -a "$LOG"

# arm 1 -- shipped recipe, corrected criterion (single variable vs the shipped ensemble)
supervise q1 3 "$DIR/runs_final" --dgps v1,v2 --ablations none --seeds $S10 $RECIPE --select-metric quality --skip-existing &
# arm 2 -- corrected criterion + admissibility term + DR pseudo-outcome supervision
supervise g1 3 "$DIR/runs_selq_gcdr" --dgps v1,v2 --ablations none --seeds $S10 $RECIPE --gate-consistency 0.5 --dr-weight 1.0 --select-metric quality --skip-existing &
wait
echo "[$(date +%m-%d_%H:%M)] both arms done in $(( $(date +%s) - START ))s wall" | tee -a "$LOG"

# no-gate control for the 2x2 factorial, run after the candidates so the pairing
# stays clean and the GPU is never oversubscribed on this 16 GB host
supervise q2 3 "$DIR/runs_final" --dgps v1,v2 --ablations no_gate --seeds $S10 $RECIPE --select-metric quality --skip-existing &
supervise g2 3 "$DIR/runs_selq_gcdr" --dgps v1,v2 --ablations no_gate --seeds $S10 $RECIPE --gate-consistency 0.5 --dr-weight 1.0 --select-metric quality --skip-existing &
wait
echo "[$(date +%m-%d_%H:%M)] chain v3 complete" | tee -a "$LOG"
