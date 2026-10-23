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

    def test_stale_market_not_ranked(self, payload):
        payload = json.loads(json.dumps(payload))
        payload["markets"]["EE"] = {
            "as_of": "2026-01-01", "market_name": "EE", "n_baskets": 5,
            "top_wtd": {"name": "old leader", "value": 0.5},
            "bottom_wtd": {"name": "old laggard", "value": -0.1},
            "distribution_wtd": [-0.1, 0.0, 0.01, 0.02, 0.5],
            "n_positive_wtd": 4,
        }
        out = compute(payload)
        assert "EE" in out.stale
        assert "EE" in [r.code for r in out.markets]
        assert [r.code for r in out.themes_of_week] == ["BB", "AA"]

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


@pytest.mark.parametrize("field,value", [("top_wtd", "broken"), ("bottom_wtd", [1]), ("n_baskets", -1), ("n_positive_wtd", 8), ("as_of", "2026-02-30")])
def test_invalid_market_payload_has_controlled_cli_failure(payload, tmp_path, capsys, field, value):
    payload["markets"]["AA"][field] = value
    path = tmp_path / "telemetry.json"
    path.write_text(json.dumps(payload))
    assert main(["--input", str(path)]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_returns_never_rank(payload, value):
    payload["markets"]["AA"]["top_wtd"]["value"] = value
    with pytest.raises(ValueError, match="finite"):
        compute(payload)


def test_unknown_freshness_is_visible_and_not_ranked(payload):
    payload["markets"]["BB"].pop("as_of")
    result = compute(payload)
    assert result.unknown_freshness == ["BB"]
    assert [r.code for r in result.themes_of_week] == ["AA"]
    assert "freshness unknown" in next(r.note for r in result.markets if r.code == "BB")
    payload.pop("report_date")
    assert not compute(payload).themes_of_week


def test_metadata_run_date_does_not_replace_returned_report_data_date(payload):
    # Telemetry can run the next day while its market data/report_date remain Friday.
    payload["metadata"] = {"run_date": "2026-01-03", "data_as_of": "2026-01-02"}
    result = compute(payload)
    assert result.report_date == "2026-01-02"
    assert [r.code for r in result.themes_of_week] == ["BB", "AA"]
    assert result.stale == ["DD"]
