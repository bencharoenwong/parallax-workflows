from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS = {
    "parallax-ai-consensus": [
        "Parallax AI Investor Profiles — Consensus for <ticker>",
    ],
    "parallax-ai-greenblatt": [
        "Greenblatt-style basket (Magic Formula)",
        "Greenblatt-style profile applied to <ticker>",
    ],
    "parallax-ai-klarman": [
        "Klarman-style profile applied to <ticker>",
    ],
    "parallax-ai-soros": [
        "Soros-style regime themes and exposure candidates (informational)",
        "Soros-style profile applied to <ticker>",
    ],
}


@pytest.mark.parametrize(("skill", "headers"), SKILLS.items())
def test_emit_contract_includes_additions_and_mode_headers(skill, headers):
    text = (REPO_ROOT / "skills" / skill / "SKILL.md").read_text()
    emit = text.split("— Emit", 1)[1].split("## Output additions", 1)[0]

    assert "plus every required Output addition below" in emit
    assert "including a URL logo and the conditional Branding Header" in emit
    assert "About This Report footer, AI-interaction disclosure, and standard disclaimer" in emit
    assert "rendered template and nothing else" not in emit
    assert "complete response, first character to last" not in emit
    for header in headers:
        assert f"`{header}`" in emit
