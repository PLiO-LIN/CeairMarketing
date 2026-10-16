"""Research-only training code for Marsh-Echo (EG-CHPN v2).

This package is intentionally outside ``app/``: the Docker image copies only
``app/`` and CI runs pytest without torch.  Nothing here may be imported by
``app/`` or by ``tests/``; the deployed inference path is the numpy runtime in
``app/algorithms/eg_chpn_runtime.py`` plus the exported ``.npz`` weights.
"""
