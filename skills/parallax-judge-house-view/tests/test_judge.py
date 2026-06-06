"""End-to-end orchestrator tests for judge.run_judge.

Uses --dry mode with injected mock MCP responses (and an injected LLM
callback) so the tests don't require live MCP or Claude. The maker's
shared modules (cross_country / pillar_compose / pillar_formulas) may
not exist yet — the orchestrator gracefully degrades and we test that
fallback path explicitly.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
import yaml

import audit_chain
import judge
import recommendation as rec_mod
import stress


# ---------------------------------------------------------------------------
# Fixtures: seed a real ~/.parallax/active-house-view/-shaped dir with
# the fixture YAML and a freshly-chained audit.jsonl.
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_view_dict(fixtures_dir: Path) -> dict:
    return yaml.safe_load((fixtures_dir / "saved_view_30d_old.yaml").read_text())


@pytest.fixture
def active_view_dir(tmp_path: Path, fixture_view_dict: dict) -> Path:
    view_dir = tmp_path / "active-house-view"
    view_dir.mkdir()
    (view_dir / "view.yaml").write_text(yaml.safe_dump(fixture_view_dict, sort_keys=False))

    # Seed audit chain with a save row so verify_chain accepts it.
    audit_chain.append_entry(view_dir / "audit.jsonl", {
        "ts": "2026-04-24T09:30:00Z",
        "action": "save",
        "view_id": fixture_view_dict["metadata"]["view_id"],
        "version_id": fixture_view_dict["metadata"]["version_id"],
        "skill": "parallax-load-house-view",
        "applied": True,
    })
    return view_dir


@pytest.fixture
def report_dir(tmp_path: Path) -> Path:
    return tmp_path / "judge-reports"


# ---------------------------------------------------------------------------
# Phase-0 happy path.
# ---------------------------------------------------------------------------


def test_phase_0_loads_view(active_view_dir: Path):
    view = judge.phase_0_load_view(active_view_dir)
    assert view.data["metadata"]["view_name"] == "Q2 2026 House View (test fixture)"
    assert view.view_hash  # non-empty


def test_phase_0_raises_when_view_missing(tmp_path: Path):
    empty = tmp_path / "empty-view-dir"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        judge.phase_0_load_view(empty)


# ---------------------------------------------------------------------------
# End-to-end smoke (--dry with mocked MCP, no LLM).
# ---------------------------------------------------------------------------


def test_smoke_dry_run_aligned_fixture(
    active_view_dir: Path,
    report_dir: Path,
    fresh_aligned_responses: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Pin chain output to an isolated dir so the test doesn't pollute
    # ~/.parallax/reasoning-chains/.
    chain_dir = tmp_path / "chains"
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    config = judge.JudgeConfig(
        dry=True,
        mock_mcp_responses=fresh_aligned_responses,
        explicit=True,
        view_dir=active_view_dir,
        report_dir=report_dir,
    )
    result = judge.run_judge(config=config)

    # Post-2026-05-24 gate-review fix: _imputed_view_from_maker now correctly
    # reconstructs MarketResponse instances from phase_1's string-keyed dict
    # (previously it silently failed when "per_market" key was absent — the
    # gate review explicitly flagged this test as asserting the bug). With
    # the fresh_aligned_responses fixture's prose, the imputed view diverges
    # from the saved view's regional tilts → severity escalates above
    # drift_minor. The exact tier depends on the fixture; assert on the
    # bounded set so this test stays robust to fixture refreshes.
    assert result.severity in ("drift_minor", "drift_moderate", "drift_material")
    assert result.audit_entry is not None
    assert result.audit_entry["action"] == "judge"
    assert result.audit_entry["applied"] is False
    assert result.audit_entry["judged_view_id"] is not None
    # Verify the audit row carries the loader.md §6.2 required fields
    # for action="judge".
    for required in ("judged_view_id", "judged_version_id",
                     "view_age_days", "parallax_age_days",
                     "drift_summary", "recommendations"):
        assert required in result.audit_entry, f"missing required field {required}"


def test_smoke_dry_run_writes_report_bundle(
    active_view_dir: Path,
    report_dir: Path,
    fresh_divergent_responses: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    chain_dir = tmp_path / "chains"
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    config = judge.JudgeConfig(
        dry=True,
        mock_mcp_responses=fresh_divergent_responses,
        explicit=True,
        view_dir=active_view_dir,
        report_dir=report_dir,
    )
    result = judge.run_judge(config=config)

    assert result.report_dir is not None
    assert result.report_dir.exists()
    assert (result.report_dir / "report.md").exists()
    assert (result.report_dir / "report.json").exists()
    assert (result.report_dir / "mcp_responses.jsonl").exists()
    assert (result.report_dir / "audit_entry.json").exists()

    # mcp_responses.jsonl should be one line per MCP call.
    lines = (result.report_dir / "mcp_responses.jsonl").read_text().strip().splitlines()
    assert len(lines) == len(fresh_divergent_responses)
    for line in lines:
        # Each line is valid JSON with call + response keys.
        parsed = json.loads(line)
        assert "call" in parsed
        assert "response" in parsed


def test_audit_entry_is_appended_with_chain(
    active_view_dir: Path,
    report_dir: Path,
    fresh_aligned_responses: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    chain_dir = tmp_path / "chains"
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    config = judge.JudgeConfig(
        dry=True,
        mock_mcp_responses=fresh_aligned_responses,
        explicit=True,
        view_dir=active_view_dir,
        report_dir=report_dir,
    )
    judge.run_judge(config=config)

    # Audit chain has 2 entries now: the seed save + the judge row.
    entries = audit_chain.verify_chain(active_view_dir / "audit.jsonl")
    assert len(entries) == 2
    assert entries[1]["action"] == "judge"
    assert entries[1]["applied"] is False
    assert entries[1]["skill"] == "parallax-judge-house-view"


def test_view_yaml_is_not_modified(
    active_view_dir: Path,
    report_dir: Path,
    fresh_divergent_responses: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Read-only invariant: view.yaml bytes do not change."""
    chain_dir = tmp_path / "chains"
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)
    pre = (active_view_dir / "view.yaml").read_bytes()
    judge.run_judge(config=judge.JudgeConfig(
        dry=True,
        mock_mcp_responses=fresh_divergent_responses,
        explicit=True,
        view_dir=active_view_dir,
        report_dir=report_dir,
    ))
    post = (active_view_dir / "view.yaml").read_bytes()
    assert pre == post, "view.yaml must not be modified by the judge"


def test_provenance_yaml_is_not_created(
    active_view_dir: Path,
    report_dir: Path,
    fresh_divergent_responses: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Judge never writes provenance.yaml."""
    chain_dir = tmp_path / "chains"
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)
    judge.run_judge(config=judge.JudgeConfig(
        dry=True,
        mock_mcp_responses=fresh_divergent_responses,
        explicit=True,
        view_dir=active_view_dir,
        report_dir=report_dir,
    ))
    assert not (active_view_dir / "provenance.yaml").exists()


# ---------------------------------------------------------------------------
# Phase 5: LLM call path with citation-validator gate.
# ---------------------------------------------------------------------------


def test_phase_5_emits_no_recs_for_minor_severity(
    active_view_dir: Path,
    fresh_aligned_responses: dict,
):
    """LLM is not called below material severity."""
    called = {"count": 0}

    def fake_llm(prompt):
        called["count"] += 1
        return {"recommended_value": 1, "confidence": 0.8, "rationale": "x", "suggested_basis_statement_addendum": ""}

    view = judge.phase_0_load_view(active_view_dir)
    resolutions = [
        {"dim": "tilts.sectors.health_care", "state": "ALIGNED",
         "cio_tilt": 1, "parallax_view": 1, "market": None}
    ]
    recs = judge.phase_5_recommendations(
        resolutions=resolutions,
        severity="drift_minor",
        view=view,
        mcp_responses=fresh_aligned_responses,
        llm_call_fn=fake_llm,
    )
    assert recs == []
    assert called["count"] == 0


def test_phase_5_drops_hallucinated_recommendation_via_validator(
    active_view_dir: Path,
    fresh_aligned_responses: dict,
):
    """LLM-returned rationale that doesn't cite the snippet is dropped."""
    view = judge.phase_0_load_view(active_view_dir)
    resolutions = [{
        "dim": "tilts.regions.japan",
        "state": "DIVERGENT_FRESH",
        "cio_tilt": 1,
        "parallax_view": -1,
        "market": "Japan",
    }]

    def hallucinator(prompt):
        # The snippet is about Japan rates — the LLM returns Brazil prose.
        return {
            "recommended_value": -1,
            "confidence": 0.7,
            "rationale": "Underweight Brazil — central bank hiking aggressively.",
            "suggested_basis_statement_addendum": "Brazil risk",
        }

    recs = judge.phase_5_recommendations(
        resolutions=resolutions,
        severity="drift_material",
        view=view,
        mcp_responses=fresh_aligned_responses,
        llm_call_fn=hallucinator,
    )
    assert len(recs) == 1
    assert recs[0]["declined"] is True
    assert recs[0]["rationale"] == rec_mod.DECLINE_MARKER
    assert recs[0]["recommended_value"] is None


def test_phase_5_keeps_well_cited_recommendation(
    active_view_dir: Path,
    fresh_divergent_responses: dict,
):
    view = judge.phase_0_load_view(active_view_dir)
    resolutions = [{
        "dim": "tilts.regions.japan",
        "state": "DIVERGENT_FRESH",
        "cio_tilt": 1,
        "parallax_view": -1,
        "market": "Japan",
    }]

    def good_llm(prompt):
        # Quote the snippet verbatim in the rationale.
        snippet = prompt["snippet_for_validation"]
        # Pick a guaranteed >= 30 char substring from the start.
        quote = snippet[:80]
        return {
            "recommended_value": -1,
            "confidence": 0.75,
            "rationale": f"Recommend flipping to UW Japan: '{quote}'",
            "suggested_basis_statement_addendum": "Japan reversal",
        }

    recs = judge.phase_5_recommendations(
        resolutions=resolutions,
        severity="drift_material",
        view=view,
        mcp_responses=fresh_divergent_responses,
        llm_call_fn=good_llm,
    )
    assert len(recs) == 1
    assert recs[0]["declined"] is False
    assert recs[0]["recommended_value"] == -1


def test_phase_5_handles_llm_call_exception(
    active_view_dir: Path,
    fresh_divergent_responses: dict,
):
    view = judge.phase_0_load_view(active_view_dir)
    resolutions = [{
        "dim": "tilts.regions.japan",
        "state": "DIVERGENT_FRESH",
        "cio_tilt": 1,
        "parallax_view": -1,
        "market": "Japan",
    }]

    def broken_llm(prompt):
        raise RuntimeError("LLM provider down")

    recs = judge.phase_5_recommendations(
        resolutions=resolutions,
        severity="drift_material",
        view=view,
        mcp_responses=fresh_divergent_responses,
        llm_call_fn=broken_llm,
    )
    assert len(recs) == 1
    assert recs[0]["declined"] is True
    assert "RuntimeError" in recs[0]["decline_reason"]


# ---------------------------------------------------------------------------
# Auto-on-load gate (cadence).
# ---------------------------------------------------------------------------


def test_auto_on_load_suppressed_for_fresh_view(
    active_view_dir: Path,
    report_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Bump upload_timestamp to today so view_age_days < 30.
    view_path = active_view_dir / "view.yaml"
    data = yaml.safe_load(view_path.read_text())
    today_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    data["metadata"]["upload_timestamp"] = today_iso
    view_path.write_text(yaml.safe_dump(data, sort_keys=False))

    chain_dir = tmp_path / "chains"
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    # Auto-on-load: explicit=False, scheduled=False.
    config = judge.JudgeConfig(
        dry=True,
        mock_mcp_responses={},
        explicit=False,
        scheduled=False,
        view_dir=active_view_dir,
        report_dir=report_dir,
    )
    result = judge.run_judge(config=config)

    # Should have returned the no-op result without running the pipeline.
    assert result.audit_entry is None
    assert any("auto-on-load suppressed" in d for d in result.diagnostics)


# ---------------------------------------------------------------------------
# Maker-modules absence diagnostic.
# ---------------------------------------------------------------------------


def test_probe_maker_modules_returns_unavailable_when_b1_absent():
    """B1 isn't shipped → probe surfaces a clean diagnostic, not a crash."""
    maker = judge.probe_maker_modules()
    # Either the modules exist (B1 landed) or the probe degrades gracefully.
    if not maker.available:
        assert "unavailable" in maker.diagnostic.lower()
        assert maker.cross_country is None
        assert maker.pillar_compose is None
        assert maker.pillar_formulas is None
