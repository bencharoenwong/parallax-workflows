"""
Conftest for white-label loader tests.

The loader lives in a hyphenated directory (white-label) which is not a valid
Python package identifier, so standard import machinery cannot reach it.
This conftest loads the module via importlib and exposes it as a session-scoped
fixture named `loader_module`.  Individual tests monkeypatch module attributes
on that object.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_LOADER_PATH = (
    Path(__file__).parent.parent / "loader.py"
)


@pytest.fixture(scope="session")
def loader_module() -> ModuleType:
    """Load loader.py from its absolute path and return the module object."""
    spec = importlib.util.spec_from_file_location(
        "parallax_white_label_loader", _LOADER_PATH
    )
    assert spec is not None, f"Could not locate loader at {_LOADER_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["parallax_white_label_loader"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod
