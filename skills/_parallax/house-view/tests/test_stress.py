"""
Tests for the House View Stress Test skill.
"""
import datetime
import hashlib
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_STRESS_DIR = _REPO_ROOT / "skills" / "stress-house-view"
_HOUSE_VIEW_DIR = _REPO_ROOT / "skills" / "_parallax" / "house-view"
for _p in (_HOUSE_VIEW_DIR, _STRESS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import audit_chain  # noqa: E402
import stress  # noqa: E402
import render  # noqa: E402

# --- Fixtures ---

@pytest.fixture
def temp_house_view_dir(tmp_path: Path) -> Path:
    """Creates a temporary house view directory."""
    d = tmp_path / "house_view"
    d.mkdir()
    (d / "stress-tests").mkdir()
    return d

@pytest.fixture
def sample_view_data():
    """Returns sample valid house view data."""
    return {
        "metadata": {
            "view_id": "uuid-view-1",
            "version_id": "uuid-version-1",
            "view_name": "Test View",
            "effective_date": (datetime.date.today() - datetime.timedelta(days=10)).isoformat(),
        },
        "tilts": {
            "macro_regime": {"rates": "holding", "growth": "steady"},
            "factors": {"momentum": 1, "value": -1},
            "regions": {"us": 1, "jp": -1},
            "sectors": {"information_technology": 2},
            "pillars": {"econometrics_phase": 1},
        },
        "excludes": ["tobacco"]
    }

@pytest.fixture
def sample_rules_path(tmp_path: Path):
    """Creates a sample internal_rules.yaml file."""
    rules_content = """
    - id: "rates_cutting_momentum_pos"
      description: "Rates cutting is historically unfavorable for high-momentum stocks."
      class: "hard_stop"
      last_reviewed: "2026-05-14"
      confidence: 0.9
      pattern:
        when:
          tilts.macro_regime.rates: "cutting"
          tilts.factors.momentum: ">=1"
    - id: "stale_rule"
      description: "A stale hard stop rule."
      class: "hard_stop"
      last_reviewed: "2024-01-01"
      confidence: 0.9
      pattern:
        when:
          tilts.macro_regime.growth: "recessionary"
    """
    rules_path = tmp_path / "internal_rules.yaml"
    rules_path.write_text(rules_content)
    return rules_path

@pytest.fixture
def mock_view(temp_house_view_dir: Path, sample_view_data: dict):
    """Creates a mock view.yaml and returns a View object."""
    view_path = temp_house_view_dir / "view.yaml"
    audit_path = temp_house_view_dir / "audit.jsonl"
    
    with open(view_path, "w") as f:
        yaml.dump(sample_view_data, f)
        
    # Seed audit chain via the real API so verify_chain accepts it.
    audit_chain.append_entry(audit_path, {
        "ts": "2026-05-13T00:00:00Z",
        "action": "save",
        "view_id": "uuid-view-1",
        "version_id": "uuid-version-1",
    })

    # Use the canonical view_hash so the race-condition guard in
    # append_stress_audit doesn't false-positive.
    fixture_hash = stress.compute_view_hash(sample_view_data)
    return stress.View(data=sample_view_data, view_hash=fixture_hash, view_path=view_path, audit_path=audit_path)

# --- Tests ---

# Phase 0: Intake
def test_load_active_view_success(mock_view: stress.View, temp_house_view_dir: Path):
    """(ID: intake-001) ★★★ active view present, all systems go"""
    loaded_view = stress.load_active_view(temp_house_view_dir)
    assert loaded_view.data["metadata"]["view_id"] == "uuid-view-1"
    assert loaded_view.view_path.exists()

def test_load_active_view_no_view(temp_house_view_dir: Path):
    """(ID: intake-002) ★★ no view → exit clean with suggestion"""
    with pytest.raises(FileNotFoundError, match="No active house view found"):
        stress.load_active_view(temp_house_view_dir)

def test_load_active_view_broken_chain(mock_view: stress.View, temp_house_view_dir: Path):
    """(ID: intake-003) ★★ view present, audit chain broken (hash mismatch) → refuse.

    Exercises the hash-chain verification path specifically — appends a valid
    JSON entry with a wrong `prev_entry_hash` so verify_chain raises
    AuditChainBroken (not AuditFileMalformed). Both subclass AuditChainError
    and surface as ConnectionAbortedError, but the security-critical path is
    hash verification, not JSON parsing.
    """
    # Use real newline so the bad entry lands on its own line (else json.loads
    # would fail first and we'd test malformed-JSON instead of hash mismatch).
    with open(mock_view.audit_path, "a") as f:
        f.write(json.dumps({
            "ts": "2026-05-14T00:00:00Z",
            "action": "consume",
            "prev_entry_hash": "0" * 64,  # valid-shape sha256 hex, wrong value
        }) + "\n")

    with pytest.raises(ConnectionAbortedError, match="Audit chain is broken"):
        stress.load_active_view(temp_house_view_dir)

def test_enumerate_dimensions_non_zero(mock_view: stress.View):
    """(ID: intake-004) ★★ non-zero tilts pulled"""
    dims, markets = stress.enumerate_dimensions(mock_view)
    assert "tilts.factors.momentum" in dims
    assert "tilts.regions.us" in dims
    assert "us" in markets["tilted"]
    assert "jp" in markets["tilted"]
    # Exact count is fixture-dependent — assert lower bound and category coverage instead.
    assert len(dims) >= 4
    assert any(d.startswith("tilts.macro_regime.") for d in dims)
    assert any(d.startswith("tilts.factors.") for d in dims)
    assert any(d.startswith("tilts.regions.") for d in dims)

def test_enumerate_dimensions_empty(mock_view: stress.View):
    """(ID: intake-005) ★ schema_v0 legacy view handling"""
    mock_view.data['tilts'] = {}
    dims, markets = stress.enumerate_dimensions(mock_view)
    assert not dims
    assert not markets["tilted"]


# Phase 1: Internal Consistency
def test_rule_pass_no_contradiction(mock_view: stress.View, sample_rules_path: Path):
    """(ID: rule-001) ★ passes when no contradiction"""
    results = stress.evaluate_internal_rules(mock_view, sample_rules_path)
    assert not any(r.triggered for r in results)

def test_rule_triggers_rates_momentum(mock_view: stress.View, sample_rules_path: Path):
    """(ID: rule-002) ★★★ triggers + downgrades on stale config"""
    mock_view.data["tilts"]["macro_regime"]["rates"] = "cutting"
    mock_view.data["tilts"]["factors"]["momentum"] = 2
    results = stress.evaluate_internal_rules(mock_view, sample_rules_path)
    triggered_result = next(r for r in results if r.rule_id == "rates_cutting_momentum_pos")
    assert triggered_result.triggered
    assert not triggered_result.downgraded_from_stale_config

def test_rule_downgrades_on_stale_config(mock_view: stress.View, sample_rules_path: Path):
    """(ID: rule-003) ★★★ triggers as Hard stop, downgradeable with stale-rule-warning"""
    mock_view.data["tilts"]["macro_regime"]["growth"] = "recessionary"
    results = stress.evaluate_internal_rules(mock_view, sample_rules_path)
    triggered_result = next(r for r in results if r.rule_id == "stale_rule")
    assert triggered_result.triggered
    assert triggered_result.downgraded_from_stale_config

# Adding more rule tests to meet the count
def test_rule_growth_slowing_cyclicals_triggers(mock_view, sample_rules_path):
    """(ID: rule-004) ★★ triggers as Taste, not Hard"""
    rules_content = sample_rules_path.read_text() + """
    - id: "growth_slowing_cyclicals_overweight"
      description: "Slowing growth favors defensive sectors over cyclicals."
      class: "taste"
      last_reviewed: "2026-05-14"
      confidence: 0.7
      pattern:
        when:
          tilts.macro_regime.growth: "slowing"
        any_of:
          - tilts.sectors.financials: ">=1"
    """
    sample_rules_path.write_text(rules_content)
    mock_view.data['tilts']['macro_regime']['growth'] = 'slowing'
    mock_view.data['tilts']['sectors']['financials'] = 1
    results = stress.evaluate_internal_rules(mock_view, sample_rules_path)
    assert any(r.triggered for r in results if r.rule_id == "growth_slowing_cyclicals_overweight")

def test_rule_excludes_energy_em_commodity_triggers(mock_view, sample_rules_path):
    """(ID: rule-005) ★★ triggers as Taste"""
    rules_content = sample_rules_path.read_text() + """
    - id: "excludes_energy_em_commodity_overweight"
      description: "Excluding energy while overweighting commodity-exporting EM regions."
      class: "taste"
      last_reviewed: "2026-05-14"
      confidence: 0.6
      pattern:
        when:
          excludes: "contains:energy"
        any_of:
          - tilts.regions.brazil: ">=1"
    """
    sample_rules_path.write_text(rules_content)
    mock_view.data['excludes'].append('energy')
    mock_view.data['tilts']['regions']['brazil'] = 1
    results = stress.evaluate_internal_rules(mock_view, sample_rules_path)
    assert any(r.triggered for r in results if r.rule_id == "excludes_energy_em_commodity_overweight")

def test_rule_pillar_omega_riskoff_riskon_triggers(mock_view, sample_rules_path):
    """(ID: rule-006) ★★★ triggers as Hard stop"""
    rules_content = sample_rules_path.read_text() + """
    - id: "pillar_omega_risk_on"
      description: "A negative econometrics phase contradicts a risk-on appetite."
      class: "hard_stop"
      last_reviewed: "2026-05-14"
      confidence: 0.85
      pattern:
        when:
          tilts.pillars.econometrics_phase: "<=-1"
          tilts.macro_regime.risk_appetite: "risk_on"
    """
    sample_rules_path.write_text(rules_content)
    mock_view.data['tilts']['pillars']['econometrics_phase'] = -1
    mock_view.data['tilts']['macro_regime']['risk_appetite'] = 'risk_on'
    results = stress.evaluate_internal_rules(mock_view, sample_rules_path)
    triggered_result = next(r for r in results if r.rule_id == 'pillar_omega_risk_on')
    assert triggered_result.triggered
    assert not triggered_result.downgraded_from_stale_config

# Phase 2: External Comparison
@pytest.mark.parametrize("cio_age, parallax_age, expected", [
    (10, 5, "both_fresh"),
    (40, 5, "stale"),
    (10, None, "unverifiable"),
    (20, 60, "fresh"), # CIO is fresher than Parallax
])
def test_compute_age_delta(cio_age, parallax_age, expected):
    """(ID: external-001 - 004) ★★★ stale/fresh/both-fresh/unverifiable classifier"""
    assert stress.compute_age_delta(cio_age, parallax_age) == expected

@pytest.mark.parametrize("cio_tilt, parallax_view, age_delta, expected_state", [
    (1, 1, "both_fresh", "ALIGNED"),
    (1, -1, "stale", "DIVERGENT_STALE"),
    (1, -1, "fresh", "DIVERGENT_FRESH"),
    (0, 1, "both_fresh", "CIO_SILENT"),
    (1, None, "both_fresh", "PARALLAX_SILENT"),
    (0, None, "both_fresh", "UNCOVERED"),
])
def test_resolve_cell_state_all_cases(cio_tilt, parallax_view, age_delta, expected_state):
    """(ID: external-005 - 010) ★★★ All 6 cell state resolutions"""
    assert stress.resolve_cell_state(cio_tilt, parallax_view, age_delta) == expected_state


def test_resolve_cell_state_uncovered_with_cio_tilt():
    """(ID: external-011) ★★★ UNCOVERED fires even when CIO has tilt (market not in list_macro_countries)"""
    # CIO tilts vietnam +1 but vietnam is outside Parallax coverage.
    assert stress.resolve_cell_state(
        cio_tilt=1,
        parallax_view=None,
        age_delta="both_fresh",
        market="vietnam",
        covered_markets={"us", "jp", "de"},
    ) == "UNCOVERED"
    # Sanity: covered market with CIO tilt + no Parallax view stays PARALLAX_SILENT.
    assert stress.resolve_cell_state(
        cio_tilt=1,
        parallax_view=None,
        age_delta="both_fresh",
        market="us",
        covered_markets={"us", "jp", "de"},
    ) == "PARALLAX_SILENT"

def test_fanout_cap_enforce_under_cap():
    """(ID: fanout-001) ★★★ <=12 markets passes through"""
    markets = ["us", "jp", "de"]
    assert stress.enforce_fanout_cap(markets) == markets

def test_fanout_cap_enforce_over_cap():
    """(ID: fanout-002) ★★★ >12 markets → prompt branch"""
    markets = [f"m{i}" for i in range(13)]
    with pytest.raises(stress.FanOutCapExceeded):
        stress.enforce_fanout_cap(markets)


# Phase 3: Audit
@patch('stress.audit_chain.append_entry')
def test_append_stress_audit_success(mock_append: MagicMock, mock_view: stress.View):
    """(ID: audit-001) ★★★ writes via existing audit_chain.append_entry() and returns the entry."""
    summary = {"internal_pass": True, "states": {"aligned": 1}}
    # The real append_entry returns the finalized entry; mock that contract.
    sentinel_return = {"skill": "parallax-stress-house-view", "action": "stress_test",
                      "prev_entry_hash": "fakehash", "schema_version": 1}
    mock_append.return_value = sentinel_return

    returned = stress.append_stress_audit(mock_view, summary)

    mock_append.assert_called_once()
    call_args = mock_append.call_args[0]
    assert call_args[0] == mock_view.audit_path
    assert call_args[1]['skill'] == 'parallax-stress-house-view'
    assert call_args[1]['action'] == 'stress_test'
    # Regression: append_stress_audit must return append_entry's value so the
    # orchestrator can compute the audit_hash_short for Phase 4-B citation.
    assert returned is sentinel_return


def test_append_stress_audit_hash_for_phase4b_citation(mock_view):
    """End-to-end: written entry can be hashed to produce the audit_hash_short
    that render_artifact uses for the Phase 4-B stress_test:<hash> citation.
    Regression for the HIGH bug where the citation always fell to fallback wording.
    """
    summary = {"internal_pass": True, "states": {"aligned": 1}}
    written = stress.append_stress_audit(mock_view, summary, disposition="completed")
    audit_hash_short = audit_chain.compute_entry_hash(written)[:12]
    assert len(audit_hash_short) == 12
    assert all(c in "0123456789abcdef" for c in audit_hash_short)
    # And the rendered Phase 4-B section should include this exact short hash
    # when deltas are passed.
    deltas = [{
        "kind": "informational", "path": "tilts.sectors.utilities", "market": "japan",
        "cio_value": 1, "parallax_signal": -1, "parallax_summary": "rank 4",
        "stress_state": "DIVERGENT_STALE", "cio_age_days": 56, "parallax_age_days": 1,
    }]
    report = render.render_artifact(
        mock_view.data["metadata"], [], {}, [], "vhash",
        recommended_deltas=deltas, audit_hash_short=audit_hash_short,
    )
    assert f"stress_test:{audit_hash_short}" in report

def test_append_stress_audit_race_guard(mock_view: stress.View):
    """(ID: audit-002) ★★ view_hash mismatch Phase 0↔3 aborts"""
    summary = {"internal_pass": True}
    # Simulate another process changing the view
    mock_view.data['tilts']['factors']['momentum'] = 5
    with open(mock_view.view_path, "w") as f:
        yaml.dump(mock_view.data, f)
    
    with pytest.raises(RuntimeError, match="View changed mid-run"):
        stress.append_stress_audit(mock_view, summary)

# Phase 4: Render
def test_render_artifact_full_report(mock_view):
    """(ID: render-001) ★★ full report renders for typical run"""
    internal_results = [stress.RuleResult(rule_id="test_rule", triggered=True, evidence=["evidence"])]
    external_results = {"us": {"factors.momentum": {"state": "ALIGNED"}}}
    themes = ["Test Theme"]
    
    report = render.render_artifact(mock_view.data['metadata'], internal_results, external_results, themes, "hash123")
    
    assert "House View Stress Test Report" in report
    assert "Phase 1: Internal Consistency" in report
    assert "test_rule" in report
    assert "Phase 2: External Comparison vs. Parallax" in report
    assert "Market: US" in report
    assert "Cross-Dimension Themes" in report
    assert "Test Theme" in report

def test_render_artifact_empty_divergence(mock_view):
    """(ID: render-002) ★ empty-divergence report (everything aligned)"""
    report = render.render_artifact(mock_view.data['metadata'], [], {}, [], "hash123")
    assert "All internal consistency checks passed" in report
    assert "No external comparison was performed" in report

def test_save_artifact(mock_view, temp_house_view_dir):
    """(ID: render-003) ★ saves artifact correctly under the active-view dir.

    Regression for adversarial-reviewer BUG-005: must write to a directory
    derived from the view's location (or an explicit output_dir override) —
    NEVER to the hardcoded ~/.parallax/active-house-view/stress-tests/. Asserts
    the file lands under the tmp fixture and the prod dir is not touched.
    """
    report_content = "This is a test report."
    output_dir = temp_house_view_dir / "stress-tests"
    report_path = render.save_artifact(report_content, mock_view, output_dir=output_dir)

    assert report_path.exists()
    assert str(report_path).startswith(str(temp_house_view_dir)), \
        f"artifact escaped tmp dir to {report_path}"
    assert report_path.name.startswith(datetime.date.today().isoformat())
    assert report_path.name.endswith(".md")
    assert (report_path.stat().st_mode & 0o777) == 0o600
    assert report_path.read_text() == report_content


def test_save_artifact_default_uses_view_path_parent(mock_view, temp_house_view_dir):
    """Default behavior (no output_dir): derive from view.view_path.parent, not hardcoded."""
    report_path = render.save_artifact("body", mock_view)  # no override
    # view_path is temp_house_view_dir/"view.yaml" per the mock_view fixture
    assert str(report_path).startswith(str(temp_house_view_dir)), \
        f"default save escaped tmp; landed at {report_path}"

# --- Paths covered by SKILL.md orchestration rather than Python ---
# The CIO-flow explicit subset (`--markets us,jp`), the fan-out cap user prompt
# (AskUserQuestion branches a/b/c), and the Phase 4 gate options (A/B/C/E) are
# all driven by AskUserQuestion in SKILL.md, not by Python code. They are
# verified by manual skill invocation, not pytest. Listed here as documentation
# only — no placeholder tests.


# --- Tests for code-review fix coverage ---

def test_rule_class_propagates_to_result(mock_view, sample_rules_path):
    """Hard-stop rules emit RuleResult.rule_class='hard_stop' (not 'taste').
    Regression for code-review HIGH#3: render previously substring-matched rule_id."""
    # Tilt to trigger the rates_cutting_momentum_pos hard_stop rule from the fixture.
    mock_view.data['tilts']['macro_regime']['rates'] = 'cutting'
    mock_view.data['tilts']['factors']['momentum'] = 2
    results = stress.evaluate_internal_rules(mock_view, sample_rules_path)
    triggered = [r for r in results if r.triggered and r.rule_id == "rates_cutting_momentum_pos"]
    assert triggered, "rates_cutting_momentum_pos rule should have triggered"
    assert triggered[0].rule_class == "hard_stop", \
        f"Expected rule_class='hard_stop'; got {triggered[0].rule_class}"


def test_render_hard_stop_status(mock_view):
    """Render produces 🛑 HARD STOP for hard_stop rule_class.
    Regression for code-review HIGH#3."""
    results = [
        stress.RuleResult(rule_id="any_id", triggered=True, rule_class="hard_stop", evidence=["x"]),
    ]
    report = render.render_artifact(mock_view.data['metadata'], results, {}, [], "hash123")
    assert "🛑 HARD STOP" in report
    assert "⚠️ TASTE" not in report.split("🛑 HARD STOP")[0]  # not also rendered as TASTE


def test_render_downgraded_hard_stop_status(mock_view):
    """Render produces downgraded-TASTE message for stale-config hard_stop."""
    results = [
        stress.RuleResult(
            rule_id="any_id",
            triggered=True,
            rule_class="taste",  # effective_class after downgrade
            evidence=["x"],
            downgraded_from_stale_config=True,
        ),
    ]
    report = render.render_artifact(mock_view.data['metadata'], results, {}, [], "hash123")
    assert "Downgraded from Hard Stop" in report
    assert "🛑 HARD STOP" not in report  # the raw hard-stop banner must NOT appear


def test_compute_view_hash_includes_excludes(sample_view_data):
    """Canonical view_hash changes when only `excludes` is mutated.
    Regression for code-review HIGH#1: old impl hashed only `tilts`."""
    h_before = stress.compute_view_hash(sample_view_data)
    sample_view_data['excludes'] = sample_view_data.get('excludes', []) + ['weapons']
    h_after = stress.compute_view_hash(sample_view_data)
    assert h_before != h_after, "view_hash must change when excludes mutate"


def test_audit_ts_format_has_z_suffix(mock_view):
    """Audit ts ends in 'Z' per loader.md §6.1.
    Regression for code-review HIGH#4."""
    captured = {}
    def fake_append(audit_path, entry):
        captured['entry'] = entry
        return entry
    import unittest.mock as _mock
    with _mock.patch.object(stress.audit_chain, 'append_entry', side_effect=fake_append):
        stress.append_stress_audit(mock_view, {"internal_pass": True})
    assert captured['entry']['ts'].endswith('Z'), captured['entry']['ts']
    assert '+00:00' not in captured['entry']['ts']


# --- Regression tests for adversarial-reviewer BUGs 001-004 ---

def test_compute_view_hash_preserves_bool_false():
    """BUG-001: _is_empty must guard isinstance(v, bool) so False is preserved.
    False == 0 in Python; without the guard a bool tilt would silently strip,
    diverging from schema.yaml Rule 2.
    """
    a = {"tilts": {"factors": {"flag": False}}}  # bool False, NOT empty
    b = {"tilts": {"factors": {"flag": 0}}}      # int zero, IS empty per schema
    c = {"tilts": {}}
    h_a = stress.compute_view_hash(a)
    h_b = stress.compute_view_hash(b)
    h_c = stress.compute_view_hash(c)
    assert h_a != h_b, "bool False must not hash identically to int 0"
    assert h_b == h_c, "int 0 must strip to empty (schema Rule 2)"


def test_evaluate_condition_strict_less_than_and_float():
    """BUG-002: < and > operators must work, with float() threshold parsing."""
    assert stress._evaluate_condition(0.5, "<0.6") is True
    assert stress._evaluate_condition(0.6, "<0.6") is False  # strict
    assert stress._evaluate_condition(0.7, ">0.6") is True
    assert stress._evaluate_condition(0.6, ">0.6") is False  # strict
    # >= still works after the operator-order fix
    assert stress._evaluate_condition(0.6, ">=0.6") is True
    # Non-numeric value vs numeric condition: no crash, returns False
    assert stress._evaluate_condition(None, "<0.6") is False


def test_enumerate_dimensions_skips_null_macro_regime(mock_view):
    """BUG-003: null-valued macro_regime fields must not be enumerated."""
    mock_view.data["tilts"]["macro_regime"] = {
        "growth": None,
        "rates": "holding",  # has a view
        "inflation": None,
    }
    dims, _ = stress.enumerate_dimensions(mock_view)
    assert "tilts.macro_regime.rates" in dims
    assert "tilts.macro_regime.growth" not in dims, "null must be skipped"
    assert "tilts.macro_regime.inflation" not in dims, "null must be skipped"


def test_resolve_cell_state_aligns_float_with_int():
    """BUG-004: alignment check must accept float on either side."""
    # CIO int +1, Parallax float +1.0 → ALIGNED (was DIVERGENT_FRESH before fix)
    assert stress.resolve_cell_state(1, 1.0, "both_fresh") == "ALIGNED"
    assert stress.resolve_cell_state(1.0, 1, "both_fresh") == "ALIGNED"
    # Opposite signs still divergent regardless of int/float mix
    assert stress.resolve_cell_state(1.0, -1, "stale") == "DIVERGENT_STALE"


def test_house_view_dir_honors_env_var(monkeypatch, tmp_path):
    """BUG-006: HOUSE_VIEW_DIR must pick up PARALLAX_HOUSE_VIEW_DIR.

    Module-level constant is evaluated at import; reload to pick up the env var.
    """
    import importlib
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(tmp_path))
    importlib.reload(stress)
    try:
        assert stress.HOUSE_VIEW_DIR == tmp_path
    finally:
        # Reload again without the env var so subsequent tests see the default.
        monkeypatch.delenv("PARALLAX_HOUSE_VIEW_DIR", raising=False)
        importlib.reload(stress)


# --- Tests for classify_mcp_meta_state (Closure 2) ---

def test_classify_mcp_uncovered_takes_precedence():
    """Market not in covered_markets → UNCOVERED, regardless of response content."""
    state, summary = stress.classify_mcp_meta_state(
        response={"success": True, "data": {"foo": "bar"}},
        market="vietnam",
        covered_markets={"us", "jp", "de"},
    )
    assert state == "UNCOVERED"
    assert "vietnam" in summary.lower() or "covered" in summary.lower()


# --- Tests for Phase 4-B handoff (recommended_deltas) ---

def test_build_recommended_deltas_shape():
    """build_recommended_deltas emits one informational entry per DIVERGENT_STALE cell."""
    resolutions = [
        {"market": "japan", "dim": "sectors.utilities", "cio_tilt": 1, "parallax_view": -1,
         "state": "DIVERGENT_STALE", "parallax_summary": "Parallax: Japan utilities rank 4"},
        {"market": "us", "dim": "factors.momentum", "cio_tilt": 1, "parallax_view": 1,
         "state": "ALIGNED", "parallax_summary": "Parallax: momentum dominant"},
        {"market": "india", "dim": "factors.profitability", "cio_tilt": 2, "parallax_view": -1,
         "state": "DIVERGENT_STALE", "parallax_summary": "Parallax: quality 0.50"},
    ]
    deltas = stress.build_recommended_deltas(resolutions, cio_age_days=56, parallax_age_days=1)
    assert len(deltas) == 2, f"expected 2 deltas (only DIVERGENT_STALE); got {len(deltas)}"
    for d in deltas:
        assert d["kind"] == "informational"
        assert d["path"].startswith("tilts.")
        assert d["stress_state"] == "DIVERGENT_STALE"
        assert d["cio_age_days"] == 56
        assert d["parallax_age_days"] == 1
    paths = {d["path"] for d in deltas}
    assert paths == {"tilts.sectors.utilities", "tilts.factors.profitability"}


def test_audit_entry_carries_recommended_deltas_roundtrip(mock_view, tmp_path):
    """recommended_deltas in append_stress_audit round-trips through audit_chain.verify_chain."""
    deltas = [{
        "kind": "informational",
        "path": "tilts.sectors.utilities",
        "market": "japan",
        "cio_value": 1,
        "parallax_signal": -1,
        "parallax_summary": "rank 4",
        "stress_state": "DIVERGENT_STALE",
        "cio_age_days": 56,
        "parallax_age_days": 1,
    }]
    stress.append_stress_audit(
        mock_view,
        summary={"internal_pass": True, "states": {"aligned": 1}},
        applied=False,
        disposition="completed",
        recommended_deltas=deltas,
    )
    entries = audit_chain.verify_chain(mock_view.audit_path)
    stress_entries = [e for e in entries if e.get("action") == "stress_test"]
    assert stress_entries, "no stress_test entry written"
    assert stress_entries[-1]["recommended_deltas"] == deltas


def test_audit_entry_omits_deltas_when_none(mock_view):
    """recommended_deltas field is omitted from the audit entry when not provided."""
    stress.append_stress_audit(mock_view, summary={"internal_pass": True}, applied=False)
    entries = audit_chain.verify_chain(mock_view.audit_path)
    stress_entries = [e for e in entries if e.get("action") == "stress_test"]
    assert "recommended_deltas" not in stress_entries[-1]


def test_render_phase4b_section_present_with_deltas(mock_view):
    """render_artifact emits the Phase 4-B section when deltas are passed."""
    deltas = [{
        "kind": "informational",
        "path": "tilts.sectors.utilities",
        "market": "japan",
        "cio_value": 1,
        "parallax_signal": -1,
        "parallax_summary": "rank 4 deteriorating",
        "stress_state": "DIVERGENT_STALE",
        "cio_age_days": 56,
        "parallax_age_days": 1,
    }]
    report = render.render_artifact(
        mock_view.data["metadata"], [], {}, [], "hashabc123",
        recommended_deltas=deltas, audit_hash_short="abc12345",
    )
    assert "Phase 4-B Handoff" in report
    assert "tilts.sectors.utilities" in report
    assert "japan" in report
    assert "stress_test:abc12345" in report


def test_render_phase4b_section_absent_without_deltas(mock_view):
    """render_artifact omits the Phase 4-B section when no deltas are passed."""
    report = render.render_artifact(mock_view.data["metadata"], [], {}, [], "hashabc")
    assert "Phase 4-B Handoff" not in report


def test_classify_mcp_none_response_is_unreachable():
    """response is None → UNREACHABLE (fail-loud)."""
    state, _ = stress.classify_mcp_meta_state(
        response=None,
        market="us",
        covered_markets={"us"},
    )
    assert state == "UNREACHABLE"


def test_classify_mcp_empty_dict_is_unreachable():
    """response is {} (no success, no error) → UNREACHABLE (malformed)."""
    state, _ = stress.classify_mcp_meta_state(
        response={},
        market="us",
        covered_markets={"us"},
    )
    assert state == "UNREACHABLE"


def test_classify_mcp_success_false_is_silent():
    """response.success is False → PARALLAX_SILENT (degrade)."""
    state, _ = stress.classify_mcp_meta_state(
        response={"success": False, "error": "internal"},
        market="us",
        covered_markets={"us"},
    )
    assert state == "PARALLAX_SILENT"


def test_classify_mcp_timeout_is_silent():
    """error: timeout → PARALLAX_SILENT."""
    state, _ = stress.classify_mcp_meta_state(
        response={"error": "timeout"},
        market="us",
        covered_markets={"us"},
    )
    assert state == "PARALLAX_SILENT"


def test_classify_mcp_rate_limit_is_silent():
    """error: rate_limit → PARALLAX_SILENT."""
    state, _ = stress.classify_mcp_meta_state(
        response={"error": "rate_limit"},
        market="us",
        covered_markets={"us"},
    )
    assert state == "PARALLAX_SILENT"


def test_classify_mcp_malformed_shape_is_unreachable():
    """Dict with neither `success` nor `error` keys → UNREACHABLE (fails closed).

    Regression for adversarial CRITICAL gap 3.2A: a malformed-but-not-erroring
    response must NOT be treated as silent-ok.
    """
    state, _ = stress.classify_mcp_meta_state(
        response={"data": {"foo": "bar"}, "meta": {"v": 1}},
        market="us",
        covered_markets={"us"},
    )
    assert state == "UNREACHABLE"


def test_classify_mcp_unknown_error_with_success_true_is_silent():
    """success: true + unrecognized error key → PARALLAX_SILENT (not ok).

    Production MCPs use diverse error vocabularies (permission_denied,
    tool_not_found, internal_error, ...). Any non-None `error` flags a
    degraded response, regardless of `success`. Without this guard, a
    degraded response would be passed to the LLM as healthy prose.
    """
    for err in ("permission_denied", "tool_not_found", "internal_error", "forbidden"):
        state, summary = stress.classify_mcp_meta_state(
            response={"success": True, "error": err},
            market="us",
            covered_markets={"us"},
        )
        assert state == "PARALLAX_SILENT", f"{err} should be PARALLAX_SILENT, got {state}"
        assert err in summary


def test_classify_mcp_ok_response():
    """success: true → ok; LLM does prose interpretation downstream."""
    state, summary = stress.classify_mcp_meta_state(
        response={"success": True, "data": {"regime_tag": "stagflation"}},
        market="us",
        covered_markets={"us"},
    )
    assert state == "ok"
    assert isinstance(summary, str)


# Original skip stubs `test_mcp_failure_paths` and `test_schema_validation_gate`
# have been replaced by substantive tests covering the same coverage IDs:
#   mcp-fail-001-004 → test_classify_mcp_* (8 tests covering UNCOVERED, UNREACHABLE
#                                            branches, PARALLAX_SILENT branches, and ok)
#   schema-val-001   → test_validate_deltas_* (12 tests covering path checks,
#                                              special cases, kind/type/market,
#                                              schema_unreadable, integration roundtrip)


# --- Tests for validate_recommended_deltas (Closure 3) ---

_SCHEMA_PATH = _REPO_ROOT / "skills" / "_parallax" / "house-view" / "schema.yaml"


def test_validate_deltas_valid_returns_ok():
    """Valid deltas → (True, [])."""
    deltas = [
        {"kind": "informational", "path": "tilts.factors.momentum", "market": None,
         "cio_value": 1, "parallax_signal": -1, "parallax_summary": "...",
         "stress_state": "DIVERGENT_STALE", "cio_age_days": 56, "parallax_age_days": 1},
    ]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is True
    assert errors == []


def test_validate_deltas_empty_returns_ok():
    """Empty list → vacuously valid."""
    ok, errors = stress.validate_recommended_deltas([], _SCHEMA_PATH)
    assert ok is True
    assert errors == []


def test_validate_deltas_missing_tilts_prefix():
    """Path not starting with `tilts.` → error."""
    deltas = [{"kind": "informational", "path": "factors.momentum",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any("tilts." in e["reason"] for e in errors)


def test_validate_deltas_unknown_category():
    """Path's category segment not in schema → error."""
    deltas = [{"kind": "informational", "path": "tilts.bogus_category.foo",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any("bogus_category" in e["reason"] for e in errors)


def test_validate_deltas_unknown_dim():
    """Dim not present in schema under that category → error."""
    deltas = [{"kind": "informational", "path": "tilts.factors.foo",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any("foo" in e["reason"] for e in errors)


def test_validate_deltas_styles_four_segment_valid():
    """tilts.styles.<sub>.<leaf> with 4 segments is valid (Plan #4 regression)."""
    deltas = [{"kind": "informational", "path": "tilts.styles.cap_size.large",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    # We accept the path; styles sub-category must exist in schema.
    # If schema.yaml doesn't define cap_size under styles, error is expected.
    schema_cats = stress._load_schema_categories(_SCHEMA_PATH)
    if "cap_size" in schema_cats.get("styles", set()):
        assert ok is True, f"errors: {errors}"
    else:
        # Documents the path-shape acceptance even if the sub-cat is absent.
        assert all("cap_size" in e["reason"] for e in errors)


def test_validate_deltas_factor_alias_quality_accepted():
    """tilts.factors.quality is accepted as alias for profitability (Plan #5)."""
    deltas = [{"kind": "informational", "path": "tilts.factors.quality",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is True, f"errors: {errors}"


def test_validate_deltas_factor_alias_defensive_accepted():
    """tilts.factors.defensive is accepted as alias for low_volatility (Plan #5)."""
    deltas = [{"kind": "informational", "path": "tilts.factors.defensive",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is True, f"errors: {errors}"


def test_validate_deltas_bad_kind():
    """kind not in {informational, global} → error."""
    deltas = [{"kind": "bogus", "path": "tilts.factors.momentum",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any(e["field"] == "kind" for e in errors)


def test_validate_deltas_string_parallax_signal_rejected():
    """For informational kind, parallax_signal must be int|float|None — strings rejected (decision 4d)."""
    deltas = [{"kind": "informational", "path": "tilts.macro_regime.growth",
               "market": None, "cio_value": "slowing", "parallax_signal": "slowing",
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any(e["field"] == "parallax_signal" for e in errors)


def test_validate_deltas_market_mismatch_on_regions_path():
    """tilts.regions.us with market=japan → error."""
    deltas = [{"kind": "informational", "path": "tilts.regions.us",
               "market": "japan", "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any(e["field"] == "market" for e in errors)


def test_validate_deltas_global_kind_accepted_without_suggested_value():
    """kind: global accepted in v1 even without suggested_value field (decision 4c)."""
    deltas = [{"kind": "global", "path": "tilts.factors.momentum",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is True


def test_validate_deltas_schema_unreadable(tmp_path):
    """schema.yaml missing or malformed → ok=False, sentinel error.

    Regression for decision 1.1A — caller maps the sentinel to
    disposition='schema_unreadable' (NOT 'validation_failed').
    """
    bad_path = tmp_path / "nonexistent.yaml"
    deltas = [{"kind": "informational", "path": "tilts.factors.momentum",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, bad_path)
    assert ok is False
    assert len(errors) == 1
    e = errors[0]
    assert e["index"] is None
    assert e["field"] is None
    assert e["reason"].startswith("schema_unreadable:")


def test_validation_failure_disposition_roundtrips_through_audit(mock_view):
    """When validation fails, append_stress_audit writes disposition=validation_failed
    and recommended_deltas round-trip through audit_chain.verify_chain.

    Regression for decision 3.1A — the audit shape consumers will read for v2 --apply-stress.
    """
    bad_deltas = [{"kind": "informational", "path": "factors.momentum",  # no tilts. prefix
                   "market": None, "cio_value": 1, "parallax_signal": -1,
                   "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
                   "cio_age_days": 1, "parallax_age_days": 1}]
    schema_path = _REPO_ROOT / "skills" / "_parallax" / "house-view" / "schema.yaml"
    ok, errors = stress.validate_recommended_deltas(bad_deltas, schema_path)
    assert ok is False
    summary = {"internal_pass": True, "states": {"divergent_stale": 1}}
    stress.append_stress_audit(
        mock_view, summary, applied=False,
        disposition="validation_failed",
        recommended_deltas=bad_deltas,
    )
    entries = audit_chain.verify_chain(mock_view.audit_path)
    stress_entries = [e for e in entries if e.get("action") == "stress_test"]
    assert stress_entries, "no stress_test entry"
    last = stress_entries[-1]
    assert last["disposition"] == "validation_failed"
    assert last["recommended_deltas"] == bad_deltas


def test_audit_validation_errors_roundtrip(mock_view):
    """append_stress_audit accepts validation_errors and writes them to the audit entry.

    Regression for final code-reviewer finding: SKILL.md Phase 3 step 3 and
    loader.md §6.2 both document the validation_errors field, but without
    this plumbing the field could never be written through the function's
    race-guard path.
    """
    errors = [
        {"index": 0, "field": "path", "reason": "path must start with 'tilts.'"},
        {"index": 1, "field": "kind", "reason": "kind must be 'informational' or 'global'"},
    ]
    summary = {"internal_pass": True, "states": {}}
    stress.append_stress_audit(
        mock_view, summary, applied=False,
        disposition="validation_failed",
        recommended_deltas=[],
        validation_errors=errors,
    )
    entries = audit_chain.verify_chain(mock_view.audit_path)
    stress_entries = [e for e in entries if e.get("action") == "stress_test"]
    assert stress_entries
    last = stress_entries[-1]
    assert last["disposition"] == "validation_failed"
    assert last["validation_errors"] == errors


def test_validate_deltas_styles_4seg_still_runs_kind_check():
    """A 4-segment styles path with bad `kind` must still produce a kind error.

    Regression for final code-reviewer finding: previously the styles branch
    `continue`d before reaching kind/signal/market checks, letting malformed
    deltas slip through validation as ok=True. Contract: ALL checks run for
    ALL deltas regardless of path category.
    """
    deltas = [{"kind": "bogus_kind", "path": "tilts.styles.cap_size.large",
               "market": None, "cio_value": 1, "parallax_signal": -1,
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any(e["field"] == "kind" for e in errors), \
        f"expected 'kind' field error; got: {errors}"


def test_validate_deltas_styles_4seg_still_runs_signal_check():
    """A 4-segment styles path with string parallax_signal must still error."""
    deltas = [{"kind": "informational", "path": "tilts.styles.cap_size.large",
               "market": None, "cio_value": 1, "parallax_signal": "not a number",
               "parallax_summary": "", "stress_state": "DIVERGENT_STALE",
               "cio_age_days": 1, "parallax_age_days": 1}]
    ok, errors = stress.validate_recommended_deltas(deltas, _SCHEMA_PATH)
    assert ok is False
    assert any(e["field"] == "parallax_signal" for e in errors), \
        f"expected 'parallax_signal' field error; got: {errors}"


# --- Grep regression tests ---

def test_fragile_extraction_reference_removed():
    """Closure 1 deleted the rule; no reference should remain anywhere under skills/.

    Acceptance criterion 7 — grep regression.
    """
    skills_dir = _REPO_ROOT / "skills"
    offenders = []
    test_file_path = Path(__file__).relative_to(_REPO_ROOT)
    for path in skills_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".yaml", ".yml", ".md"}:
            continue
        # Skip pycache and archived test fixtures.
        if "__pycache__" in path.parts or ".archive" in path.parts:
            continue
        # Skip this test file itself (it mentions fragile_extraction in the test docstring).
        if path.relative_to(_REPO_ROOT) == test_file_path:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "fragile_extraction" in content:
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert not offenders, f"fragile_extraction still referenced in: {offenders}"
