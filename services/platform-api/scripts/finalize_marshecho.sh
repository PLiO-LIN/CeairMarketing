#!/usr/bin/env bash
# Wait for the training sweep to finish, then assemble the final Marsh-Echo
# artefacts: export weights -> numpy v2 benchmark -> report tables -> invariant
# checks -> copyable bundle -> full pytest.  Safe to leave running unattended;
# every step is deterministic and logged.
set -uo pipefail
cd "$(dirname "$0")/.."
CEAIR=/d/venv/ceair/Scripts/python.exe
EGCHPN=/d/venv/egchpn/Scripts/python.exe
LOG=research/egchpn_torch/finalize.log
: > "$LOG"

echo "[$(date +%H:%M:%S)] waiting for sweep workers" | tee -a "$LOG"
while true; do
  alive=$(powershell -NoProfile -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*tag w?*' } | Measure-Object | Select-Object -ExpandProperty Count" 2>/dev/null | tr -d '\r')
  if [ "${alive:-0}" = "0" ]; then break; fi
  sleep 60
done
echo "[$(date +%H:%M:%S)] sweep finished" | tee -a "$LOG"

echo "[$(date +%H:%M:%S)] export weights" | tee -a "$LOG"
"$EGCHPN" -B research/egchpn_torch/export_weights.py >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] numpy v2 benchmark" | tee -a "$LOG"
"$CEAIR" -B scripts/run_eg_chpn_simulation_v2.py >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] build report tables" | tee -a "$LOG"
"$CEAIR" -B scripts/build_marshecho_report.py >> "$LOG" 2>&1
"$CEAIR" -B scripts/render_marshecho_report.py >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] invariant checks" | tee -a "$LOG"
"$CEAIR" -B scripts/verify_marshecho_v2.py >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] package copyable bundle" | tee -a "$LOG"
"$CEAIR" -B scripts/package_marshecho_bundle.py >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] full pytest (no torch)" | tee -a "$LOG"
"$CEAIR" -m pytest -q >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] finalize done" | tee -a "$LOG"
