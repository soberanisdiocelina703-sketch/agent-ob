"""Pytest root config: make server/, sdk/, agent/ importable without packaging.

Demo scope decision (plan.md §2): no editable installs on Windows —
sys.path injection keeps the toolchain to a single venv.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
for sub in ("server", "sdk", "agent"):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
