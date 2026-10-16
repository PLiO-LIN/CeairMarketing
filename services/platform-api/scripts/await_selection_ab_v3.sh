#!/usr/bin/env bash
# Wait for the two corrected-criterion arms, then run the paired test-window A/B.
# Writes a short human-readable summary next to the raw artifact output so the
# result can be read without re-running anything.
set -uo pipefail
cd "$(dirname "$0")/.."
CEAIR=/d/venv/ceair/Scripts/python.exe
LOG=research/egchpn_torch/continue_v3.log
RES=research/egchpn_torch/ab_result.txt

while true; do
  q=$(grep -c '^\[.*] q1 complete' "$LOG" 2>/dev/null || true)
  g=$(grep -c '^\[.*] g1 complete' "$LOG" 2>/dev/null || true)
  f=$(grep -c 'attempt .* failed\|still failing' "$LOG" 2>/dev/null || true)
  if [ "${q:-0}" -ge 1 ] && [ "${g:-0}" -ge 1 ]; then break; fi
  if [ "${f:-0}" -ge 6 ]; then echo "ABORT: repeated worker failures, see $LOG" > "$RES"; exit 1; fi
  sleep 60
done

{
  echo "measured_at=$(date +%m-%d_%H:%M)"
  echo "== paired test-window A/B (selector=oracle_rule, tag=marshecho_none) =="
  "$CEAIR" -B scripts/ab_marshecho_selection.py
  echo
  echo "== selection-defect recompute (new criterion included) =="
  "$CEAIR" -B scripts/analyze_marshecho_selection_defect.py
  echo
  echo "== arm manifests =="
  for tree in runs_final runs_selq_gcdr; do
    for mf in research/egchpn_torch/$tree/manifest_*.jsonl; do
      [ -f "$mf" ] || continue
      echo "$mf runs=$(wc -l < "$mf")"
    done
  done
} > "$RES" 2>&1
echo "done=$(date +%m-%d_%H:%M)" >> "$RES"
