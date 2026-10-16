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


def test_partial_ontology_graph_is_encoded_against_the_artifact_vocab():
    """A half-wired tenant path must score, not fail.

    The runtime used to demand that the observed node types equal the training
    vocabulary in size, so a graph containing only ProductPackage and
    AudienceSnapshot raised ArtifactSchemaError and the API answered 500.  Type
    ids now index the artifact vocabulary itself, which is also the only mapping
    that keeps the trained embedding rows aligned.
    """

    runtime = load_default_runtime()
    full = tiny_spec()
    keep = [index for index, name in enumerate(full.node_types) if name in ("ProductPackage", "AudienceSnapshot")]
    renumber = {old: new for new, old in enumerate(keep)}
    edge = Hyperedge(
        member_nodes=tuple(renumber[node] for node in keep),
        member_types=("ProductPackage", "AudienceSnapshot"),
        hops=(("targets_audience", "ProductPackage", "AudienceSnapshot"),),
        status="pending",
        confidence=0.8,
        freshness_days=3.0,
        rule_agreement=0.9,
        source_stability=0.7,
        delta_days=5.0,
    )
    partial = HypergraphSpec(
        full.node_features[keep],
        tuple(full.node_types[index] for index in keep),
        (edge,),
    )
    tau, trace = runtime.predict_from_spec(partial)
    assert np.isfinite(tau).all()
    assert trace.decisions[0].accepted is False
    assert tuple(runtime.last_encoding["node_types"]) == tuple(sorted(TYPES))
    assert runtime.last_encoding["missing_node_types"]


def test_type_ids_are_invariant_to_how_much_of_the_graph_is_present():
    """The same node type must land on the same embedding row in any graph.

    Deriving the alphabet from the types observed in one tenant's projection
    shifts every id as soon as a path is half wired, which changes τ̂ without
    changing anything the model was trained on.
    """

    runtime = load_default_runtime()
    full = tiny_spec()
    full_ids = runtime.spec_arrays(full)[0]
    keep = [index for index, name in enumerate(full.node_types) if name in ("Route", "Flight", "AudienceSnapshot")]
    subset = HypergraphSpec(
        full.node_features[keep],
        tuple(full.node_types[index] for index in keep),
        (),
    )
    subset_ids = runtime.spec_arrays(subset)[0]
    assert [full_ids[index] for index in keep] == list(subset_ids)
    assert len(set(full_ids)) == len(TYPES)


def test_unknown_node_type_is_still_rejected():
    runtime = load_default_runtime()
    spec = tiny_spec()
    corrupted = HypergraphSpec(spec.node_features, tuple(["AlienType"] * len(spec.node_types)), spec.hyperedges)
    with pytest.raises(ArtifactSchemaError):
        runtime.predict_from_spec(corrupted)


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
