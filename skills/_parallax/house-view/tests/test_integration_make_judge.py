"""Cross-skill integration tests: maker ↔ judge.

Verifies the make-house-view + judge-house-view skills work together
end-to-end. Maker synthesizes a view; judge re-imputes from the same
MCP surface and classifies drift.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
MAKER_DIR = REPO / "skills" / "make-house-view"
JUDGE_DIR = REPO / "skills" / "judge-house-view"
SHARED_DIR = REPO / "skills" / "_parallax" / "house-view"
MAKER_FIXTURES = MAKER_DIR / "tests" / "fixtures"
JUDGE_FIXTURES = JUDGE_DIR / "tests" / "fixtures"

# sys.path injection — same pattern as stress.py uses for shared infra
for _path in (SHARED_DIR, MAKER_DIR, JUDGE_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import maker
import judge
import gate_present
from cross_country import MarketResponse


def build_mock_mcp_aligned() -> dict[str, Any]:
    us_macro = json.loads((MAKER_FIXTURES / "us_macro_indicators.json").read_text())
    japan_tactical = json.loads((MAKER_FIXTURES / "japan_tactical.json").read_text())
    china_macro = json.loads((MAKER_FIXTURES / "china_macro_indicators.json").read_text())
    telemetry = json.loads((MAKER_FIXTURES / "telemetry_full.json").read_text())

    return {
        "list_macro_countries": {
            "success": True,
            "markets": ["United States", "Japan", "China"],
        },
        "telemetry": telemetry,
        ("United States", "macro_indicators"): us_macro,
        ("Japan", "tactical"): japan_tactical,
        ("China", "macro_indicators"): china_macro,
    }


class MockMCPRunner(maker.MCPRunner):
    def __init__(self, mcp_dict: dict[str, Any]):
        self.mcp_dict = mcp_dict

    def list_macro_countries(self) -> dict[str, Any] | None:
        return self.mcp_dict.get("list_macro_countries")

    def get_telemetry(self, fields: list[str]) -> dict[str, Any] | None:
        return self.mcp_dict.get("telemetry")

    def macro_analyst_batch(
        self, requests: list[tuple[str, str]], concurrency: int = 8, per_call_timeout_s: int = 45
    ) -> dict[tuple[str, str], dict[str, Any] | None]:
        results = {}
        for m, c in requests:
            results[(m, c)] = self.mcp_dict.get((m, c))
        return results


def get_judge_mcp_dict(maker_result: maker.MakerResult) -> dict[str, Any]:
    """Convert Maker's MCPResponses to the dict shape the judge's dry mode expects."""
    m_res = maker_result.mcp_responses
    if m_res is None:
        return {}
    
    d: dict[str, Any] = {
        "per_market": m_res.per_market,
        "telemetry": m_res.telemetry,
        "list_macro_countries": m_res.list_macro_countries,
    }
    
    # Add flat keys for judge's staleness/hash logic
    for m in m_res.per_market:
        for comp, resp in (m.components or {}).items():
            if resp is not None:
                d[f"macro_analyst:{m.market_name}:{comp}"] = resp
    
    if m_res.telemetry is not None:
        d["get_telemetry"] = m_res.telemetry
        
    if m_res.list_macro_countries is not None:
        d["list_macro_countries"] = m_res.list_macro_countries

    return d


def mutate_mcp_to_divergent(base_mcp: dict[str, Any], flips: dict[tuple[str, str], str]) -> dict[str, Any]:
    mutated = copy.deepcopy(base_mcp)
    for (m, c), text in flips.items():
        if (m, c) in mutated and mutated[(m, c)] is not None:
            mutated[(m, c)]["content"] = text
    return mutated


def run_maker_with_mocked_mcp(mcp_responses: dict[str, Any], view_dir: Path) -> maker.MakerResult:
    runner = MockMCPRunner(mcp_responses)
    opts = maker.MakerOptions(view_dir=view_dir)
    orch = maker.MakerOrchestrator(opts)

    def _mock_gate_loop(*args, **kwargs):
        return gate_present.GateResult(disposition="confirm", final_draft=args[0])

    with patch("gate_present.run_gate_loop", side_effect=_mock_gate_loop):
        res = orch.execute_synthesis(
            mcp=runner,
            dispose_fn=lambda _: "confirm",
            edit_fn=lambda _, __: ({}, None),
        )
    return res


def run_judge_with_mocked_mcp(mcp_responses: dict[str, Any], view_dir: Path, report_dir: Path) -> judge.JudgeResult:
    # NOTE: prior version of this helper monkey-patched
    # ``judge._imputed_view_from_maker`` to work around two bugs in the
    # judge orchestrator: (a) ``weights={}`` hardcoded in the caller, and
    # (b) ``aggregated.get("tilts", {})`` looking for a non-existent
    # subtree. Both bugs were fixed in judge.py; the patch is removed and
    # this test now exercises the real imputed-view path end-to-end.
    config = judge.JudgeConfig(
        dry=True,
        mock_mcp_responses=mcp_responses,
        explicit=True,
        view_dir=view_dir,
        report_dir=report_dir,
    )

    def dummy_llm(*args, **kwargs):
        return {"recommendations": [{"action": "Update view", "rationale": "Tests", "declined": False}]}

    return judge.run_judge(config=config, llm_call_fn=dummy_llm)


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

def test_maker_save_then_judge_aligned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    view_dir = tmp_path / "active-house-view"
    report_dir = tmp_path / "judge-reports"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    base_mcp = build_mock_mcp_aligned()

    maker_res = run_maker_with_mocked_mcp(base_mcp, view_dir)
    assert maker_res.disposition == "confirm"

    assert (view_dir / "view.yaml").exists()
    assert (view_dir / "prose.md").exists()
    assert (view_dir / "provenance.yaml").exists()
    assert (view_dir / "audit.jsonl").exists()

    judge_mcp = get_judge_mcp_dict(maker_res)
    judge_res = run_judge_with_mocked_mcp(judge_mcp, view_dir, report_dir)

    assert judge_res.severity == "drift_minor"
    assert judge_res.drift_summary.get("aligned_count", 0) > 0
    assert judge_res.drift_summary.get("drift_material_count", 0) == 0


def test_maker_save_then_divergent_mcp_yields_drift_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    view_dir = tmp_path / "active-house-view"
    report_dir = tmp_path / "judge-reports"
    chain_dir = tmp_path / "chains"
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    monkeypatch.setattr("chain_emit.DEFAULT_CHAIN_DIR", chain_dir)

    base_mcp = build_mock_mcp_aligned()

    run_maker_with_mocked_mcp(base_mcp, view_dir)

    flips = {
        ("United States", "macro_indicators"): "US growth is rapidly deteriorating. Cautious on tech and consumer sectors. Underweight equities.",
        ("Japan", "tactical"): "Japan tactical view turns outright bearish. Sell industrials.",
    }
    mutated_mcp = mutate_mcp_to_divergent(base_mcp, flips)

    runner = MockMCPRunner(mutated_mcp)
    opts = maker.MakerOptions(view_dir=view_dir)
    orch = maker.MakerOrchestrator(opts)
    covered, raw_lmc = orch.resolve_covered_markets(runner)
    pm, tel = orch.fan_out(runner, covered)
    mcp_res = maker.MCPResponses(list_macro_countries=raw_lmc, per_market=pm, telemetry=tel)

    maker_res_mock = maker.MakerResult(disposition="mock", draft_view=None, mcp_responses=mcp_res)
    judge_mcp = get_judge_mcp_dict(maker_res_mock)

    judge_res = run_judge_with_mocked_mcp(judge_mcp, view_dir, report_dir)

    assert judge_res.severity in ("drift_moderate", "drift_material")
    assert len(judge_res.recommendations) > 0
    assert judge_res.audit_entry is not None
    assert judge_res.audit_entry["action"] == "judge"
    assert judge_res.audit_entry["applied"] is False


def test_judge_imputed_view_uses_maker_modules():
    modules = judge.probe_maker_modules()
    assert modules.available is True
    assert modules.cross_country is not None
    assert modules.pillar_compose is not None
    assert modules.pillar_formulas is not None
    assert hasattr(modules.cross_country, "aggregate")
    assert hasattr(modules.pillar_compose, "compute_pillars")
    assert hasattr(modules.pillar_formulas, "compute_omega")
