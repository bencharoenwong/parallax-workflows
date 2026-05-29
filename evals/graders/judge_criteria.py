"""Editable Tier-2 rubric criteria for /parallax-should-i-buy.

Each criterion is a binary the deterministic Tier-1 checks cannot see. Add a
target by appending a dict — no code change. Every criterion must clear the
well-definedness bar (anchored / decidable / low-variance) per design §4.1.
All criteria below are current-spec conformance (NOT aspirational — the
two-lens example in §4.4 is deliberately excluded from this baseline list).
"""
from __future__ import annotations

CRITERIA: list[dict] = [
    {
        "id": "bottom_line_balanced",
        "statement": "The Bottom Line names at least one positive AND at least one negative about the stock.",
        "pass_when": "Both a pro and a con are present and it reads as balanced, not as a buy/sell call.",
    },
    {
        "id": "scores_interpretation_consistent",
        "statement": "The Scores section's plain-English interpretation is consistent with the score table values.",
        "pass_when": "The narrative direction (high/low, up/down) matches the numbers shown in the table.",
    },
    {
        "id": "macro_specific",
        "statement": "If a Macro Context section is present, it is specific to the relevant market, not generic boilerplate.",
        "pass_when": "It references the actual market/economy in question; or it is correctly absent.",
    },
    {
        "id": "no_hallucinated_data",
        "statement": "The output introduces no quantitative claim unsupported by the tool calls that were made.",
        "pass_when": "Numbers/figures in the prose are plausibly grounded in the called tools; no invented precise stats.",
    },
]
