"""Tests for shadow_diff rendering."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from shadow_diff import diff_views, render_shadow_diff


FIXTURES = Path(__file__).parent / "fixtures"


def _load_bank_view() -> dict:
    with open(FIXTURES / "bank_view_anchor.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _synth_view() -> dict:
    """A synthesis that ADDS health_care/financials/energy_neg, AGREES on us,
    and DISAGREES on information_technology."""
    return {
        "tilts": {
            "pillars": {
                "econometrics_phase": 1,
                "valuation_state": -1,
                "market_entropy": 0,
                "psychological_wavelength": 1,
            },
            "sectors": {
                "information_technology": -1,  # disagree (bank: +1, synth: -1)
                "health_care": 1,  # additive
                "financials": 1,  # additive
                "energy": -1,  # agree
            },
            "regions": {
                "us": 1,  # agree
                "japan": 0,  # bank had +1, synth silent → bank_only
                "china": -1,  # additive
            },
            "factors": {},
        }
    }


def test_diff_classifies_each_cell():
    bank = _load_bank_view()
    synth = _synth_view()
    diff = diff_views(bank, synth)

    # Additive surface: synthesis fills cells bank is silent on.
    assert "tilts.sectors.health_care" in diff["added"]
    assert "tilts.sectors.financials" in diff["added"]
    assert "tilts.regions.china" in diff["added"]
    # Agreements:
    assert "tilts.sectors.energy" in diff["agree"]
    assert diff["agree"]["tilts.sectors.energy"] == -1
    assert "tilts.regions.us" in diff["agree"]
    # Disagreement:
    assert "tilts.sectors.information_technology" in diff["disagree"]
    d = diff["disagree"]["tilts.sectors.information_technology"]
    assert d["bank"] == 1 and d["synthesized"] == -1
    # Bank-only:
    assert "tilts.regions.japan" in diff["bank_only"]


def test_render_carries_additive_framing_language():
    """The report MUST frame synthesis as ADDITIVE; bank's view is sovereign."""
    bank = _load_bank_view()
    synth = _synth_view()
    text = render_shadow_diff(bank, synth)
    lowered = text.lower()
    # Mandatory framing tokens — required for narrative consistency.
    assert "additive" in lowered
    assert "sovereign" in lowered
    assert "bank's view" in lowered or "bank view" in lowered
    # Section markers.
    assert "ADDITIVE" in text
    assert "AGREE" in text
    assert "DISAGREE" in text
    # No save / shadow framing.
    assert "no save" in lowered or "re-run without" in lowered


def test_render_without_bank_view_shows_full_synthesis_as_additive():
    """When no active bank view, EVERY synthesized cell is additive."""
    synth = _synth_view()
    text = render_shadow_diff(None, synth)
    assert "additive" in text.lower()


def test_disagreement_is_informational_not_corrective():
    """Disagreement lines must say informational — not 'override' or 'correct'."""
    bank = _load_bank_view()
    synth = _synth_view()
    text = render_shadow_diff(bank, synth)
    # Find a disagree line.
    disagree_lines = [
        ln for ln in text.splitlines()
        if "information_technology" in ln and "bank=" in ln
    ]
    assert disagree_lines, f"expected disagree line, got\n{text}"
    line = disagree_lines[0]
    assert "informational" in line.lower()


def test_pillars_block_renders_when_supplied():
    """When pillars dict is passed, the report should show per-pillar confidence."""
    from pillar_formulas import PillarResult

    pillars = {
        "omega": PillarResult(value=1, confidence=0.7, missing_inputs=[]),
        "phi": PillarResult(value=-1, confidence=0.4, missing_inputs=[]),
        "xi": PillarResult(value=0, confidence=0.3, missing_inputs=["entropy_prose_silent_in_all_markets"]),
        "psi": PillarResult(value=1, confidence=0.5, missing_inputs=[]),
    }
    text = render_shadow_diff(None, _synth_view(), pillars=pillars)
    assert "PILLAR CONFIDENCE" in text
    assert "OMEGA" in text or "omega" in text.lower()
    # Missing inputs surface.
    assert "entropy_prose_silent_in_all_markets" in text
