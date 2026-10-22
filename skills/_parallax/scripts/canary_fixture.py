"""Shared hermetic canary-term fixture for the scripts/ test modules.

Lives in a plain module rather than a `conftest.py`: `run-gate-tests.sh`
asserts at most one conftest.py per top-level test root, and `skills/_parallax`
already spends that budget on `white-label/tests/conftest.py`. Test modules
import `hermetic_extra_terms` into their own namespace; being autouse, it then
applies to every test in the importing module.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_bundle as bb


@pytest.fixture(autouse=True)
def hermetic_extra_terms(monkeypatch, tmp_path_factory):
    """Tests must not depend on the operator's home directory.

    load_canary_terms() fails closed when ~/.claude/parallax-canary-extra.txt
    is absent (CI runners, fresh clones). When the real file exists, use it
    unchanged (full-strength). Otherwise substitute a synthetic extra list:
    one sentinel term plus each CANARY_ALLOWLIST entry's trailing token (the
    text after its final underscore, e.g. derived from "pick_toscore"),
    preserving the allowlist-overlaps-a-term invariant that
    test_canary_allowlist_does_not_mask_sibling_identifiers asserts is
    non-vacuous. Every line derives at runtime from already-public literals.
    Fragility note: the derived token stays clean only while no tracked
    archive/symlink/binary carries those bytes on the raw-scan path (no
    allowlist masking there); if that ever changes, CI fails while a machine
    with the real file passes -- the failure message will name the file.
    Tests that need the file ABSENT re-point EXTRA_CANARY_FILE themselves;
    their in-body monkeypatch.setattr overrides this fixture's.

    The sentinel below is deliberately concatenated from two literals: once
    loaded as an extra term, its full contiguous form would otherwise match
    itself right here in this tracked source file under the repo-wide
    restricted-terms scan (test_this_repo_has_no_restricted_terms).
    """
    if bb.EXTRA_CANARY_FILE.exists():
        return
    extra = tmp_path_factory.mktemp("canary") / "synthetic-extra.txt"
    sentinel = "zz-synthetic-extra-term" + "-for-tests"
    lines = [sentinel]
    lines += [allowed.split("_")[-1] for allowed in bb.CANARY_ALLOWLIST]
    extra.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(bb, "EXTRA_CANARY_FILE", extra)
