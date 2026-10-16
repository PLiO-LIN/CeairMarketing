"""Export Marsh-Echo (九皋) weights for the torch-free numpy runtime.

Writes ``app/algorithms/weights/marshecho_v2_0.npz`` (fp32, C-order,
``allow_pickle=False``) plus ``tests/fixtures/marshecho_v2_parity.npz`` holding
a tiny graph's torch intermediate activations.  The parity fixture is what lets
CI — which has no torch — prove that the deployed numpy forward pass is the
same function that was trained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.egchpn_torch.data import build_batch, simulate  # noqa: E402
from research.egchpn_torch.model import EGCHPNv2  # noqa: E402

SCHEMA_VERSION = "marshecho-egchpn-v2.0"


def parity_batch(device: torch.device):
    """A deterministic 19-node / 3-hyperedge graph for the parity fixture."""

    from app.algorithms.hypergraph_spec import ELIGIBILITY_HOPS, Hyperedge, HypergraphSpec

    rng = np.random.default_rng(2026)
    types = ["Route", "Flight", "Cabin", "Fare", "Product", "ProductPackage", "BusinessRule", "Evidence"]
    node_types = types + ["AudienceSnapshot"] * 3 + types
    features = rng.uniform(0.0, 1.0, (len(node_types), 6)).astype(np.float32)
    order = ["ProductPackage", "AudienceSnapshot", "Product", "Fare", "Cabin", "Flight", "Route", "Evidence", "BusinessRule"]
    statuses = ["eligible", "pending", "eligible"]
    hyperedges = []
    for customer in range(3):
        base = 0 if customer != 1 else len(types) + 3
        members = {name: base + offset for offset, name in enumerate(types)}
        members["AudienceSnapshot"] = 8 + customer
        member_nodes = tuple(members[name] for name in order)
        hyperedges.append(
            Hyperedge(
                member_nodes=member_nodes,
                member_types=tuple(node_types[node] for node in member_nodes),
                hops=ELIGIBILITY_HOPS,
                status=statuses[customer],
                confidence=float(rng.uniform(0.7, 0.95)),
                freshness_days=float(rng.integers(0, 30)),
                rule_agreement=float(rng.uniform(0.6, 0.95)),
                source_stability=float(rng.uniform(0.6, 0.95)),
                delta_days=float(rng.integers(0, 40)),
            )
        )
    spec = HypergraphSpec(features, tuple(node_types), tuple(hyperedges))

    class _Sim:
        pass

    sim = _Sim()
    sim.spec = spec
    sim.customer_nodes = np.asarray([8, 9, 10], dtype=np.int64)
    sim.days = np.arange(3) % 90
    sim.treatment = np.asarray([1, 0, 1], dtype=int)
    sim.outcome = np.asarray([0.5, 0.3, 0.9], dtype=float)
    sim.y0 = np.asarray([0.4, 0.3, 0.6], dtype=float)
    sim.y1 = np.asarray([0.7, 0.4, 1.1], dtype=float)
    sim.eligible_rule = np.asarray([True, False, True])
    sim.eligible_latent = np.asarray([True, True, False])
    sim.in_holdout = np.asarray([False, True, False])
    sim.propensity = np.asarray([0.5, 0.5, 0.5], dtype=float)
    return sim


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=str(ROOT / "research/egchpn_torch/runs/v1/checkpoint_seed13.pt"))
    parser.add_argument("--weights-out", default=str(ROOT / "app/algorithms/weights/marshecho_v2_0.npz"))
    parser.add_argument("--fixture-out", default=str(ROOT / "tests/fixtures/marshecho_v2_parity.npz"))
    parser.add_argument("--expect-wd", type=float, default=None, help="refuse to export unless the checkpoint matches this weight decay")
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    bundle = torch.load(args.checkpoint, map_location=device, weights_only=False)
    loaded_cfg = bundle.get("cfg", {})
    if args.expect_wd is not None and abs(float(loaded_cfg.get("wd", -1)) - args.expect_wd) > 1e-12:
        raise SystemExit(f"checkpoint cfg mismatch: wd={loaded_cfg.get('wd')} != expected {args.expect_wd}")
    print(f"exporting checkpoint cfg={loaded_cfg}")
    model_cfg = bundle["model_cfg"]
    model = EGCHPNv2(**model_cfg).to(device)
    model.load_state_dict(bundle["state_dict"])
    model.eval()

    payload: dict[str, np.ndarray] = {"_schema_version": np.asarray([SCHEMA_VERSION], dtype=object).astype(str)}
    for name, parameter in model.state_dict().items():
        payload[name.replace(".", "__")] = parameter.detach().cpu().numpy().astype(np.float32, order="C")
    from app.algorithms.hypergraph_spec import ELIGIBILITY_HOPS, NODE_TYPES

    parameter_count = int(sum(p.numel() for p in model.parameters()))
    payload["_meta"] = np.asarray(
        [
            json.dumps(
                {
                    "model": {"name": "marshecho", "name_zh": "九皋", "architecture": "EG-CHPN v2", "paper_name": "Marsh-Echo"},
                    "schema_version": SCHEMA_VERSION,
                    "config": model_cfg,
                    "train_config": loaded_cfg,
                    "node_types": list(NODE_TYPES),
                    "relation_vocab": ["|".join(relation for relation, _, _ in ELIGIBILITY_HOPS)],
                    "parameters": parameter_count,
                    "torch_version": torch.__version__,
                    "device": str(device),
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "synthetic": True,
                    "label": "流程验证（虚构）",
                    "license": "Apache-2.0",
                },
                ensure_ascii=False,
            )
        ]
    )
    out = Path(args.weights_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, **payload)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()

    sim = parity_batch(device)
    batch, _ = build_batch(sim, device)
    with torch.no_grad():
        out_dict = model(batch, temperature=0.5)
    fixture = Path(args.fixture_out)
    fixture.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        fixture,
        x=batch.x.cpu().numpy(),
        type_ids=batch.type_ids.cpu().numpy(),
        H=batch.H.cpu().numpy(),
        H_norm=batch.H_norm.cpu().numpy(),
        attrs=batch.attrs.cpu().numpy(),
        hard_mask=batch.hard_mask.cpu().numpy(),
        delta=batch.delta.cpu().numpy(),
        rel_ids=batch.rel_ids.cpu().numpy(),
        g_raw=out_dict["g_raw"].cpu().numpy(),
        g=out_dict["g"].cpu().numpy(),
        h1=out_dict["h1"].cpu().numpy(),
        h0=out_dict["h0"].cpu().numpy(),
        tau=out_dict["tau"].cpu().numpy(),
        y1=out_dict["y1"].cpu().numpy(),
        y0=out_dict["y0"].cpu().numpy(),
        score=out_dict["score"].cpu().numpy(),
        z=out_dict["z"].cpu().numpy(),
    )
    manifest = {
        "weights": str(out),
        "sha256": digest,
        "bytes": out.stat().st_size,
        "parameters": int(sum(p.numel() for p in model.parameters())),
        "fixture": str(fixture),
        "schema_version": SCHEMA_VERSION,
    }
    (out.parent / f"{out.stem}.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
