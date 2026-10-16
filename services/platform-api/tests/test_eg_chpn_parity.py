from pathlib import Path

import numpy as np
import pytest

from app.algorithms.eg_chpn_runtime import EGCHPNRuntime

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "marshecho_v2_parity.npz"
KEYS = ("g_raw", "g", "h1", "h0", "tau", "y1", "y0", "score", "z")

pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="parity fixture not exported yet")


def test_numpy_runtime_reproduces_the_torch_forward_pass():
    """The deployed NumPy runtime must compute the trained torch function."""

    runtime = EGCHPNRuntime.load()
    fixture = np.load(FIXTURE)
    got = runtime.forward_arrays(
        fixture["x"],
        fixture["type_ids"],
        fixture["H"],
        fixture["H_norm"],
        fixture["attrs"],
        fixture["hard_mask"],
        fixture["delta"],
        fixture["rel_ids"],
    )
    for key in KEYS:
        assert np.allclose(got[key], fixture[key], atol=1e-5), f"{key} diverges from torch"
        assert np.isfinite(got[key]).all(), f"{key} not finite"


def test_runtime_imports_no_torch():
    import sys

    EGCHPNRuntime.load()
    assert "torch" not in sys.modules


def test_semantic_hard_mask_forces_gate_to_zero():
    runtime = EGCHPNRuntime.load()
    fixture = np.load(FIXTURE)
    got = runtime.forward_arrays(
        fixture["x"],
        fixture["type_ids"],
        fixture["H"],
        fixture["H_norm"],
        fixture["attrs"],
        fixture["hard_mask"],
        fixture["delta"],
        fixture["rel_ids"],
    )
    blocked = np.flatnonzero(fixture["hard_mask"] == 0)
    assert blocked.size, "fixture must contain a non-eligible path"
    assert (got["g"][blocked] == 0).all()
