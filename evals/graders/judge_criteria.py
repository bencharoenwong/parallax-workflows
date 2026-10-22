"""Baseline Tier-2 rubric criteria used by the /parallax-* eval substrate.

Each criterion is a binary the deterministic Tier-1 checks cannot see. Criteria
are shared across skills via the SPEC.tier2_criteria list in each eval_config.py.
Every criterion must clear the well-definedness bar (anchored / decidable /
low-variance) per design §4.1.
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


# Two-lens raised-bar criteria (Stage 2; design-doc §4.4). Kept OUT of the
# baseline CRITERIA list so the §5 Tier-2 noise floor stays current-spec. Run
# alongside CRITERIA only when grading the upgraded skill (red/green check).
TWO_LENS_CRITERIA: list[dict] = [
    {
        "id": "lenses_separate_reads",
        "statement": "Each lens states its own directional read; any disagreement is surfaced, not averaged into one verdict.",
        "pass_when": "Both a Technicals and a Fundamentals directional read are present; if they diverge, the Bottom Line names the divergence rather than blending it into a single rating.",
    },
    {
        "id": "technicals_grounded",
        "statement": "The Technicals read cites price/trend/momentum; the Fundamentals read cites financials/scores; neither borrows the other's evidence.",
        "pass_when": "The Technicals section references trend/momentum/support-resistance (or the labeled Momentum-proxy fallback); the Fundamentals section references factor scores/financials; evidence is not cross-contaminated.",
    },
]
