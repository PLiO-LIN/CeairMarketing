"""Record why the currently installed weights are the ones that shipped.

Reads the paired A/B, the early-stopping audit, the installed artifact and the
pre-candidate snapshot, and writes a single provenance artifact.  It refuses to
write anything unless the A/B names the shipped tree as a winner, so the audit
trail can never describe a model that was exported by accident.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
OUT = REPO / "docs" / "实验" / "marshecho-ship-decision-v2.0.json"
WEIGHTS = ROOT / "app/algorithms/weights/marshecho_v2_0.npz"
MANIFEST = ROOT / "app/algorithms/weights/marshecho_v2_0.manifest.json"
SNAPSHOT = ROOT / "research/egchpn_torch/snapshot_pre_stage3/app_algorithms_weights/marshecho_v2_0.npz"
SHIPPED_TREE = "runs_selq_gcdr"


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main() -> int:
    ab = json.loads((REPO / "docs/实验/marshecho-final-recipe-ab-v2.0.json").read_text(encoding="utf-8"))
    audit = json.loads((REPO / "docs/实验/marshecho-early-stopping-audit-v2.0.json").read_text(encoding="utf-8"))
    if SHIPPED_TREE not in (ab.get("winners") or []):
        print(f"refusing: paired A/B does not nominate {SHIPPED_TREE}; winners={ab.get('winners')}")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    arm = ab["arms"][SHIPPED_TREE]["by_dgp"]
    payload = {
        "synthetic": True,
        "label": "流程验证（虚构）",
        "decided_at": datetime.now().astimezone().isoformat(),
        "shipped_tree": SHIPPED_TREE,
        "recipe": "GRID[1] lr=3e-3 wd=0 lam_policy=0.1, hidden128 x3 layers, 2000 epochs, "
        "admissibility lambda=0.5 + DR pseudo-outcome weight 1.0, 10-member same-config ensemble",
        "decision_rule": ab["decision_rule"],
        "members": manifest.get("members"),
        "parameters_per_member": manifest.get("parameters_per_member"),
        "installed_sha256": sha(WEIGHTS),
        "manifest_sha256": manifest.get("sha256"),
        "superseded_shipment_sha256": sha(SNAPSHOT),
        "paired_test_window": {
            dgp: {
                metric: {
                    "baseline": values["baseline_mean"],
                    "shipped": values["candidate_mean"],
                    "delta": values["mean_delta"],
                    "delta_ci95": values.get("delta_ci95_bootstrap_seeds"),
                    "seeds_won": f"{values['candidate_wins']}/{arm[dgp]['seeds_paired']}",
                }
                for metric, values in arm[dgp]["metrics"].items()
            }
            for dgp in ("v1", "v2")
        },
        "rejected_change": {
            "what": "checkpoint-selection criterion (composite loss -> drop the Lagrangian penalty)",
            "measured": ab["arms"]["runs_final"]["by_dgp"]["v1"]["metrics"]["policy_value"]["mean_delta"],
            "why_rejected": audit["verdict"],
        },
        "open_question": audit["long_horizon_caveat"],
    }
    if payload["installed_sha256"] != payload["manifest_sha256"]:
        print(f"refusing: installed weights {payload['installed_sha256']} != manifest {payload['manifest_sha256']}")
        return 1
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.name} shipped={payload['installed_sha256'][:16]} members={payload['members']}")
    for dgp, metrics in payload["paired_test_window"].items():
        print(f"  {dgp}: value {metrics['policy_value']['baseline']:.1f}->{metrics['policy_value']['shipped']:.1f}, "
              f"rmse {metrics['uplift_rmse']['baseline']:.4f}->{metrics['uplift_rmse']['shipped']:.4f}, "
              f"invalid_pre {metrics['invalid_rule_rate_pre_filter']['baseline']:.3f}->{metrics['invalid_rule_rate_pre_filter']['shipped']:.3f}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
