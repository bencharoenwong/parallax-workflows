---
name: parallax-AI-soros
description: "Applies George Soros's top-down reflexivity framework (per 'The Alchemy of Finance', 1987) to current Parallax data. Two modes: basket mode surfaces regime themes and ranked trade ideas; single-ticker mode runs the same macro workflow and checks ticker exposure via dual channels (industry exposure AND telemetry basket theme). Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized."
negative-triggers:
  - Bottom-up factor scoring → use /parallax-AI-buffett
  - Mechanical formula screen → use /parallax-AI-greenblatt
  - Balance-sheet-first checks → use /parallax-AI-klarman
  - Cross-profile consensus → use /parallax-AI-consensus
  - Full macro outlook without a persona lens → use /parallax-macro-outlook
  - Morning brief for a portfolio → use /parallax-morning-brief
gotchas:
  - JIT-load _parallax/parallax-conventions.md, profile-schema.md, output-template.md, profiles/soros.md
  - Soros has TWO modes — basket (no ticker) and single-ticker dual-channel — sharing a macro workflow
  - list_macro_countries is 1 token; macro_analyst is 5 tokens per market — cap at 5 markets
  - get_telemetry is 1 token but distinctive — it's the second exposure channel for single-ticker mode
  - Single-ticker mode requires BOTH the macro workflow AND a ticker-exposure check via 2 independent channels
  - NEVER use first-person impersonation of Soros — always frame as "Soros-style" or "reflexivity lens identifies"
  - The dual-channel logic is load-bearing — single-channel flag is partial, not full match
  - Disclaimer verbatim per output-template.md, substituting "George Soros" for [Investor]
  - build_stock_universe is async (~15-40s) and may time out — fallback per conventions §4
---

# Parallax AI Soros Profile

Top-down reflexivity lens: regime identification → thematic exposure → ranked trade ideas OR single-ticker dual-channel check.

## Usage

```
/parallax-AI-soros                         # basket mode — regime themes + ranked ideas
/parallax-AI-soros AAPL.O                  # single-ticker mode — dual-channel exposure check
/parallax-AI-soros --markets US,JP,EU      # basket mode with explicit market list
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools.

### Step 0 — JIT-load dependencies

Before the first Parallax tool call:

1. Load `skills/_parallax/parallax-conventions.md`
2. Load `skills/_parallax/AI-profiles/profile-schema.md`
3. Load `skills/_parallax/AI-profiles/output-template.md`
4. Load `skills/_parallax/AI-profiles/profiles/soros.md`

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas.

### Step 1 — Determine mode

- Zero tickers → **basket mode**
- Exactly one ticker → **single-ticker mode**
- Multiple tickers → reject: "Soros profile takes zero or one ticker. Use /parallax-AI-consensus for multi-ticker."

### Step 2 — Macro workflow (runs in BOTH modes)

1. Call `list_macro_countries` to get covered markets (1 token).
2. Select 3-5 tactically interesting markets. Default: US, JP, EU plus top-2 EM based on telemetry divergence. If user passed `--markets`, use that list.
3. Call `macro_analyst(component=tactical)` for each selected market IN PARALLEL (5 tokens each × 3-5 = 15-25 tokens).
4. Call `get_telemetry` for cross-market regime divergence signals (1 token).
5. Identify 1-3 regime themes where macro and telemetry agree on directional views. Examples:
   - "Fed cutting + dollar weakening → EM equities and commodities"
   - "Rates higher for longer → financials and defensive dividend payers"
   - "Fiscal divergence US vs EU → US cyclicals overweight EU cyclicals"

### Step 3 — Basket mode completion (skip if single-ticker)

1. For each identified theme, call `build_stock_universe` with a thematic query (5 tokens each, async).
2. For top 3-5 names per theme, call `get_peer_snapshot` (1 token each).
3. Apply cross-validation gate per `profile-schema.md §2 Step 2` for each ticker surfaced.
4. Rank names within each theme by momentum + macro sensitivity.
5. Render as `trade_ideas` output (Step 5).

### Step 4 — Single-ticker mode completion (skip if basket)

1. Call `get_company_info` on the input ticker (1 token) — retrieve sector, industry.
2. For each identified theme, call `build_stock_universe` with the theme's query (5 tokens each).
3. **Dual-channel exposure check:**

   **Channel A — Industry exposure:**
   - Does the ticker appear directly in any theme's `build_stock_universe` result?
   - OR does the ticker's sector/industry classification match a theme's target industry (e.g., ticker is Energy, theme is "Energy benefiting from dollar weakness")?
   - Output: `FLAGGED` or `NOT_FLAGGED` for channel A.

   **Channel B — Telemetry basket theme:**
   - Does the ticker fall into any regime basket surfaced by `get_telemetry`?
   - Telemetry baskets are typically named (e.g., "growth-over-value rotation," "dollar regime beneficiaries").
   - Output: `FLAGGED` or `NOT_FLAGGED` for channel B.

4. Cross-validation gate: after `get_peer_snapshot` (if called during universe resolution), cross-check name per conventions.

5. Combine:
   - Both channels `FLAGGED` → verdict `match`
   - Exactly one channel `FLAGGED` → verdict `partial_match`
   - Neither flagged → verdict `no_match`

### Step 5 — Render through output template

**Basket mode output:**

```
Soros-style regime themes and trade ideas

Source: Soros, G. (1987). The Alchemy of Finance. | Drobny, S. (2006). Inside the House of Money.

Reflexivity framework: identify regime break or narrative-fundamentals divergence → surface exposed industries → concentrate on high-conviction names.

Markets analyzed: <list>

## Theme 1: <name>
Macro thesis: <one paragraph — regime break or tactical opportunity>
Directional view: <long / short / rotation>
Currency/rate context: <brief>

Ranked trade ideas:
| Rank | Ticker | Industry | Momentum | Rationale |
|------|--------|----------|----------|-----------|
| 1    | XXX.N  | ...      | 7.2      | ...       |
| ...  | ...    | ...      | ...      | ...       |

## Theme 2: <name>
[same structure]

Workflow derived from: Soros (1987); Drobny (2006).
Last anchor-tested: <date> | Last legal review: <date>
Tool sequence: list_macro_countries, macro_analyst × N, get_telemetry, build_stock_universe × N, get_peer_snapshot × M
Token cost: ~25-40 tokens

---
This output is an AI-inferred interpretation of George Soros's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by George Soros or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

**Single-ticker mode output:**

```
Soros-style profile applied to <ticker>

Source: Soros, G. (1987). The Alchemy of Finance.

Reflexivity framework: top-down regime identification → thematic exposure check. Single-ticker mode answers "is this stock in an industry and basket theme the current regime analysis flags?"

Current regime themes (1-3): <list with one-line theses>

Ticker exposure check (dual-channel):

  Channel A — Industry exposure
    <ticker>'s sector/industry: <sector>
    Industry appears in theme(s): <theme names or NONE>
    Status: FLAGGED / NOT FLAGGED

  Channel B — Telemetry basket theme
    Telemetry baskets surfaced: <list>
    <ticker> falls in basket(s): <basket names or NONE>
    Status: FLAGGED / NOT FLAGGED

Profile fit: <match / partial_match / no_match>
  - match: both channels flagged (genuine thematic exposure)
  - partial_match: one channel flagged (industry OR basket, not both)
  - no_match: neither channel flagged (Soros-style lens has no current view)

Workflow derived from: Soros (1987); Drobny (2006).
Last anchor-tested: <date> | Last legal review: <date>

---
This output is an AI-inferred interpretation of George Soros's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by George Soros or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 6 — Emit

## Graceful fallback

If `list_macro_countries` fails, derive covered markets from RIC suffix defaults per `parallax-conventions.md §6` and note degradation.

If `macro_analyst` fails for a subset of markets, proceed with remaining markets as long as ≥2 succeeded.

If `get_telemetry` fails, single-ticker mode cannot perform Channel B. Fall back to industry-exposure-only: verdict becomes `match` (channel A only, noted as "telemetry unavailable"), `partial_match`, or `no_match`. Document the degradation in the output.

If `build_stock_universe` returns no names or times out for any theme, the themes are still surfaced without names. For basket mode, report themes without rankings. For single-ticker mode, channel A is `NOT_FLAGGED`.
