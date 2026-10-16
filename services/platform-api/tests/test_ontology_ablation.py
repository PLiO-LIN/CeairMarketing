"""Regression guard for the ontology ablation experiment behind the defense deck.

The deck cites these figures, so CI must fail if the production gates ever stop
blocking a case, start over-blocking a legal one, or drift from the committed artifact.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = API_ROOT.parents[1] / "docs" / "实验" / "ontology-ablation-v1.0.summary.json"

spec = importlib.util.spec_from_file_location("ontology_ablation", API_ROOT / "scripts" / "ontology_ablation.py")
ablation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ablation)

_cache: dict[str, dict] = {}
NUMERIC_KEYS = ("cases", "must_block", "blocked", "block_rate", "false_accept", "over_block", "localization_rate")


def results() -> dict:
    if not _cache:
        _cache["summary"] = ablation.run_all()
    return _cache["summary"]


def test_registry_matches_live_code():
    from app.ontology.semantic_model import SEMANTIC_MODEL_VERSION

    summary = results()
    assert summary["registry"]["semantic_model_version"] == SEMANTIC_MODEL_VERSION
    assert summary["registry"]["object_types"] == 41
    assert summary["registry"]["relation_types"] >= 44
    assert summary["registry"]["registered_attributes"] >= 200


def test_no_gate_lets_an_unsellable_plan_through():
    summary = results()
    for tier in summary["tiers"].values():
        assert tier.get("false_accept") == 0
        assert tier.get("over_block") == 0
        assert tier.get("block_rate") in (None, 1.0)
    assert summary["overall"]["block_rate"] == 1.0


def test_baseline_graph_admits_a_complete_eligibility_path():
    summary = results()
    baseline = summary["baseline"]
    assert baseline["gate_eligible"] is True
    assert baseline["path_flight_to_product"] is True
    assert baseline["eligibility_hops"] == 3
    assert baseline["accepted_entities"] == baseline["evidence"]["baseline_entities"]
    assert baseline["evidence"]["entities_with_source_refs"] == baseline["evidence"]["baseline_entities"]


def test_adapter_is_deterministic():
    assert results()["baseline"]["evidence"]["deterministic_adapter"] is True


def test_committed_artifact_still_matches_the_gates():
    summary = results()
    assert SUMMARY_PATH.exists(), "docs/实验 artifact must be regenerated with scripts/ontology_ablation.py --write"
    committed = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    for key in NUMERIC_KEYS:
        assert committed["overall"][key] == summary["overall"][key]
    assert {row["id"]: row["blocked"] for row in committed["cases"]} == {row["id"]: row["blocked"] for row in summary["cases"]}
