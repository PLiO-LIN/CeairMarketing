#!/usr/bin/env bash
# Stage 2 continuation training for Marsh-Echo (九皋).
#
# Two real gaps are filled here, not filler compute:
#   (1) the pre-registered second data-generating process (dgp=v2) has zero
#       runs: main model, all 11 component ablations and the 3 torch baselines
#       over 10 seeds;
#   (2) larger / longer-trained candidate models (hidden 192 x 4 layers,
#       6000 epochs, and a second learning-rate point) written to a separate
#       tree so the shipped checkpoint is chosen by validation loss only.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=/d/venv/egchpn/Scripts/python.exe
S10=13,29,41,53,67,83,97,101,113,127
LOGDIR=research/egchpn_torch

# --- dgp v2 matrix -------------------------------------------------------
nohup "$PY" -B research/egchpn_torch/train.py --dgps v2 --ablations none,no_gate,no_dual_tower,no_temporal,no_balance \
  --seeds $S10 --epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --tag s1 \
  --out research/egchpn_torch/runs > $LOGDIR/s1.log 2>&1 &
nohup "$PY" -B research/egchpn_torch/train.py --dgps v2 --ablations no_counterfactual,no_evidence_loss,no_lagrangian,no_policy_head,gate_deterministic_only,no_hypergraph \
  --seeds $S10 --epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --tag s2 \
  --out research/egchpn_torch/runs > $LOGDIR/s2.log 2>&1 &
sleep 300
nohup "$PY" -B research/egchpn_torch/train.py --dgps v2 --skip-ablations --baselines tarnet,dragonnet,gat_trained \
  --seeds $S10 --epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --tag s3 \
  --out research/egchpn_torch/runs > $LOGDIR/s3.log 2>&1 &

# --- longer / larger candidate models (separate tree) --------------------
# Staggered behind the dgp-v2 matrix so host RAM stays above ~1.5 GB.
sleep 600
nohup "$PY" -B research/egchpn_torch/train.py --dgps v1,v2 --ablations none \
  --seeds $S10 --epochs 6000 --hidden 192 --layers 4 --n-customers 3000 --cfg-index 1 --tag l1 \
  --out research/egchpn_torch/runs_long > $LOGDIR/l1.log 2>&1 &
sleep 300
nohup "$PY" -B research/egchpn_torch/train.py --dgps v1,v2 --ablations none \
  --seeds $S10 --epochs 6000 --hidden 128 --layers 3 --n-customers 3000 --cfg-index 0 --tag l2 \
  --out research/egchpn_torch/runs_long > $LOGDIR/l2.log 2>&1 &

echo "stage2 launched: s1 s2 s3 (dgp v2 matrix) + l1 l2 (long candidates)"
