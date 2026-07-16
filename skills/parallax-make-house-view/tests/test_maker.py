"""End-to-end orchestration tests for maker.py.

Verifies:
- audit row format conforms to loader.md §6.1/§6.2 (forbidden keys absent).
- provenance.yaml has generator_synthesis entries with valid fields.
- hash chain integrity (audit_chain.verify_chain passes).
- gate is required (no save path bypasses it).
- shadow_diff short-circuits save.
- hard abort fires when unreachable_share > 30%.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import audit_chain
import gate_present
import provenance_classes

from maker import (
    DEFAULT_COMPONENTS,
    HARDCODED_COVERAGE,
    MARKET_TO_SCHEMA_KEY,
    SKILL_NAME,
    MakerOptions,
    MakerOrchestrator,
    MakerResult,
    MCPResponses,
    MCPRunner,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as f:
        return json.load(f)


class _FixtureRunner(MCPRunner):
    """Mock MCPRunner that returns fixtures or synthetic responses for any market."""

    def __init__(
        self,
        markets: list[str] | None = None,
        unreachable: set[str] | None = None,
        list_macro_countries_response: dict | None = None,
    ):
        self.markets = markets if markets is not None else list(HARDCODED_COVERAGE)
        self.unreachable = unreachable or set()
        self._list_response = list_macro_countries_response

    def list_macro_countries(self):
        if self._list_response is not None:
            return self._list_response
        return {
            "success": True,
            "countries": self.markets + ["Global"],
        }

    def get_telemetry(self, fields):
        return _load("telemetry_full.json")

    def macro_analyst_batch(self, requests, *, concurrency=8, per_call_timeout_s=45):
        out: dict[tuple[str, str], dict | None] = {}
        for market, comp in requests:
            if market in self.unreachable:
                out[(market, comp)] = None
                continue
            out[(market, comp)] = self._response_for(market, comp)
        return out

    def _response_for(self, market: str, component: str) -> dict | None:
        # Prefer real fixtures where available.
        if market == "United States" and component == "macro_indicators":
            return _load("us_macro_indicators.json")
        if market == "Japan" and component == "tactical":
            return _load("japan_tactical.json")
        if market == "China" and component == "macro_indicators":
            return _load("china_macro_indicators.json")

        # Synthetic minimal-success response so other markets contribute to
        # fan-out summary and per-region tilts.
        return {
            "report_date": "2026-05-19",
            "market": market,
            "component": component,
            "success": True,
            "content": (
                f"{market} {component}: constructive backdrop with selective "
                "overweight bias; favourable positioning. " if component != "sectors"
                else "Sector ranking data remains unavailable for this reporting period."
            ),
        }


@pytest.fixture
def tmp_view_dir(tmp_path: Path) -> Path:
    d = tmp_path / "active-house-view"
    return d


@pytest.fixture
def runner() -> _FixtureRunner:
    return _FixtureRunner()


def _confirm_dispose(prompt: gate_present.GatePrompt) -> str:
    return "confirm"


# ---------------------------------------------------------------------------
# Step 1: list_macro_countries resolution
# ---------------------------------------------------------------------------


def test_resolve_covered_markets_excludes_global():
    orc = MakerOrchestrator(MakerOptions())
    runner = _FixtureRunner(markets=["United States", "Japan", "Global"])
    markets, _ = orc.resolve_covered_markets(runner)
    assert "Global" not in markets
    assert "United States" in markets
    assert "Japan" in markets


def test_resolve_covered_markets_applies_filter():
    orc = MakerOrchestrator(MakerOptions(market_filter=["us"]))
    runner = _FixtureRunner()
    markets, _ = orc.resolve_covered_markets(runner)
    assert markets == ["United States"]


def test_resolve_falls_back_to_hardcoded_on_list_failure():
    orc = MakerOrchestrator(MakerOptions())
    runner = _FixtureRunner(list_macro_countries_response={"success": False, "countries": []})
    markets, _ = orc.resolve_covered_markets(runner)
    assert set(markets) == set(HARDCODED_COVERAGE)


# ---------------------------------------------------------------------------
# DEFAULT_COMPONENTS fan-out set (cost regression guard)
# ---------------------------------------------------------------------------


def test_default_components_excludes_fixed_income():
    """Cost regression guard.

    `fixed_income` was dropped from the default fan-out because no
    downstream formula consumes it (macro_analyst was fanned out per
    market for `fixed_income` — 14x/run — with the response never read by
    cross_country, pillar_compose, or pillar_formulas). Re-add it ONLY in
    the same change that lands a consuming formula (the deferred "rates
    leg" of econometrics_phase) — a silent re-add here would reinflate the
    make-house-view / judge-house-view MCP fan-out from 14x4 back to 14x5.
    """
    assert DEFAULT_COMPONENTS == ("macro_indicators", "tactical", "sectors", "news")
    assert len(DEFAULT_COMPONENTS) == 4
    assert "fixed_income" not in DEFAULT_COMPONENTS


def test_fan_out_requests_no_fixed_income_component(tmp_view_dir: Path):
    """Functional companion to the structural guard above.

    Verifies the actual fan-out request set built from `DEFAULT_COMPONENTS`
    (not just the constant in isolation) excludes `fixed_income` for every
    covered market.
    """
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us", "japan"])
    )
    runner = _FixtureRunner()
    markets, _ = orc.resolve_covered_markets(runner)
    per_market, _telemetry = orc.fan_out(runner, markets)
    assert per_market, "fan_out should return per-market responses"
    for m in per_market:
        assert set(m.components.keys()) == set(DEFAULT_COMPONENTS)
        assert "fixed_income" not in m.components


# ---------------------------------------------------------------------------
# End-to-end save: audit + provenance + chain
# ---------------------------------------------------------------------------


def test_end_to_end_save_produces_valid_audit_row(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us", "japan", "china"])
    )
    runner = _FixtureRunner()
    result = orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)
    assert result.disposition == "confirm"
    assert result.saved_paths is not None
    assert tmp_view_dir.is_dir()
    audit_path = tmp_view_dir / "audit.jsonl"
    assert audit_path.exists()

    # Read the audit entry and verify shape.
    lines = audit_path.read_text().strip().splitlines()
    assert lines, "audit.jsonl should have at least one entry"
    entry = json.loads(lines[-1])
    assert entry["action"] == "generate"
    assert entry["applied"] is True
    assert entry["skill"] == SKILL_NAME
    assert entry["calibration_status"] == "heuristic_phase0"
    assert isinstance(entry["source_tools"], list)
    assert entry["source_tools"]
    # provenance_hash is present + 64 hex chars.
    assert len(entry["provenance_hash"]) == 64

    # Loader.md §6.2 forbids these keys on the generate row.
    for forbidden in (
        "composition_formula",
        "aggregator_weights_ref",
        "source_snippets",
        "pillar_missing_inputs",
    ):
        assert forbidden not in entry, f"forbidden key {forbidden!r} on audit row"


def test_provenance_yaml_has_generator_synthesis_entries(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us", "japan", "china"])
    )
    runner = _FixtureRunner()
    orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)

    prov_path = tmp_view_dir / "provenance.yaml"
    assert prov_path.exists()
    with open(prov_path, "r") as f:
        prov = yaml.safe_load(f)
    assert isinstance(prov, dict) and prov, "provenance.yaml should have entries"

    # Every entry should validate against generator_synthesis spec.
    for path, entry in prov.items():
        errs = provenance_classes.validate_provenance_entry(entry)
        assert not errs, f"{path}: {errs}"
        assert entry["class"] == "generator_synthesis"
        # Required composition_formula + aggregator_weights_ref live here,
        # NOT on the audit row.
        assert "composition_formula" in entry
        assert "aggregator_weights_ref" in entry


def test_audit_chain_verifies(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us", "japan", "china"])
    )
    runner = _FixtureRunner()
    orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)

    audit_path = tmp_view_dir / "audit.jsonl"
    entries = audit_chain.verify_chain(audit_path)
    assert entries
    # First entry must carry chain_root flag.
    assert entries[0].get("chain_root") is True


# ---------------------------------------------------------------------------
# View YAML written matches save path semantics
# ---------------------------------------------------------------------------


def test_view_yaml_round_trips(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us", "japan"])
    )
    runner = _FixtureRunner()
    result = orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)
    view_path = tmp_view_dir / "view.yaml"
    with open(view_path, "r") as f:
        view = yaml.safe_load(f)
    assert view["metadata"]["view_id"] == result.view_id
    assert view["metadata"]["version_id"] == result.version_id
    assert view["metadata"]["calibration_status"] == "heuristic_phase0"
    assert view["extraction"]["uploader_confirmed"] is True
    # Synthesized views default to 30-day auto-expire.
    assert view["metadata"]["auto_expire_days"] == 30
    # Pillar values present in tilts.pillars.
    pillars = view["tilts"]["pillars"]
    assert set(pillars.keys()) == {
        "econometrics_phase",
        "valuation_state",
        "market_entropy",
        "psychological_wavelength",
    }


def test_prose_md_paired_yaml_hash_matches_view_hash(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us"])
    )
    runner = _FixtureRunner()
    orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)

    prose_path = tmp_view_dir / "prose.md"
    text = prose_path.read_text()
    # frontmatter contains paired_yaml_hash + prose_body_hash.
    assert "paired_yaml_hash:" in text
    assert "prose_body_hash:" in text


# ---------------------------------------------------------------------------
# Gate is REQUIRED (no save path bypass)
# ---------------------------------------------------------------------------


def test_no_dispose_fn_raises_when_not_shadow_diff(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us"])
    )
    runner = _FixtureRunner()
    with pytest.raises(ValueError, match="dispose_fn"):
        orc.execute_synthesis(runner)


def test_abandon_disposition_does_not_save(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us"])
    )
    runner = _FixtureRunner()
    result = orc.execute_synthesis(runner, dispose_fn=lambda p: "abandon")
    assert result.disposition == "abandoned"
    assert result.saved_paths is None
    assert not (tmp_view_dir / "view.yaml").exists()


# ---------------------------------------------------------------------------
# Shadow-diff mode short-circuits save
# ---------------------------------------------------------------------------


def test_shadow_diff_returns_report_without_save(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(
            view_dir=tmp_view_dir,
            market_filter=["us", "japan"],
            shadow_diff=True,
        )
    )
    runner = _FixtureRunner()
    # No dispose_fn required in shadow_diff mode.
    result = orc.execute_synthesis(runner)
    assert result.disposition == "shadow_diff"
    assert result.shadow_diff_report is not None
    assert "ADDITIVE" in result.shadow_diff_report
    # No save: view.yaml should NOT exist.
    assert not (tmp_view_dir / "view.yaml").exists()


# ---------------------------------------------------------------------------
# Hard abort on unreachable_share > 30%
# ---------------------------------------------------------------------------


def test_hard_abort_when_unreachable_share_above_threshold(tmp_view_dir: Path):
    """Make most markets unreachable → execute_synthesis raises."""
    markets = ["United States", "Japan", "China"]
    # 2/3 unreachable = 66% > 30%
    runner = _FixtureRunner(
        markets=markets, unreachable={"Japan", "China"}
    )
    orc = MakerOrchestrator(
        MakerOptions(
            view_dir=tmp_view_dir,
            market_filter=[MARKET_TO_SCHEMA_KEY[m] for m in markets],
        )
    )
    with pytest.raises(RuntimeError, match="unreachable_share"):
        orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)


# ---------------------------------------------------------------------------
# Pillars surfaced in result
# ---------------------------------------------------------------------------


def test_pillars_surface_on_result(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us", "japan", "china"])
    )
    runner = _FixtureRunner()
    result = orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)
    assert result.pillars is not None
    assert set(result.pillars.keys()) == {"omega", "phi", "xi", "psi"}
    assert result.aggregated is not None
    assert result.mcp_responses is not None


# ---------------------------------------------------------------------------
# response_hash determinism
# ---------------------------------------------------------------------------


def test_mcp_responses_response_hash_is_deterministic():
    runner = _FixtureRunner()
    orc = MakerOrchestrator(MakerOptions(market_filter=["us"]))
    markets, raw = orc.resolve_covered_markets(runner)
    per_market, telemetry = orc.fan_out(runner, markets)
    r1 = MCPResponses(list_macro_countries=raw, per_market=per_market, telemetry=telemetry)
    _, hash1 = r1.as_chain_payload()

    # Rebuild — should produce identical hash.
    per_market2, telemetry2 = orc.fan_out(runner, markets)
    r2 = MCPResponses(list_macro_countries=raw, per_market=per_market2, telemetry=telemetry2)
    _, hash2 = r2.as_chain_payload()

    assert hash1 == hash2
    assert len(hash1) == 64


def test_source_tools_list_includes_per_market_per_component(tmp_view_dir: Path):
    orc = MakerOrchestrator(
        MakerOptions(view_dir=tmp_view_dir, market_filter=["us", "japan"])
    )
    runner = _FixtureRunner()
    orc.execute_synthesis(runner, dispose_fn=_confirm_dispose)
    audit_path = tmp_view_dir / "audit.jsonl"
    entry = json.loads(audit_path.read_text().strip().splitlines()[-1])
    tools = entry["source_tools"]
    assert any(t.startswith("macro_analyst:United States:") for t in tools)
    assert any(t.startswith("macro_analyst:Japan:") for t in tools)
    assert any(t.startswith("get_telemetry") for t in tools)
    assert any(t.startswith("list_macro_countries") for t in tools)
