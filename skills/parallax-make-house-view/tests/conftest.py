"""Pytest path-resolution for make-house-view tests.

Ensures `import maker`, `import cross_country`, etc. resolve to this
skill's modules and that the shared `_parallax/house-view/` modules
resolve too.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
SKILL_DIR = HERE.parent
SHARED_DIR = (SKILL_DIR / ".." / "_parallax" / "house-view").resolve()

for p in (SKILL_DIR, SHARED_DIR):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
