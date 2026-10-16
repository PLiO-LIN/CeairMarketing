import numpy as np
import pytest

from app.algorithms.eg_chpn_runtime import ArtifactSchemaError, EGCHPNRuntime, SCHEMA_VERSION, load_default_runtime
from app.algorithms.hypergraph_spec import ELIGIBILITY_HOPS, Hyperedge, HypergraphSpec

TYPES = ("ProductPackage", "AudienceSnapshot", "Product", "Fare", "Cabin", "Flight", "Route", "Evidence", "BusinessRule")
CONTEXT = tuple(name for name in TYPES if name != "AudienceSnapshot")


def tiny_spec() -> HypergraphSpec:
    node_types = CONTEXT + ("AudienceSnapshot",) * 3 + CONTEXT
    features = np.linspace(0.0, 1.0, len(node_types) * 6, dtype=np.float32).reshape(len(node_types), 6)
    edges = []
    for customer, status in enumerate(("eligible", "pending", "eligible")):
        base = 11 if customer == 1 else 0
        members = (base, 8 + customer, *(base + offset for offset in range(1, len(CONTEXT))))
        member_types = tuple(node_types[index] for index in members)
        assert member_types == TYPES
        edges.append(
            Hyperedge(
                member_nodes=members,
                member_types=member_types,
                hops=ELIGIBILITY_HOPS,
                status=status,
                confidence=0.8,
                freshness_days=3.0,
                rule_agreement=0.9,
                source_stability=0.7,
                delta_days=5.0,
            )
        )
    return HypergraphSpec(features, node_types, tuple(edges))


def test_runtime_loads_and_predicts_finite_uplift():
    runtime = load_default_runtime()
    spec = tiny_spec()
    tau, trace = runtime.predict_from_spec(spec)
    assert tau.shape == (spec.node_features.shape[0],)
    assert np.isfinite(tau).all()
    assert trace.schema_version == SCHEMA_VERSION


def test_gate_zeroes_non_eligible_paths_and_reports_trace():
    runtime = load_default_runtime()
    tau, trace = runtime.predict_from_spec(tiny_spec())
    assert trace.accepted_edges == 2
    assert trace.rejected_edges == 1
    pending = trace.decisions[1]
    assert pending.status == "pending"
    assert pending.gate_value == 0.0
    assert pending.reason == "ontology_gate:pending"


def test_predictions_are_deterministic_across_loads():
    spec = tiny_spec()
    first, _ = EGCHPNRuntime.load().predict_from_spec(spec)
    second, _ = EGCHPNRuntime.load().predict_from_spec(spec)
    assert np.array_equal(first, second)


def test_partial_eligibility_path_is_flagged_as_unmatched() -> None:
    """A path missing hops is not in the training vocabulary and must say so."""

    runtime = load_default_runtime()
    spec = tiny_spec()
    edge = spec.hyperedges[0]
    partial = Hyperedge(
        member_nodes=edge.member_nodes,
        member_types=edge.member_types,
        hops=edge.hops[:4],
        status="pending",
        confidence=edge.confidence,
        freshness_days=edge.freshness_days,
        rule_agreement=edge.rule_agreement,
        source_stability=edge.source_stability,
        delta_days=edge.delta_days,
    )
    from app.algorithms.hypergraph_spec import HypergraphSpec

    degraded = HypergraphSpec(spec.node_features, spec.node_types, (partial,))
    _, trace = runtime.predict_from_spec(degraded)
    assert trace.unmatched_paths == 1
    assert "未出现在训练词表中" in trace.vocab_note


def test_incompatible_schema_is_rejected(tmp_path):
    import json

    path = tmp_path / "broken.npz"
    np.savez(
        path,
        _meta=np.asarray([json.dumps({"schema_version": "older", "config": {}, "node_types": [], "relation_vocab": [], "parameters": 0})]),
    )
    with pytest.raises(ArtifactSchemaError):
        EGCHPNRuntime.load(path)


def test_missing_artifact_is_reported(tmp_path):
    with pytest.raises(ArtifactSchemaError):
        EGCHPNRuntime.load(tmp_path / "absent.npz")
