"""Full-scale confirmation of the admissibility loss term before it ships.

The original A/B ran on a reduced population.  Stage 3 would ship the term, so
this check repeats the comparison at the production configuration on two seeds
and records whether the pre-filter invalid ranking really goes to zero and
whether policy value improves.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.egchpn_torch.train import GRID, run_one  # noqa: E402

_spec_loader = __import__("importlib.util", fromlist=["util"])

_spec = _spec_loader.spec_from_file_location("eg_chpn_v2_full", ROOT / "scripts" / "run_eg_chpn_simulation_v2.py")
_v2 = _spec_loader.module_from_spec(_spec)
sys.modules["eg_chpn_v2_full"] = _v2
assert _spec.loader is not None
_spec.loader.exec_module(_v2)

SEEDS = [13, 29]
VARIANTS = [0.0, 0.5]
CONFIG = GRID[4]
OUT_DIR = ROOT / "research" / "egchpn_torch" / "runs_gcfull"


def main() -> int:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    rows = []
    for seed in SEEDS:
        sim = _v2.simulate(seed, n_customers=3000, dgp="v1")
        test = np.flatnonzero(sim.days >= _v2.TRAIN_DAYS)
        for gate_consistency in VARIANTS:
            record = run_one(
                seed,
                "v1",
                "none",
                CONFIG,
                device,
                OUT_DIR,
                2000,
                128,
                3,
                n_customers=3000,
                gate_consistency=gate_consistency,
            )
            scores = np.load(OUT_DIR / "v1" / f"scores_marshecho_none_seed{seed}.npz")
            pos = {int(node): index for index, node in enumerate(sim.customer_nodes)}
            index = np.array([pos[int(node)] for node in scores["test_index"]])
            metrics = _v2.policy_metrics_v2(sim, test, scores["tau"][index], selector="none")
            rows.append(
                {
                    "seed": seed,
                    "gate_consistency": gate_consistency,
                    "invalid_rule_rate_pre_filter": metrics["invalid_rule_rate_pre_filter"],
                    "invalid_latent_rate_pre_filter": metrics["invalid_latent_rate_pre_filter"],
                    "policy_value": metrics["policy_value"],
                    "uplift_rmse": metrics["uplift_rmse"],
                    "qini": metrics["qini"],
                    "val_loss": record["best_val"],
                    "wall_seconds": record["wall_seconds"],
                }
            )
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    summary = {}
    for gate_consistency in VARIANTS:
        subset = [row for row in rows if row["gate_consistency"] == gate_consistency]
        summary[str(gate_consistency)] = {
            "mean_invalid_pre": float(np.mean([row["invalid_rule_rate_pre_filter"] for row in subset])),
            "mean_policy_value": float(np.mean([row["policy_value"] for row in subset])),
            "mean_rmse": float(np.mean([row["uplift_rmse"] for row in subset])),
            "mean_qini": float(np.mean([row["qini"] for row in subset])),
        }
    payload = {
        "synthetic": True,
        "label": "流程验证（虚构）",
        "experiment": "可执行性损失项在生产配置下的全量确认",
        "protocol": f"seeds {SEEDS}、3000 客群、hidden 128 / 3 层 / 2000 epoch、GRID[4]（lr {CONFIG['lr']}, wd {CONFIG['wd']}）",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "summary": summary,
        "verdict": "采用" if summary["0.5"]["mean_invalid_pre"] <= summary["0.0"]["mean_invalid_pre"] and summary["0.5"]["mean_policy_value"] >= summary["0.0"]["mean_policy_value"] else "不采用（全量下未同时改善非法率与策略价值）",
    }
    target = REPO / "docs" / "实验" / "marshecho-gate-consistency-full.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "verdict": payload["verdict"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
