"""Gate: exit 0 only when the paired A/B nominates a given tree as a winner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT.parents[1] / "docs" / "实验" / "marshecho-final-recipe-ab-v2.0.json"


def main() -> int:
    tree = sys.argv[1] if len(sys.argv) > 1 else "runs_selq_gcdr"
    if not ARTIFACT.exists():
        print(f"missing artifact: {ARTIFACT}")
        return 2
    winners = json.loads(ARTIFACT.read_text(encoding="utf-8")).get("winners") or []
    print(f"winners={winners}")
    return 0 if tree in winners else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
