"""Reproducibility harness for Marsh-Echo (九皋).

Default mode proves run-to-run determinism: the same seed and configuration are
trained twice and the test-window scores must be bit-identical.  ``--full``
additionally re-exports the weights and compares the SHA-256 against the
shipped manifest (same machine, same torch/CUDA build).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import torch  # noqa: F401
except ModuleNotFoundError:
    print("需要 torch：请用 D:/venv/egchpn 运行本脚本（训练环境，不进镜像）")
    raise SystemExit(2)

from research.egchpn_torch.train import GRID, run_one  # noqa: E402

MANIFEST = ROOT / "app" / "algorithms" / "weights" / "marshecho_v2_0.manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--dgp", default="v1")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--n-customers", type=int, default=1200)
    parser.add_argument("--full", action="store_true", help="also re-export weights and compare sha256 with the manifest")
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    workspace = Path(tempfile.mkdtemp(prefix="marshecho_repro_"))
    try:
        results = []
        for attempt in (1, 2):
            out = workspace / f"attempt{attempt}"
            record = run_one(args.seed, args.dgp, "none", GRID[1], device, out, args.epochs, args.hidden, args.layers, n_customers=args.n_customers)
            path = out / args.dgp / f"scores_marshecho_none_seed{args.seed}.npz"
            payload = np_load(path)
            results.append((record, payload))
            print(f"attempt {attempt}: wall={record['wall_seconds']}s best_val={record['best_val']:.6f}")
        first, second = results[0][1], results[1][1]
        identical = all((first[key] == second[key]).all() for key in first.files)
        print(f"determinism: {'PASS' if identical else 'FAIL'} (bit-identical across repeats)")
        status = 0 if identical else 1
        if args.full:
            before = json.loads(MANIFEST.read_text(encoding="utf-8"))["sha256"] if MANIFEST.exists() else ""
            subprocess.run([sys.executable, "-B", str(ROOT / "research/egchpn_torch/export_weights.py")], check=True)
            after = json.loads(MANIFEST.read_text(encoding="utf-8"))["sha256"]
            same = bool(before) and before == after
            print(f"weights sha256 before={before[:16]}... after={after[:16]}... -> {'PASS' if same else 'DIFFERS (retrained from a different sweep state)'}")
        return status
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def np_load(path: Path):
    import numpy as np

    return np.load(path)


if __name__ == "__main__":
    raise SystemExit(main())
