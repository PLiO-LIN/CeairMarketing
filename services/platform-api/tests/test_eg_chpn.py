import numpy as np

from app.algorithms.eg_chpn import EGCHPN
from app.algorithms.oth_gct import CausalSample, GraphEdge


def test_eg_chpn_gates_low_evidence_edges_and_emits_trace():
    features = [[1, 0], [0, 1], [1, 1]]
    edges = [GraphEdge(0, 2, "supports_product", 2, 0.95), GraphEdge(1, 2, "has_evidence", 8, 0.40)]
    samples = [CausalSample(0, 0, 0.2), CausalSample(1, 0, 0.1), CausalSample(2, 0, 0.3), CausalSample(0, 1, 0.5), CausalSample(1, 1, 0.2), CausalSample(2, 1, 0.7)]
    model = EGCHPN(input_dim=2, hidden_dim=8, confidence_floor=0.65, seed=3).fit(features, edges, samples)
    uplift, trace = model.predict_with_trace(features, edges)
    assert np.isfinite(uplift).all()
    assert trace.accepted_edges == 1
    assert trace.rejected_edges == 1
    assert trace.decisions[1].reason == "evidence_below_floor"
