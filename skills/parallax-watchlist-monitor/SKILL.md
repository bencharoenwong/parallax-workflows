---
name: parallax-watchlist-monitor
description: "Monitor a watchlist of tickers: flag score changes, news alerts, technical shifts, and analyst updates via Parallax MCP tools. Provide list of symbols. NOT for single stock analysis (use /parallax-deep-dive), not for portfolio diagnostics (use /parallax-morning-brief)."
---

<!-- white-label: integration-pattern.md -->

# Watchlist Monitor

## When not to use

- Single stock deep dive → use /parallax-deep-dive
- Portfolio with weights → use /parallax-morning-brief or /parallax-client-review
- Building a portfolio → use /parallax-portfolio-builder

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallback patterns, and the §0.2 integer-param serialization caveat
- This is a surveillance skill — optimized for breadth over depth
- get_score_analysis with 4-8 weeks is sufficient for detecting recent changes — fire all in parallel. `weeks` is non-default here and must be passed as a typed integer at the call site (see conventions §0.2)
- Only call get_news_synthesis for names with significant score changes (saves API calls)
- Rank output by magnitude of change — most-changed at top
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Surveillance scan across a list of tickers — flag what's changed, what needs attention.

## Usage

```
/parallax-watchlist-monitor AAPL.O MSFT.O GOOGL.O AMZN.O META.O NVDA.O TSLA.O
/parallax-watchlist-monitor AAPL.O JPM.N XOM.N JNJ.N weeks=8
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools:

1. **Score Scan** — For each symbol, call `get_score_analysis` with `weeks` as int N, where N is the user-supplied value from the invocation (e.g., `weeks=8`) or 8 if none provided. This is non-default (server default is 52) — see conventions §0.2 for the serialization caveat. Compute change in total score over the period.
2. **Flag Movers** — Identify symbols with significant score changes (>1 point total score change or any factor moving >2 points).
3. **News Check** — For flagged symbols only, call `get_news_synthesis` to identify catalysts.
4. **Technical Check** — For flagged symbols, call `get_technical_analysis` for trend changes.
5. **Analyst Check** — For flagged symbols, call `get_stock_outlook` with `aspect="recommendations"` for consensus shifts.

## Output Format

- **Watchlist Summary** (table: all symbols, current total score, score change, alert flag)
- **Alerts** (ranked by magnitude of change):
  - **Symbol** — score change, which factors moved, brief catalyst
- **Stable Names** (one-liner each — "no material changes")
- **Recommended Actions** (which names warrant a deeper look via /parallax-deep-dive)

Keep it scannable. Lead with what changed.

## Output additions

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** watchlist scan`. Logo handling per integration-pattern.md §5.
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second Provenance line.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
