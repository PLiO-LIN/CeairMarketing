#!/usr/bin/env bash
# Block until the continuation chain finishes (or 10 h elapse), then report the
# measured accounting so the >=8h requirement can be audited from evidence.
cd "$(dirname "$0")/../.."
LOG=research/egchpn_torch/wait.log
: > "$LOG"
START=$(date +%s)
while true; do
  if grep -q "continuation chain complete" research/egchpn_torch/continue.log 2>/dev/null; then
    echo "[$(date +%H:%M)] chain complete" | tee -a "$LOG"; break
  fi
  NOW=$(date +%s)
  if [ $(( NOW - START )) -ge 36000 ]; then echo "[$(date +%H:%M)] waiter cap reached (10h)" | tee -a "$LOG"; break; fi
  sleep 180
done
echo "=== progress ===" | tee -a "$LOG"
/d/venv/ceair/Scripts/python.exe -B scripts/marshecho_progress.py 2>&1 | tee -a "$LOG"
echo "=== verifier ===" | tee -a "$LOG"
/d/venv/ceair/Scripts/python.exe -B scripts/verify_marshecho_v2.py 2>&1 | tee -a "$LOG"
echo "=== continuation artifact ===" | tee -a "$LOG"
cat "../docs/实验/marshecho-continuation-v2.0.json" 2>/dev/null | tee -a "$LOG"
