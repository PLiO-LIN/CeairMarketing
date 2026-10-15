"""Validate the generated EG-CHPN simulation artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[1] / "docs" / "实验"


def main() -> None:
    summary = json.loads((OUT / "eg-chpn-simulation-v1.0.json").read_text(encoding="utf-8"))
    with (OUT / "eg-chpn-simulation-v1.0.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert summary["synthetic"] is True
    assert len(rows) == 25
    assert {int(row["seed"]) for row in rows} == {13, 29, 41, 53, 67}
    assert {row["method"] for row in rows} == {
        "random_feasible", "response_only", "tabular_t_learner",
        "oth_gct_no_evidence_gate", "eg_chpn_graph_evidence_gate",
    }
    by_method = {item["method"]: item for item in summary["summary"]}
    assert by_method["eg_chpn_graph_evidence_gate"]["invalid_selection_rate_mean"] == 0.0
    assert by_method["oth_gct_no_evidence_gate"]["invalid_selection_rate_mean"] > 0.0
    for item in summary["summary"]:
        for key, value in item.items():
            if key.endswith(("_mean", "_ci95")):
                assert isinstance(value, (int, float))
    print("EG-CHPN simulation artifact validation: PASS")
    print(f"rows={len(rows)} methods={len(by_method)} seeds={len(summary['seeds'])}")


if __name__ == "__main__":
    main()
