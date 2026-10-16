#!/usr/bin/env bash
# Ship the paired-A/B winner and rebuild everything downstream.
#
# The winner is decided by scripts/ab_marshecho_final_recipe.py (paired
# test-window metrics, same seeds/data/recipe except the loss terms).  This
# script only executes the export and the rebuild, and it refuses to touch the
# installed weights unless that artifact nominates runs_selq_gcdr.  The previous
# shipment stays recoverable under research/egchpn_torch/snapshot_pre_stage3/.
set -uo pipefail
cd "$(dirname "$0")/.."
CEAIR=/d/venv/ceair/Scripts/python.exe
EGCHPN=/d/venv/egchpn/Scripts/python.exe
DIR=research/egchpn_torch
LOG=$DIR/finalize_v3.log
WIN=runs_selq_gcdr
export MARSHECHO_SHIPPED_TREE=$WIN
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export PYTHONHASHSEED=0

step() {
  echo "[$(date +%m-%d_%H:%M)] run: $*" | tee -a "$LOG"
  if ! "$@" >> "$LOG" 2>&1; then
    echo "[$(date +%m-%d_%H:%M)] FAILED: $*" | tee -a "$LOG"
    exit 1
  fi
}

echo "[$(date +%m-%d_%H:%M)] finalize v3 up; waiting for the no-gate control arm g2" | tee -a "$LOG"
for _ in $(seq 1 240); do
  grep -q '^\[.*] g2 complete' "$DIR/continue_v3.log" 2>/dev/null && break
  grep -q 'g2 still failing' "$DIR/continue_v3.log" 2>/dev/null && break
  sleep 60
done
echo "[$(date +%m-%d_%H:%M)] control arm finished (or gave up); proceeding" | tee -a "$LOG"

step "$CEAIR" -B scripts/ab_marshecho_final_recipe.py

if ! "$CEAIR" -B scripts/check_marshecho_winner.py "$WIN" 2>>"$LOG"; then
  echo "[$(date +%m-%d_%H:%M)] paired A/B does not nominate $WIN; installed weights left untouched" | tee -a "$LOG"
  exit 0
fi

mapfile -t MEMBERS < <(ls "$DIR/$WIN/v1"/checkpoint_seed*_h*_L*_e*.pt 2>/dev/null)
if [ "${#MEMBERS[@]}" -lt 2 ]; then
  echo "[$(date +%m-%d_%H:%M)] only ${#MEMBERS[@]} tagged members in $WIN; refusing to export an ensemble" | tee -a "$LOG"
  exit 1
fi
echo "[$(date +%m-%d_%H:%M)] exporting ${#MEMBERS[@]}-member ensemble from $WIN" | tee -a "$LOG"
step "$EGCHPN" -B research/egchpn_torch/export_ensemble.py --checkpoints "${MEMBERS[@]}" \
  --weights-out app/algorithms/weights/marshecho_v2_0.npz \
  --fixture-out tests/fixtures/marshecho_v2_parity.npz

step "$CEAIR" -B scripts/analyze_marshecho_early_stopping.py
step "$CEAIR" -B scripts/run_eg_chpn_simulation_v2.py
step "$CEAIR" -B scripts/build_marshecho_report.py
step "$CEAIR" -B scripts/render_marshecho_report.py
step "$CEAIR" -B scripts/verify_marshecho_v2.py
step "$CEAIR" -B scripts/package_marshecho_bundle.py
step "$CEAIR" -m pytest -q
step "$CEAIR" -B scripts/write_marshecho_ship_decision.py

echo "[$(date +%m-%d_%H:%M)] finalize v3 complete" | tee -a "$LOG"
