---
name: parallax-AI-greenblatt
description: "Applies Joel Greenblatt's Magic Formula (per 'The Little Book That Beats the Market', 2006; academic replication Gray & Carlisle 2012) to Parallax data. Two modes: universe mode returns a top-decile ranked basket; ticker-check mode reports whether a single stock falls in the top decile of its peer universe by combined ROC + earnings yield rank. Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts no args (universe mode) or a single ticker."
negative-triggers:
  - Bottom-up factor scoring without the mechanical formula → use /parallax-AI-buffett
  - Balance-sheet-first special situations → use /parallax-AI-klarman
  - Top-down macro analysis → use /parallax-AI-soros
  - Cross-profile consensus → use /parallax-AI-consensus
  - Full due diligence → use /parallax-due-diligence
  - Running backtests → use /backtest
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks
  - JIT-load _parallax/AI-profiles/profile-schema.md for the dispatcher workflow and cross-validation gate
  - JIT-load _parallax/AI-profiles/output-template.md for the required output structure and verbatim disclaimer
  - JIT-load _parallax/AI-profiles/profiles/greenblatt.md for the profile spec
  - Universe mode is default when no ticker is provided; ticker-check mode activates with a single ticker
  - build_stock_universe is ~5 tokens; budget accordingly
  - Exclude financials and utilities from default universe per Greenblatt's original rule
  - NEVER use first-person impersonation — always "Greenblatt-style" or "Magic Formula"
  - Disclaimer verbatim; substitute "Joel Greenblatt" for [Investor] in the disclaimer block
  - Profile is derived from public book + academic replication only — no get_assessment, no score_total
---

# Parallax AI Greenblatt Profile

Applies Joel Greenblatt's Magic Formula (ROC rank + earnings yield rank, combined, top decile) to Parallax data.

## Usage

```
/parallax-AI-greenblatt                    # universe mode — default US equity universe
/parallax-AI-greenblatt AAPL               # ticker-check mode — is AAPL in the top decile?
/parallax-AI-greenblatt AAPL.O             # RIC format also accepted
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools.

### Step 0 — JIT-load dependencies

Before the first Parallax tool call:

1. Load `skills/_parallax/parallax-conventions.md` — RIC resolution, parallel execution, fallback patterns.
2. Load `skills/_parallax/AI-profiles/profile-schema.md` — dispatcher workflow and cross-validation gate.
3. Load `skills/_parallax/AI-profiles/output-template.md` — required output structure and disclaimer.
4. Load `skills/_parallax/AI-profiles/profiles/greenblatt.md` — profile spec.

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas.

### Step 1 — Determine mode

- No ticker → **universe mode**
- Exactly one ticker → **ticker-check mode**
- Multiple tickers → reject: "Greenblatt profile takes zero or one ticker. For multi-ticker checks use /parallax-AI-consensus."

### Step 2 — Universe mode workflow

**IMPORTANT — query scoping:** `build_stock_universe` is async and broad queries consistently time out in practice (e.g., "US large-cap equities with high ROIC" — confirmed timeout). The default query MUST be sector-scoped or otherwise narrow. Valid defaults:

- `"US large-cap consumer staples"` ← DEFAULT if no theme provided
- `"US large-cap industrials"`
- `"US large-cap healthcare"`
- User-provided theme passed via `--universe "<theme>"`

Do NOT pass broad queries like "US large-cap and mid-cap equities excluding financials and utilities" — they time out. If a user requests a broad screen, execute sector-by-sector and merge the rankings.

1. Call `build_stock_universe` with the sector-scoped query. Cost: 5 tokens. If the call times out, retry ONCE with a narrower query (e.g., drop "large-cap and mid-cap" → "large-cap"). If the retry also times out, return `INSUFFICIENT_UNIVERSE` and decline to render a verdict.
2. **Cap the universe at top 30 names** by `composite_score` from the `build_stock_universe` response (which already ranks candidates internally). This bounds the token cost for Step 3.
3. For each candidate in the top-30 cap, call `get_financials(statement=ratios)` in parallel batches to pull ROC and earnings yield. Substitute Parallax's `return_on_invested_capital` if direct ROC is not available. Derive earnings yield as `1 / enterprise_value_ebit`. Cost: 1 token per name, so ~30 tokens max.
4. Rank each candidate on ROC and earnings yield independently. Sum the two ranks. Sort by combined rank ascending.
5. Take the top 10% as the Magic Formula basket (top 3 names out of 30).
6. For the top 3 basket members, call `get_peer_snapshot` (1 token each) to surface Parallax factor scores as pedagogy.

### Step 3 — Ticker-check mode workflow

1. Resolve ticker per shared conventions.
2. Call `get_company_info` to identify the ticker's sector/industry.
3. Call `build_stock_universe` with a sector-based peer universe query derived from the ticker's sector (e.g., if AAPL is in "Technology Hardware," query `"US large-cap technology hardware"`). Sector-scoped queries succeed where broad queries time out.
4. Cap the peer universe at top 30 names by `composite_score`.
5. Run Step 2 sub-steps 3-4 on the capped peer universe.
6. Check where the target ticker ranks in the combined distribution.

### Step 4 — Cross-validation gate

For ticker-check mode, after `get_peer_snapshot` on the target ticker, cross-check `target_company` (the top-level field — NOT `name` on individual peer rows) against `get_company_info`'s `name`. Refuse to render on mismatch per `profile-schema.md §2 Step 2`.

For universe mode, cross-validation is per-name on the top-3 basket members that get `get_peer_snapshot` calls.

### Step 5 — Compute verdict (ticker-check mode only)

- **Top 10% of combined rank → `match`**
- **Top 25% but below top 10% → `partial_match`**
- **Below top 25% → `no_match`**

### Step 6 — Render through output template

**Universe mode output:**

```
Greenblatt-style basket (Magic Formula)
Source: Greenblatt, J. (2006). The Little Book That Beats the Market.
Secondary: Gray, W., Carlisle, T. (2012). Quantitative Value.

Universe: <query>
Universe size: <N>

Top decile by combined ROC + earnings yield rank:

| Rank | Ticker  | ROC rank | EY rank | Combined | Sector          |
|------|---------|----------|---------|----------|-----------------|
| 1    | XXX.N   | 2        | 5       | 7        | Consumer Disc.  |
| 2    | YYY.O   | 4        | 3       | 7        | Technology      |
| ...  | ...     | ...      | ...     | ...      | ...             |

Methodology footer (tool sequence, token cost, anchor-test date)

---
This output is an AI-inferred interpretation of Joel Greenblatt's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Joel Greenblatt or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

**Ticker-check mode output:**

```
Greenblatt-style profile applied to <ticker>
Source: Greenblatt, J. (2006). The Little Book That Beats the Market.

Peer universe: <sector peers>
Universe size: <N>

<Ticker> ranking:
  ROC rank:            <R> of <N> (<percentile>th percentile)
  Earnings yield rank: <R> of <N> (<percentile>th percentile)
  Combined rank:       <R> of <N> (<percentile>th percentile)

Profile fit: <match/partial_match/no_match> — <ticker> is in the [top 10% | top 25% | below top 25%] of the peer universe by Greenblatt combined rank.

Methodology footer

---
This output is an AI-inferred interpretation of Joel Greenblatt's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Joel Greenblatt or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 7 — Emit

## Graceful fallback

If `build_stock_universe` returns fewer than 10 names, the top-decile calculation is unreliable. Expand the universe query once; if expansion fails, return `INSUFFICIENT_UNIVERSE` and decline to render a verdict. In ticker-check mode, this means the Phase 3 consensus meta-skill should treat the profile as `skipped`.

If `get_financials(ratios)` fails for a subset of universe members, drop those names from the ranking and note the coverage loss in the methodology footer.
