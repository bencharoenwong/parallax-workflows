# Parallax AI Investor Profile — Output Template (distribution subset)

This copy carries the sections that consumer skills render by reference from `parallax-conventions.md` (verdict language rules and the standard disclaimer). The full template ships with the AI investor-profile skills.

### 5. Verdict

Exactly one of:
- `Profile fit: match` — with count, e.g., "4 of 4 factor criteria met"
- `Profile fit: partial match` — with count, e.g., "2 of 4 factor criteria met"
- `Profile fit: no match` — with explanation

**FORBIDDEN verdict language:** "buy", "sell", "recommend", "would buy", "endorses", "rates", "likes", "hates", any first-person impersonation. See spec §5.

### 8. Standard disclaimer (REQUIRED, VERBATIM)

Every profile output MUST end with this exact disclaimer. Substitute `[Investor]` with the named investor (e.g., "Warren Buffett"). No other substitutions are permitted. The phrases "AI-inferred," "solely from publicly available information," "not financial advice," and "consult a qualified financial advisor" are load-bearing and MUST NOT be removed, softened, or replaced:

```
---
This output is an AI-inferred interpretation of [Investor]'s approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by [Investor] or their representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```
