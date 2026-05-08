---
name: parallax-should-i-buy
description: "Quick stock evaluation: company overview, Parallax factor scores, financial health, score trends, macro context, dividends, news, and analyst outlook. Plain language output. Accepts plain ticker (AAPL) or RIC (AAPL.O). NOT for portfolio analysis (use /parallax-morning-brief), not for full due diligence (use /parallax-due-diligence), not for backtesting (use /backtest)."
negative-triggers:
  - Portfolio-level analysis → use /parallax-morning-brief
  - Full research report → use /parallax-due-diligence
  - Running backtests → use /backtest
  - Peer comparison deep dive → use /parallax-peer-comparison
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §7.1/§7.2/§7.3 (single-stock conflict surfacing — blanket note + peer-suggest token + score-tension banner), §6 (audit). Do NOT apply tilts — single-stock skills surface conflicts only; peer suggestions are flagged but never filtered.
  - When rendering §7.1/§7.2/§7.3 flags, JIT-load _parallax/house-view/render_helpers.md and route every token through `render_view_conflict()`. Do not hand-construct the string.
  - When active view is present, use the view-aware disclaimer per loader.md §5; otherwise use the standard disclaimer
  - get_stock_outlook supports 4 aspects — analyst_targets, recommendations, risk_return, dividends
  - explain_methodology is free/instant — use it for any notably high or low score
  - For non-US tickers, consult the exchange suffix table in shared conventions
  - Always include the disclaimer at the end
  - If a second positional arg is supplied AND is not `en`, Step 5 (Translate output) is MANDATORY — do not skip. Route `zh-CN`/`zh-TW`/`zh-HK` to `/translate-chinese-finance`, `th` to `/translate-thai-finance`. The variant must be passed as an imperative one-line prefix (`Translate to <variant>:`) above the rendered prose, otherwise the Chinese translator will ask the user to disambiguate (especially for `zh-HK`) and break the automated chain.
  - Disclaimer boundary check after translation: track which disclaimer was rendered in the English output (view-aware per loader.md §5 if a house view is active, otherwise the standard wording). If the translator drops the disclaimer, re-append THAT SAME disclaimer (translated if possible, English fallback if not) — not the standard one unconditionally.
---

# Should I Buy

Quick, plain-language stock evaluation using Parallax MCP tools.

## Usage

```
/parallax-should-i-buy AAPL
/parallax-should-i-buy MSFT.O
/parallax-should-i-buy 005930.KS
/parallax-should-i-buy AAPL zh-CN
/parallax-should-i-buy 005930.KS th
```

Accepts plain tickers (auto-converts to RIC) or RIC format directly. Optional second positional arg sets the output language — one of `en` (default), `zh-CN`, `zh-TW`, `zh-HK`, `th`. Anything else falls back to `en` with a warning.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, fallback patterns, and HK ambiguity protocol. JIT-load `_parallax/house-view/loader.md` for active-view validation and single-stock conflict surfacing.

### Step 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2 + §7.1/§7.2/§7.3. If view present, capture tilt vector + excludes. Do NOT apply tilts to scoring. During output rendering (see Output Format below), surface: (a) the blanket House View Note immediately after The Scores (§7.1), (b) an inline peer-suggest token at the Risk vs Peers section if Parallax's peer-suggest sits on a view-UW sector or the excludes list (§7.2), (c) an inline tension banner at The Scores if `total_score ≥ 7` AND the stock's sector is UW in the view (§7.3). Flag, do not filter — peer suggestions stay in the table.

### Step 1 — Resolve Ticker

Use `get_company_info` with the plain ticker or RIC. If empty, retry with exchange suffixes per shared conventions. For `.HK`/numeric codes, apply the HK ambiguity cross-check.

### Step 2 — Fire data calls in parallel

Once RIC is confirmed, call **all of the following simultaneously**:

| Tool | Parameters | Notes |
|---|---|---|
| `get_peer_snapshot` | `symbol` | Factor scores + peer ranking |
| `get_financials` | `symbol`, `statement="summary"` | Revenue/income narrative |
| `get_score_analysis` | `symbol` | 52-week factor trend (server default) |
| `get_stock_outlook` | `symbol`, `aspect="analyst_targets"` | Price targets |
| `get_stock_outlook` | `symbol`, `aspect="recommendations"` | Buy/hold/sell |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` | Risk/return vs peers |
| `get_stock_outlook` | `symbol`, `aspect="dividends"`, `limit` as int 8 (non-default; default is 20 — see conventions §0.1) | Dividend history |
| `get_news_synthesis` | `symbol` | Async — don't block output |

### Step 3 — Macro context

After Step 1 resolves (need company info for market reasoning):

1. Call `list_macro_countries` to check coverage.
2. Identify relevant markets (home market + key revenue geographies). Cap at 2 markets.
3. Call `macro_analyst` with component="tactical" for each relevant covered market.

If no covered markets are relevant, skip macro section.

### Step 4 — Interpret and explain

- Call `explain_methodology` for any notably high (≥8) or low (≤3) factor score.
- Synthesize all data into plain-language output.
- Apply graceful fallback patterns from shared conventions for any missing data.

## Output Format

Present as a friendly, structured report. When an active house view is loaded, JIT-load `_parallax/house-view/render_helpers.md` and route every §7 flag through `render_view_conflict()` — do not hand-construct the strings.

- **The Company** (what they do, how big)
- **The Scores** (simple table with plain-English interpretation; include 52-week trend direction — e.g., "Quality trending up from 5.8 to 7.2")
  - *If view active:* check §7.3 tension condition (`total_score >= 7.0 AND view.tilts.sectors[stock_sector] <= -1`). If true, render the tension banner via `render_view_conflict(kind="score_tension", ...)` directly below the scores table.
- **House View Note** (only if view active and stock conflicts with view) — render via `render_view_conflict(kind="blanket", ...)` per loader.md §7.1. This section appears HERE — immediately after The Scores — so the reader sees the view lens before reading the rest. Not at the bottom of the output.
- **Financial Health** (green/yellow/red traffic light metaphor)
- **Macro Context** (2-3 sentences on the relevant economic environment — skip if no covered markets)
- **Dividends** (yield, consistency, recent changes — or "Not a dividend payer" if none)
- **Risk vs Peers** (risk/return profile relative to peer group)
  - *If view active AND `get_peer_snapshot.suggestion` returned a peer:* check §7.2 condition (peer's sector tilt ≤ -1 in view, or peer ticker on excludes). If true, render the inline token via `render_view_conflict(kind="peer_suggest", ...)` immediately under the Risk vs Peers section. Flag, do not filter — the peer stays in the table.
- **Recent News** (bullets)
- **Analyst View** (price target range, consensus)
- **Bottom Line** (balanced 2-sentence summary — pros and cons, not a recommendation)

Append audit log entry per loader.md §6.

If active view: use the view-aware disclaimer per loader.md §5. Otherwise:

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*

### Step 5 — Translate output (conditional, terminal)

This step runs ONLY when the user supplied a second positional arg AND that arg is not `en`.

**Imperative directive — do not skip.** Capture two things from the rendered English output before invoking the translator:

1. The full body — every section in the Output Format above, in order: The Company, The Scores, House View Note (if rendered), Financial Health, Macro Context, Dividends, Risk vs Peers, Recent News, Analyst View, Bottom Line, audit log entry, Disclaimer. Both the audit log entry (per loader.md §6) and the Disclaimer (per loader.md §5 if view active, otherwise the standard wording at the bottom of this file) are in scope.
2. Which disclaimer variant was rendered (view-aware vs. standard). Used by the boundary check below.

**Variant routing (mechanism is explicit — the translator skill has no parameter slot, only prose).** Invoke the appropriate translator skill with a one-line variant prefix on the input, then the rendered body:

- `zh-CN` → `/translate-chinese-finance` with input prefixed by `Translate to zh-CN (Simplified, mainland conventions):`
- `zh-TW` → `/translate-chinese-finance` with input prefixed by `Translate to zh-TW (Traditional, Taiwan conventions):`
- `zh-HK` → `/translate-chinese-finance` with input prefixed by `Translate to zh-HK (Traditional, Hong Kong conventions):` — the prefix is REQUIRED for HK because otherwise the Chinese translator will pause to ask the user, breaking the automated chain.
- `th` → `/translate-thai-finance` (no variant — the Thai skill has no branching).

The translator skill consumes the rendered prose, NOT the raw MCP tool responses. Do not pass `get_company_info` JSON or `get_score_analysis` payloads through the translator — they are structural data, not narrative.

Translator-failure handling:
- If the translator fails or returns an empty/partial result, output the original English with a one-line warning footer: `> Translation to <lang> failed; output shown in English. Re-run if the issue is transient.`
- If the language arg is unrecognized (anything other than the five values listed in Usage), output the original English with: `> Language '<arg>' not supported; output shown in English. Supported: en, zh-CN, zh-TW, zh-HK, th.`
- Translator output replaces the English output in the chat; do not show both.

**Disclaimer boundary check.** Translators are instructed to preserve disclaimer wording per `_parallax/parallax-conventions.md` §9, but compliance is not guaranteed. After translation completes, if the disclaimer is missing from the translated output:

- If the original English used the **view-aware disclaimer** (active house view), re-append the view-aware wording per loader.md §5 in English (the translator already had its chance; do not re-attempt translation just for the disclaimer).
- If the original English used the **standard disclaimer**, re-append the standard wording in English.

Do NOT re-append the standard disclaimer unconditionally — that would substitute the wrong text in any view-active session.
