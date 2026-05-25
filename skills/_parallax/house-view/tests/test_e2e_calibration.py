"""End-to-end tests for the calibration_status flip surface.

The contract under test: per loader.md §6.2 generate-row conditional fields
and load-house-view/SKILL.md Step 4 6b, ``metadata.calibration_status``
(and the corresponding audit-row field) must be ``empirical_phase1`` iff
the active calibration manifest is signed AND its
``provenance.methodology_section != "GUESS"`` AND
``provenance.backtest_ref is not None``. Otherwise ``heuristic_phase0``.

These tests sit alongside ``test_e2e.py`` and follow its helper conventions
(duplicated inline rather than imported to dodge the pytest conftest
collision pattern between make-house-view/ and judge-house-view/).

KNOWN GAP DOCUMENTED HERE (see DECISIONS.md follow-up):
The v2 plan §10 retention #3 claims "calibration_status passthrough requires
zero code change." That is TRUE for the LLM-orchestrated
``load-house-view`` skill (Step 4 reads ``manifest_cache.load_manifest()``
in prose at runtime and the LLM decides which string to emit). It is
FALSE for the programmatic ``make-house-view`` maker path
(``make-house-view/maker.py`` lines 470 + 655 hardcode ``"heuristic_phase0"``
and never import ``manifest_cache``). Tests 1 and 3 therefore assert the
current pinned-Phase-0 behavior. Test 2 documents the missing flip wiring
via ``pytest.xfail(strict=True)`` so that the moment maker.py is wired to
consult the manifest, the xfail will flip to a hard failure and force this
test to be re-affirmed as a positive assertion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
MAKER_DIR = REPO / "skills" / "make-house-view"
JUDGE_DIR = REPO / "skills" / "judge-house-view"
SHARED_DIR = REPO / "skills" / "_parallax" / "house-view"
MAKER_FIXTURES = MAKER_DIR / "tests" / "fixtures"

for _p in (SHARED_DIR, MAKER_DIR, JUDGE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gate_present  # noqa: E402
import maker  # noqa: E402
import manifest_cache  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — duplicated from test_e2e.py per the file-header note.
# ---------------------------------------------------------------------------


def build_mock_mcp_aligned() -> dict[str, Any]:
    us = json.loads((MAKER_FIXTURES / "us_macro_indicators.json").read_text())
    jp = json.loads((MAKER_FIXTURES / "japan_tactical.json").read_text())
    cn = json.loads((MAKER_FIXTURES / "china_macro_indicators.json").read_text())
    tl = json.loads((MAKER_FIXTURES / "telemetry_full.json").read_text())
    return {
        "list_macro_countries": {
            "success": True,
            "markets": ["United States", "Japan", "China"],
        },
        "telemetry": tl,
        ("United States", "macro_indicators"): us,
        ("Japan", "tactical"): jp,
        ("China", "macro_indicators"): cn,
    }


class _MockMCPRunner(maker.MCPRunner):
    def __init__(self, mcp: dict[str, Any]):
        self.mcp = mcp

    def list_macro_countries(self) -> dict[str, Any] | None:
        return self.mcp.get("list_macro_countries")

    def get_telemetry(self, fields: list[str]) -> dict[str, Any] | None:
        return self.mcp.get("telemetry")

    def macro_analyst_batch(
        self,
        requests: list[tuple[str, str]],
        concurrency: int = 8,
        per_call_timeout_s: int = 45,
    ) -> dict[tuple[str, str], dict[str, Any] | None]:
        return {(m, c): self.mcp.get((m, c)) for m, c in requests}


def _run_maker(mcp: dict[str, Any], view_dir: Path) -> maker.MakerResult:
    runner = _MockMCPRunner(mcp)
    orch = maker.MakerOrchestrator(maker.MakerOptions(view_dir=view_dir))

    def _mock_gate(*args, **_kw):
        return gate_present.GateResult(disposition="confirm", final_draft=args[0])

    with patch("gate_present.run_gate_loop", side_effect=_mock_gate):
        return orch.execute_synthesis(
            mcp=runner,
            dispose_fn=lambda _: "confirm",
            edit_fn=lambda _, __: ({}, None),
        )


def _read_save_audit_row(view_dir: Path) -> dict[str, Any]:
    """Return the most recent save/generate audit row from audit.jsonl."""
    audit_path = view_dir / "audit.jsonl"
    assert audit_path.exists(), "audit.jsonl missing after maker save"
    rows = [json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()]
    save_rows = [r for r in rows if r.get("action") in ("save", "generate")]
    assert save_rows, f"no save/generate audit row in {rows}"
    return save_rows[-1]


def _build_empirical_phase_manifest() -> dict[str, Any]:
    """Manifest shape mirroring the empirical-phase contract per
    load-house-view Step 4 6b (non-GUESS methodology + non-null backtest_ref).
    Shape matches the production manifest dict per
    test_skill_integration._build_signed_manifest (without re-signing —
    the maker would consult the orchestrator's RETURN, not re-verify).
    """
    return {
        "schema_version": "1.0.0",
        "calibration_version": "backtested-2026-Q2.1",
        "org_id": "parallax-default",
        "issued_at": "2026-04-25T12:00:00Z",
        "manifest_expires_at": "2027-01-01T00:00:00Z",
        "signing_key_id": "test-key-id",
        "provenance": {
            "methodology_section": "backtested-2026Q2",
            "backtest_ref": "sha256:abc1234567890def",
        },
        "values": {},
    }


# ---------------------------------------------------------------------------
# Test 1 — Default save carries heuristic_phase0 (today's pinned behavior).
# ---------------------------------------------------------------------------


def test_e2e_default_save_carries_heuristic_phase0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default-state invariant: with no manifest customization, both
    view.yaml.metadata.calibration_status AND the generate audit row's
    calibration_status field must be ``"heuristic_phase0"``.

    This is the "today" state — guards against a regression that would
    silently ship empirical_phase1 before calibration actually lands. It
    also pins the audit-row schema per loader.md §6.2 (the generate row
    must carry the conditional ``calibration_status`` field).
    """
    view_dir = tmp_path / "active-house-view"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    res = _run_maker(build_mock_mcp_aligned(), view_dir)
    assert res.disposition == "confirm"

    # view.yaml side
    view = yaml.safe_load((view_dir / "view.yaml").read_text())
    assert view["metadata"]["calibration_status"] == "heuristic_phase0", (
        "view.yaml.metadata.calibration_status must be heuristic_phase0 "
        f"by default; got {view['metadata'].get('calibration_status')!r}"
    )

    # audit.jsonl side (per loader.md §6.2 conditional fields on the
    # generate row)
    audit_row = _read_save_audit_row(view_dir)
    assert audit_row.get("calibration_status") == "heuristic_phase0", (
        "audit generate row must carry calibration_status='heuristic_phase0' "
        f"by default; got {audit_row.get('calibration_status')!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Mocked empirical manifest should flip the save to phase1.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Documented gap: v2 plan §10 retention #3 claims calibration_status "
        "passthrough requires zero code change. That holds for the LLM-driven "
        "load-house-view path (Step 4 6b in SKILL.md is prose). It does NOT "
        "hold for make-house-view/maker.py, which hardcodes "
        "'heuristic_phase0' at lines 470 and 655 and never imports "
        "manifest_cache. Until maker.py is wired to call "
        "manifest_cache.load_manifest() and branch on the returned "
        "provenance, monkeypatching the loader cannot reach the maker. "
        "When the wiring lands, strict=True flips this xfail to XPASS and "
        "forces the test to be promoted to a positive assertion."
    ),
)
def test_e2e_mocked_empirical_manifest_flips_save_to_phase1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the documented flip mechanism: when load_manifest returns
    an empirical-phase manifest (non-GUESS methodology, non-null
    backtest_ref), both view.yaml and the audit row must carry
    ``calibration_status == "empirical_phase1"``.

    We monkeypatch at BOTH the canonical module attribute
    (``manifest_cache.load_manifest``) AND on the ``maker`` module
    namespace (in case maker did ``from manifest_cache import
    load_manifest``). The xfail above documents why this currently
    cannot flip — maker.py never imports either form.
    """
    view_dir = tmp_path / "active-house-view"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    empirical_manifest = _build_empirical_phase_manifest()

    def _fake_load_manifest(*args, **kwargs):
        return empirical_manifest

    # Patch on the source module.
    monkeypatch.setattr(
        manifest_cache, "load_manifest", _fake_load_manifest, raising=True
    )
    # Patch on the maker module's namespace if it imported the symbol
    # directly (``from manifest_cache import load_manifest``). setattr
    # with raising=False is a no-op if the attribute isn't there.
    if hasattr(maker, "load_manifest"):
        monkeypatch.setattr(maker, "load_manifest", _fake_load_manifest, raising=True)
    # Same for the manifest_cache attribute on the maker module (in case
    # maker did ``import manifest_cache`` and calls
    # ``manifest_cache.load_manifest(...)``).
    if hasattr(maker, "manifest_cache"):
        monkeypatch.setattr(
            maker.manifest_cache, "load_manifest", _fake_load_manifest, raising=True
        )

    res = _run_maker(build_mock_mcp_aligned(), view_dir)
    assert res.disposition == "confirm"

    view = yaml.safe_load((view_dir / "view.yaml").read_text())
    assert view["metadata"]["calibration_status"] == "empirical_phase1", (
        "view.yaml must flip to empirical_phase1 when manifest is "
        "empirically-calibrated; got "
        f"{view['metadata'].get('calibration_status')!r}"
    )

    audit_row = _read_save_audit_row(view_dir)
    assert audit_row.get("calibration_status") == "empirical_phase1", (
        "audit generate row must flip to empirical_phase1 in lockstep "
        f"with view.yaml; got {audit_row.get('calibration_status')!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Manifest missing or invalid falls back to heuristic_phase0.
# ---------------------------------------------------------------------------


def test_e2e_manifest_missing_or_invalid_falls_back_to_heuristic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the fallback behavior: when the manifest loader raises
    (DeadStateNoFallback, ManifestExpired, anything), the maker save
    must still complete and ship ``heuristic_phase0``. NEVER crash.

    Per load-house-view Step 4.1a: "Capture manifest and status (handle
    exceptions by falling back to status='PHASE_0_FALLBACK')." The maker
    path currently achieves this by hardcoding heuristic_phase0 (never
    calling the loader at all); patching the loader to raise should
    therefore not crash and should still produce a phase0 save. If
    maker.py is later wired to consult the loader, the try/except
    contract above must still hold and this test will continue to pass.
    """
    view_dir = tmp_path / "active-house-view"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    def _raise_dead_state(*args, **kwargs):
        raise manifest_cache.DeadStateNoFallback(
            "test injection: no manifest in cache and no fresh manifest"
        )

    monkeypatch.setattr(
        manifest_cache, "load_manifest", _raise_dead_state, raising=True
    )
    if hasattr(maker, "load_manifest"):
        monkeypatch.setattr(maker, "load_manifest", _raise_dead_state, raising=True)
    if hasattr(maker, "manifest_cache"):
        monkeypatch.setattr(
            maker.manifest_cache, "load_manifest", _raise_dead_state, raising=True
        )

    # Must not raise.
    res = _run_maker(build_mock_mcp_aligned(), view_dir)
    assert res.disposition == "confirm", (
        f"Maker must complete the save even when manifest load fails; "
        f"got disposition={res.disposition!r}"
    )

    # Phase-0 invariant on both surfaces.
    view = yaml.safe_load((view_dir / "view.yaml").read_text())
    assert view["metadata"]["calibration_status"] == "heuristic_phase0", (
        "view.yaml must fall back to heuristic_phase0 when manifest load "
        f"fails; got {view['metadata'].get('calibration_status')!r}"
    )
    audit_row = _read_save_audit_row(view_dir)
    assert audit_row.get("calibration_status") == "heuristic_phase0", (
        "audit row must fall back to heuristic_phase0 in lockstep with "
        f"view.yaml; got {audit_row.get('calibration_status')!r}"
    )

    # No crash diagnostic leaked into the result.
    diag = getattr(res, "diagnostics", None) or {}
    diag_text = json.dumps(diag, default=str).lower()
    assert "traceback" not in diag_text, (
        f"Maker diagnostics carry a traceback; manifest-fail fallback "
        f"should be clean: {diag}"
    )
