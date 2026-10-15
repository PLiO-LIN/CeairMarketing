import numpy as np

from app.algorithms.oth_gct import CausalSample, GraphEdge, OTHGCT


def test_relation_aware_encoder_and_causal_heads_produce_uplift():
    features = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0]]
    edges = [
        GraphEdge(0, 3, "reveals_need", delta_days=2, evidence_confidence=0.9),
        GraphEdge(1, 3, "supports_product", delta_days=5, evidence_confidence=0.8),
        GraphEdge(2, 3, "concerns_route", delta_days=1, evidence_confidence=0.95),
    ]
    samples = [
        CausalSample(0, 0, 0.2), CausalSample(1, 0, 0.25),
        CausalSample(2, 0, 0.1), CausalSample(3, 0, 0.4),
        CausalSample(0, 1, 0.5), CausalSample(1, 1, 0.7),
        CausalSample(2, 1, 0.3), CausalSample(3, 1, 0.9),
    ]
    model = OTHGCT(input_dim=3, hidden_dim=8, seed=2).fit(features, edges, samples)
    uplift = model.predict_uplift(features, edges)
    assert uplift.shape == (4,)
    assert np.isfinite(uplift).all()
    assert not np.allclose(uplift, 0.0)


def test_confidence_and_temporal_edges_change_graph_representation():
    features = [[1, 0], [0, 1], [1, 1]]
    model = OTHGCT(input_dim=2, hidden_dim=6, seed=4)
    high = model.encode(features, [GraphEdge(0, 2, "has_evidence", 1, 0.95)])
    low = model.encode(features, [GraphEdge(0, 2, "has_evidence", 30, 0.2)])
    assert not np.allclose(high[2], low[2])
