#!/usr/bin/env bash
# Launch the Marsh-Echo (九皋) training sweep across three GPU workers.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=/d/venv/egchpn/Scripts/python.exe
S10=13,29,41,53,67,83,97,101,113,127
S5=13,29,41,53,67
COMMON="--epochs 2000 --hidden 128 --layers 3 --n-customers 3000 --out research/egchpn_torch/runs"
nohup "$PY" -B research/egchpn_torch/train.py --grid --ablations none --seeds $S5 --dgps v1 --tag w1 $COMMON > research/egchpn_torch/w1.log 2>&1 &
nohup "$PY" -B research/egchpn_torch/train.py --ablations no_hypergraph,no_gate,gate_deterministic_only,no_dual_tower,no_temporal --seeds $S10 --dgps v1 --tag w2 $COMMON > research/egchpn_torch/w2.log 2>&1 &
nohup "$PY" -B research/egchpn_torch/train.py --ablations no_balance,no_counterfactual,no_evidence_loss,no_lagrangian,no_policy_head --baselines tarnet,dragonnet,gat_trained --seeds $S10 --dgps v1 --tag w3 $COMMON > research/egchpn_torch/w3.log 2>&1 &
echo "launched w1 w2 w3"
