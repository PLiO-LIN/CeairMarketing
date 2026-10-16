"""Export an ensemble Marsh-Echo artifact (same configuration, many seeds).

The A/B in ``docs/实验`` shows that averaging tau across same-configuration
checkpoints trained on independent synthetic populations improves policy value
by ~11% and uplift RMSE by ~20% on both data-generating processes.  This
script stacks those checkpoints into one ``.npz`` that the torch-free runtime
consumes transparently, and writes a parity fixture holding the *averaged*
torch outputs so CI can prove the ensemble forward is identical.
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

from app.algorithms.hypergraph_spec import ELIGIBILITY_HOPS, NODE_TYPES  # noqa: E402
from research.egchpn_torch.data import build_batch  # noqa: E402
from research.egchpn_torch.export_weights import SCHEMA_VERSION, parity_batch  # noqa: E402
from research.egchpn_torch.model import EGCHPNv2  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoints", nargs="+", required=True)
    parser.add_argument("--weights-out", required=True)
    parser.add_argument("--fixture-out", required=True)
    parser.add_argument("--dgp", default="v1")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    payload: dict[str, np.ndarray] = {"_schema_version": np.asarray([SCHEMA_VERSION], dtype=object).astype(str)}
    member_cfgs: list[dict] = []
    models: list[EGCHPNv2] = []
    for index, path in enumerate(sorted(Path(p) for p in args.checkpoints)):
        bundle = torch.load(path, map_location=device, weights_only=False)
        model = EGCHPNv2(**bundle["model_cfg"]).to(device)
        model.load_state_dict(bundle["state_dict"])
        model.eval()
        models.append(model)
        member_cfgs.append(bundle.get("cfg", {}))
        for name, parameter in bundle["state_dict"].items():
            payload[f"m{index}::{name.replace('.', '__')}"] = parameter.detach().cpu().numpy().astype(np.float32, order="C")

    sim = parity_batch(device)
    batch, _ = build_batch(sim, device)
    member_outputs: list[dict[str, np.ndarray]] = []
    with torch.no_grad():
        for model in models:
            out = model(batch, temperature=0.5)
            member_outputs.append({key: value.detach().cpu().numpy() for key, value in out.items() if value.dtype != torch.bool})
    averaged = dict(member_outputs[0])
    for key in ("tau", "y1", "y0", "score", "z"):
        averaged[key] = np.mean([member[key] for member in member_outputs], axis=0)

    parameter_count = int(sum(p.numel() for p in models[0].parameters()))
    payload["_meta"] = np.asarray(
        [
            json.dumps(
                {
                    "model": {"name": "marshecho", "name_zh": "九皋", "architecture": "EG-CHPN v2", "paper_name": "Marsh-Echo"},
                    "schema_version": SCHEMA_VERSION,
                    "members": len(models),
                    "member_configs": member_cfgs,
                    "config": models[0].cfg,
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
    out_path = Path(args.weights_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path, **payload)
    fixture_path = Path(args.fixture_out)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        fixture_path,
        x=batch.x.cpu().numpy(),
        type_ids=batch.type_ids.cpu().numpy(),
        H=batch.H.cpu().numpy(),
        H_norm=batch.H_norm.cpu().numpy(),
        attrs=batch.attrs.cpu().numpy(),
        hard_mask=batch.hard_mask.cpu().numpy(),
        delta=batch.delta.cpu().numpy(),
        rel_ids=batch.rel_ids.cpu().numpy(),
        **{key: value for key, value in averaged.items()},
    )
    manifest = {
        "weights": str(out_path),
        "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "bytes": out_path.stat().st_size,
        "members": len(models),
        "parameters_per_member": parameter_count,
        "fixture": str(fixture_path),
        "schema_version": SCHEMA_VERSION,
    }
    (out_path.parent / f"{out_path.stem}.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
