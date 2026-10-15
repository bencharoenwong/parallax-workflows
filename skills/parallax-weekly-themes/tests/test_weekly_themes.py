"""Tests for /parallax-weekly-themes arithmetic. Run: pytest skills/parallax-weekly-themes/tests -v"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SKILL_DIR))

from weekly_themes import compute, main, market_row  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "telemetry_markets.json"


@pytest.fixture()
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestMarketRow:
    def test_vs_median_uses_middle_of_distribution(self, payload):
        row = market_row("AA", payload["markets"]["AA"], payload["report_date"])
        assert row.median_wtd == pytest.approx(0.004)
        assert row.leader_vs_median == pytest.approx(0.031 - 0.004)
        assert row.laggard_vs_median == pytest.approx(-0.022 - 0.004)
        assert row.breadth == pytest.approx(3 / 5)

    def test_single_theme_market_has_no_spread(self, payload):
        row = market_row("CC", payload["markets"]["CC"], payload["report_date"])
        assert row.n_themes == 1
        assert row.leader_vs_median is None
        assert row.laggard is None
        assert "single theme" in row.note

    def test_malformed_distribution_gives_none(self):
        row = market_row("ZZ", {"n_baskets": 4, "top_wtd": {"name": "x", "value": 0.01},
                                "distribution_wtd": [0.1, 0.2]}, "2026-01-02")
        assert row.median_wtd is None
        assert row.leader_vs_median is None


class TestCompute:
    def test_ranking_order_and_exclusions(self, payload):
        out = compute(payload)
        codes = [r.code for r in out.themes_of_week]
        # BB leads AA on vs-median; CC (1 theme) and DD (2 themes) are excluded.
        assert codes == ["BB", "AA"]

    def test_top_caps_ranking(self, payload):
        assert len(compute(payload, top=1).themes_of_week) == 1

    def test_unknown_market_listed_not_covered(self, payload):
        out = compute(payload, markets=["aa", "XX"])
        assert [r.code for r in out.markets] == ["AA"]
        assert out.not_covered == ["XX"]

    def test_stale_market_flagged(self, payload):
        out = compute(payload)
        assert out.stale == ["DD"]

    def test_missing_markets_raises(self):
        with pytest.raises(ValueError):
            compute({"report_date": "2026-01-02"})

    def test_bad_top_raises(self, payload):
        with pytest.raises(ValueError):
            compute(payload, top=0)


def test_cli_round_trip(capsys):
    assert main(["--input", str(FIXTURE), "--markets", "AA,BB"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [m["code"] for m in out["markets"]] == ["AA", "BB"]


def test_no_report_date_gives_no_stale_notes(payload):
    payload = dict(payload)
    payload.pop("report_date")
    out = compute(payload)
    assert out.stale == []
    assert all("data as of" not in r.note for r in out.markets)


def test_duplicate_codes_deduped(payload):
    out = compute(payload, markets=["AA", "aa", "BB"])
    assert [r.code for r in out.markets] == ["AA", "BB"]


def test_cli_bad_input_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["--input", str(bad)]) == 2
    assert main(["--input", str(tmp_path / "missing.json")]) == 2
