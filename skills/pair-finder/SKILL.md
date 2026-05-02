---
name: parallax-pair-finder
description: "Long/short equity pair builder: given one leg, suggest top-3 counter-leg candidates from peers; given both legs, report residual factor / sector / macro / dollar / beta exposure. Symbols in RIC format. NOT for single-stock analysis (use /parallax-deep-dive), not for peer comparison tables (use /parallax-peer-comparison), not for portfolio analysis (use /parallax-morning-brief)."
negative-triggers:
  - Single stock deep dive → use /parallax-deep-dive
  - Generic peer table only → use /parallax-peer-comparison
  - Multi-position portfolio analysis → use /parallax-morning-brief
  - Long-only stock screening → use /parallax-thematic-screen
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - JIT-load references/residual-math.md for factor-net, beta, and hedge-ratio formulas
  - "Default selection criterion (mode B): closest peer with worst total score for short candidates; closest peer with best total score for long candidates"
  - Suggestion mode (one leg given) uses single export_peer_comparison call to guarantee cross-sectionally comparable factor scores across all candidates
  - Evaluate mode (both legs given) MUST flag score-comparability uncertainty when short_ric is NOT in long's peer set (cross-sector pair)
  - "v1 scope cuts: no revenue-geography mix (use domicile/listing-currency only), no share counts (dollar/beta-neutral ratios only), no cross-sector suggestions (within-sector peers only). Evaluate mode accepts cross-sector pairs but flags them."
  - "Liquidity disclaimer is MANDATORY in every output: ADV / borrow / float not validated by Parallax — verify externally before sizing."
---

# Pair Finder

Long/short equity pair construction for fundamental PMs. Given one leg of a thesis, suggest the other leg from peers and report what residual exposure survives the hedge. Given both legs, report the residual.

## Usage

Three invocation modes:

```bash
# Mode 1 — Find short candidate for a long thesis
/parallax-pair-finder NVDA.O long
/parallax-pair-finder NVDA.O long --candidates=3 --with-history

# Mode 2 — Find long candidate for a short thesis
/parallax-pair-finder INTC.O short

# Mode 3 — Evaluate a pair the PM already has
/parallax-pair-finder long=NVDA.O short=AMD.O
/parallax-pair-finder long=NVDA.O short=AMD.O --with-history
```

**Flags:**
- `--candidates=N` (default 3 in suggestion modes; ignored in evaluate mode)
- `--with-history` (adds 60d→180d realized correlation, pair vol, max drawdown, hit rate)

**Default selection criterion (v1):** closest peer with worst total score for short candidates; closest peer with best total score for long candidates. (Same-sector relative-value framing.)

## Workflow

JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns. JIT-load `references/residual-math.md` for factor-net, beta, and hedge-ratio formulas. Call `ToolSearch` with query `"+Parallax"` to load deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Detect mode from invocation:
- `<symbol> long` → Mode 1 (find short candidate)
- `<symbol> short` → Mode 2 (find long candidate)
- `long=<symbol> short=<symbol>` → Mode 3 (evaluate pair)
- Anything else → ask the user to clarify which mode.

### Mode 1 / Mode 2 — Suggestion mode (one leg given)

Inputs: primary RIC + side (`long` | `short`). Optional: `--candidates=N` (default 3), `--with-history`.

#### Batch A — Identification + peer set + macro coverage (parallel)

Fire all three simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | symbol = primary RIC | Validates RIC, returns sector, industry, market cap, market |
| `export_peer_comparison` | symbol = primary RIC, format = "json" | **Workhorse call.** Returns peer set with cross-sectionally comparable factor scores (value, quality, momentum, defensive, tactical, total), sector, industry, market, market cap, P/E, EV/EBITDA, ROE, YTD return, recommendation. Single-call comparability — DO NOT use independent `get_peer_snapshot` calls in this mode |
| `list_macro_countries` | (none) | Gates macro coverage for Batch D |

If `export_peer_comparison` fails: retry once. If it still fails, fall back to `get_peer_snapshot(primary)` and note in output that score comparability across candidates is "best-effort" (Plan-agent finding D).

If `get_company_info` returns empty: apply RIC resolution per `_parallax/parallax-conventions.md` §1 (try `.O`, then `.N`, then escalate to user).

#### Step A.5 — In-process candidate selection (no MCP calls)

From the `export_peer_comparison.data` array, exclude the row where `is_target == true` (that's the primary leg). For the remaining peers:

- **`long` side given** → user wants a SHORT candidate. Sort peers ascending by `total` score. Take the bottom N (default 3). These are the lowest-scoring peers — the v1 mode-B candidates.
- **`short` side given** → user wants a LONG candidate. Sort peers descending by `total` score. Take the top N.

Record each candidate's: ric, company_name, sector, industry, market, all 5 factor scores, total, market cap, recommendation, ytd return.

#### Batch C — Beta computation (parallel, default path — NOT gated by --with-history)

Per spec scope-cut: beta-neutral sizing is in the default path because PMs act on beta-neutral, not dollar-neutral.

Determine benchmark from primary leg's `market` field: US → `SPY` (or `SPY.N` if RIC required); Japan → `EWJ`; UK → `EWU`; etc. (Default fallback: `SPY` if market is unrecognized — flag in output.)

Fire all in parallel:

- `export_price_series(symbol=primary_ric, days=180, format="json")`
- `export_price_series(symbol=candidate_ric, days=180, format="json")` × N candidates
- `export_price_series(symbol=benchmark_ric, days=180, format="json")`

Compute beta inline per `references/residual-math.md` §"Beta computation". Beta-neutral hedge ratio = `beta_long / beta_short` (dollars short per dollar long).

If a price series returns < 90 days of data: flag the affected candidate as "insufficient history for beta" and report only dollar-neutral sizing for that pair.

#### Batch D — Macro residual (parallel, after Batch A confirms primary's market)

Both legs are within-sector in suggestion mode → both legs share the same primary `market`. So one `macro_analyst` call covers both:

- `macro_analyst(market=<primary_market>, component="tactical")`

If `list_macro_countries` does not include `<primary_market>`: skip macro and render "macro context unavailable for this market" in output.

#### Batch E — (Optional, with `--with-history`)

If `--with-history` flag passed, extend Batch C: re-call `export_price_series` with `days=365` for primary + each candidate (skip benchmark — already have it from Batch C). Compute realized correlation, pair vol, max drawdown of the spread, hit rate per `references/residual-math.md` §"Realized pair stats".

(If skill latency is a concern, do this as a single 365-day call per leg in Batch C and slice; revisit if a future audit shows it matters.)
