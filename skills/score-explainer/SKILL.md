---
name: parallax-score-explainer
description: "Explain Parallax scores, factors, and methodology in plain language. Why does a stock score this way? What would change it? Uses methodology docs and score data. NOT for stock analysis (use /parallax-should-i-buy), not for deep dives (use /parallax-deep-dive)."
user-invocable: true
negative-triggers:
  - Stock analysis with buy/sell framing → use /parallax-should-i-buy
  - Full position analysis → use /parallax-deep-dive
  - Portfolio diagnostics → use /parallax-portfolio-checkup
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - explain_methodology takes a topic string — be specific (e.g., "quality score", "momentum factor")
  - get_docs and list_docs access the full methodology documentation
  - get_score_analysis shows trajectory — useful for explaining "why did this change"
  - Output must be accessible to non-technical clients and compliance teams
---

# Score Explainer

Plain-language explanations of Parallax scores, factors, and methodology.

## Usage

```
/parallax-score-explainer AAPL.O "why is the value score so low?"
/parallax-score-explainer "what does the quality factor measure?"
/parallax-score-explainer TSLA.O "why did the score drop last month?"
/parallax-score-explainer "how does Shariah screening work?"
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools based on query type:

**For "why does X score this way?":**
1. Call `get_score_analysis` for the symbol (52 weeks) to get current scores and trajectory.
2. Call `get_peer_snapshot` for peer context.
3. Call `explain_methodology` for each factor that's notably high or low.
4. Call `get_docs` or `list_docs` for deeper methodology documentation if needed.

**For "what does X factor mean?":**
1. Call `explain_methodology` for the specific factor/concept.
2. Call `list_docs` to find relevant methodology pages.
3. Call `get_docs` for the specific documentation page.

**For "why did the score change?":**
1. Call `get_score_analysis` with enough weeks to cover the change period.
2. Call `get_news_synthesis` to check for fundamental catalysts.
3. Call `explain_methodology` for the changed factor.
4. Call `get_stock_report` if a comprehensive explanation is needed (paid).

## Output Format

- **The Question** (restate clearly)
- **The Answer** (lead with the plain-language explanation — 2-3 sentences max)
- **Score Breakdown** (table if applicable: factor scores with interpretation)
- **What's Driving It** (specific data points, peer comparison, methodology context)
- **What Would Change It** (concrete conditions that would improve/worsen the score)
- **Methodology Reference** (brief citation of the scoring methodology for credibility)
