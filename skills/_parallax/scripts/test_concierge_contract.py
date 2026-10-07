from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "parallax-concierge" / "SKILL.md").read_text(encoding="utf-8")


def test_concierge_offers_new_here_in_the_opening():
    opening = SRC[SRC.index("**Hi — where are we looking today?**"):SRC.index("## 🔍 Stock branch")]
    assert "New here? I'll show you what fits your role." in opening


def test_concierge_new_here_states_in_order():
    sec = SRC[SRC.index("## New here?"):]
    order = ["Check", "Role", "Integrator", "Input", "Run", "After the result"]
    positions = [sec.index(f"**{s}**") for s in order]
    assert positions == sorted(positions)
    assert "<!-- new-here:begin -->" in sec and "<!-- new-here:end -->" in sec


def test_concierge_role_question_handles_four_option_cap():
    assert "caps options" in SRC and "then narrow" in SRC


def test_concierge_input_step_resolves_and_reports_misses():
    sec = SRC[SRC.index("**Input**"):SRC.index("**Run**")]
    assert "search_stocks" in sec and "not covered by Parallax" in sec


def test_concierge_rule_asks_instead_of_assuming():
    assert "regardless of who the user is" not in SRC
    assert "Never guess the user; ask when it matters" in SRC
