"""Tensor adapters from the v2 simulator to the PyTorch trainer."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.egchpn_torch.model import Batch  # noqa: E402

_V2_PATH = ROOT / "scripts" / "run_eg_chpn_simulation_v2.py"
_spec = importlib.util.spec_from_file_location("eg_chpn_v2_sim", _V2_PATH)
_sim = importlib.util.module_from_spec(_spec)
sys.modules["eg_chpn_v2_sim"] = _sim
assert _spec.loader is not None
_spec.loader.exec_module(_sim)


def simulate(seed: int, dgp: str = "v1", n_customers: int = 1800):
    return _sim.simulate(seed, n_customers=n_customers, dgp=dgp)


def build_batch(sim, device: torch.device, pairwise: bool = False) -> tuple[Batch, dict[str, np.ndarray]]:
    types = sorted(set(sim.spec.node_types))
    type_ids = np.asarray([types.index(t) for t in sim.spec.node_types], dtype=np.int64)
    if pairwise:
        rows: list[tuple[int, int]] = []
        keys: list[str] = []
        deltas: list[float] = []
        masks: list[float] = []
        attrs: list[list[float]] = []
        for edge in sim.spec.hyperedges:
            if "AudienceSnapshot" not in edge.member_types:
                continue
            anchor = edge.member_nodes[edge.member_types.index("AudienceSnapshot")]
            for position, node_type in enumerate(edge.member_types):
                if node_type == "AudienceSnapshot":
                    continue
                relation = next((rel for rel, src, dst in edge.hops if src == node_type or dst == node_type), "supports_product")
                rows.append((edge.member_nodes[position], anchor))
                keys.append(relation)
                deltas.append(edge.delta_days)
                masks.append(1.0 if edge.status == "eligible" else 0.0)
                attrs.append(list(edge.gate_vector()))
        matrix = np.zeros((len(sim.spec.node_types), len(rows)), dtype=np.float32)
        for index, (source, target) in enumerate(rows):
            matrix[source, index] = 1.0
            matrix[target, index] = 1.0
    else:
        matrix = sim.spec.incidence().astype(np.float32)
        keys = list(sim.spec.keys())
        deltas = list(sim.spec.delta_days())
        masks = list(sim.spec.hard_mask())
        attrs = [list(row) for row in sim.spec.gate_attrs()]
    vocab = {key: index for index, key in enumerate(sorted(set(keys)))}
    rel_ids = np.asarray([vocab[key] for key in keys], dtype=np.int64)
    degree_v = matrix.sum(axis=1).clip(min=1.0)
    degree_e = matrix.sum(axis=0).clip(min=1.0)
    h_norm = (matrix / degree_v[:, None]) / np.sqrt(degree_e)[None, :]
    n = len(sim.spec.node_types)
    group_ids = np.zeros(n, dtype=np.int64)
    cost = np.zeros(n, dtype=np.float32)
    margin = np.zeros(n, dtype=np.float32)
    for position, node in enumerate(sim.customer_nodes):
        edge = sim.spec.hyperedges[position]
        rule_position = edge.member_types.index("BusinessRule") if "BusinessRule" in edge.member_types else 0
        group_ids[node] = edge.member_nodes[rule_position]
        cost[node] = 1.0
        margin[node] = 100.0
    batch = Batch(
        x=torch.as_tensor(sim.spec.node_features, dtype=torch.float32, device=device),
        type_ids=torch.as_tensor(type_ids, device=device),
        H=torch.as_tensor(matrix, device=device),
        H_norm=torch.as_tensor(h_norm, dtype=torch.float32, device=device),
        attrs=torch.as_tensor(np.asarray(attrs, dtype=np.float32), device=device),
        hard_mask=torch.as_tensor(np.asarray(masks, dtype=np.float32), device=device),
        delta=torch.as_tensor(np.asarray(deltas, dtype=np.float32), device=device),
        rel_ids=torch.as_tensor(rel_ids, device=device),
        group_ids=torch.as_tensor(group_ids, device=device),
        cost=torch.as_tensor(cost, device=device),
        margin=torch.as_tensor(margin, device=device),
    )
    arrays = {
        "customer_nodes": sim.customer_nodes,
        "days": sim.days,
        "treatment": sim.treatment,
        "outcome": sim.outcome,
        "y0": sim.y0,
        "y1": sim.y1,
        "eligible_rule": sim.eligible_rule,
        "eligible_latent": sim.eligible_latent,
        "in_holdout": sim.in_holdout,
        "propensity": sim.propensity,
        "status_eligible": np.asarray([edge.status == "eligible" for edge in sim.spec.hyperedges]),
    }
    return batch, arrays


def n_relations(sim) -> int:
    return len({edge.key for edge in sim.spec.hyperedges})


def n_types(sim) -> int:
    return len(set(sim.spec.node_types))
