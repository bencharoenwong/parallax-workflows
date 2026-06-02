from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "baseline"))

from aggregate_report import summarize  # noqa: E402


def test_summarize_computes_passrate_and_variance():
    runs = [
        {"task": "aapl_en", "tier1": 1.0, "tier2": 0.75},
        {"task": "aapl_en", "tier1": 1.0, "tier2": 0.50},
        {"task": "msft_en", "tier1": 1.0, "tier2": 1.00},
        {"task": "msft_en", "tier1": 0.9, "tier2": 1.00},
    ]
    rep = summarize(runs)
    assert rep["overall"]["tier1_mean"] == 0.975
    assert rep["overall"]["tier2_mean"] == 0.8125
    assert rep["overall"]["tier2_var"] >= 0
    assert rep["per_task"]["aapl_en"]["tier2_mean"] == 0.625
    assert rep["below_ceiling"] is True


def test_ceiling_flagged_when_everything_passes():
    runs = [{"task": "x", "tier1": 1.0, "tier2": 1.0}]
    rep = summarize(runs)
    assert rep["below_ceiling"] is False
