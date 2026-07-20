---
name: parallax-should-i-buy
description: "Quick stock evaluation: company overview, Parallax factor scores, financial health, score trends, macro context, dividends, news, and analyst outlook. Plain language output. Accepts plain ticker (AAPL) or RIC (AAPL.O). NOT for portfolio analysis (use /parallax-morning-brief), not for full due diligence (use /parallax-due-diligence), not for backtesting (use /backtest)."
---

<!-- white-label: integration-pattern.md -->

# Should I Buy

## When not to use

- Portfolio-level analysis → use /parallax-morning-brief
- Full research report → use /parallax-due-diligence
- Running backtests → use /backtest
- Peer comparison deep dive → use /parallax-peer-comparison

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
- JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §7.1/§7.2/§7.3 (single-stock conflict surfacing — blanket note + peer-suggest token + score-tension banner), §6 (audit). Do NOT apply tilts — single-stock skills surface conflicts only; peer suggestions are flagged but never filtered.
- When rendering §7.1/§7.2/§7.3 flags, JIT-load _parallax/house-view/render_helpers.md and route every token through `render_view_conflict()`. Do not hand-construct the string.
- LANGUAGE PILOT — if a second positional arg is supplied AND is not `en`, Step 5 (Translate output) is MANDATORY — do not skip. Route `zh-CN`/`zh-TW`/`zh-HK` to `/translate-chinese-finance`, `th` to `/translate-thai-finance`. The variant must be passed as a delimited routing block ABOVE the prose body — NOT as a prose sentence the translator could echo. Use exactly this shape (the marker line and the dashed separator are required so the translator skips the block):
ROUTING DIRECTIVE — DO NOT TRANSLATE OR ECHO THIS BLOCK:
        target_variant: zh-HK            # one of: zh-CN | zh-TW | zh-HK | (omit for Thai)
        register: institutional | retail # optional; absent → institutional
        source_language: en
        begin_content_below_separator: true
      ---

      <rendered prose body starts here>

    Without this exact shape, zh-HK in particular will trigger the Chinese translator's "ask for HK listings" branch and break the automated chain.
- Disclaimer boundary check after translation: track which disclaimer was rendered in the English output (view-aware per loader.md §5 if a house view is active, otherwise the standard wording). If the translator dropped the disclaimer, FIRST attempt a single-section re-translation pass on just the disclaimer text (using the same routing-directive shape) so the appended disclaimer matches the output language. Only fall back to appending the original English disclaimer if the second translator pass also fails or returns empty.
- When active view is present, use the view-aware disclaimer per loader.md §5; otherwise use the standard disclaimer
- get_stock_outlook supports 4 aspects — analyst_targets, recommendations, risk_return, dividends
- explain_methodology is free/instant — use it for any notably high or low score
- For non-US tickers, consult the exchange suffix table in shared conventions
- Always include the disclaimer at the end
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.

Quick, plain-language stock evaluation using Parallax MCP tools.

## Usage

```
/parallax-should-i-buy AAPL
/parallax-should-i-buy MSFT.O
/parallax-should-i-buy 005930.KS
/parallax-should-i-buy AAPL zh-CN
/parallax-should-i-buy 005930.KS th
/parallax-should-i-buy AAPL zh-CN register=retail
/parallax-should-i-buy AAPL audience=client_safe
```

Accepts plain tickers (auto-converts to RIC) or RIC format directly. Optional second positional arg sets the output language — one of `en` (default), `zh-CN`, `zh-TW`, `zh-HK`, `th`. Optional keyword `register=retail` after the positional language passes the retail register to the translator; absent means institutional register. Optional third argument: `audience=client_safe | audience=internal_analyst`; precedence follows `parallax-conventions.md` §13.1. Anything else falls back to `en` with a warning.

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
| `get_technical_analysis` | `symbol` | Trend direction, momentum, support/resistance — feeds the Technicals lens. Async ~2-5s, may time out (see Technicals fallback in Output Format) |
| `get_stock_outlook` | `symbol`, `aspect="analyst_targets"` | Price targets |
| `get_stock_outlook` | `symbol`, `aspect="recommendations"` | Buy/hold/sell |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` | Risk/return vs peers |
| `get_stock_outlook` | `symbol`, `aspect="dividends"`, `limit` as int 8 (non-default; default is 20 — see conventions §0.2) | Dividend history |
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

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format. The loader returns exactly seven keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete English report per **Output Format** below, then run it through the **shared** render gate in **one Bash step** before replying or translating. Use a private `mktemp` file. The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key with `--skill should-i-buy` (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/shouldibuy.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill should-i-buy < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final English message is exactly that command's stdout** — nothing before it, nothing after it. If Step 5 translation runs, it consumes this gated stdout; translated output is not re-gated.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is `## The Company`, or the Branding Header / House View Preamble when active.

Present as a friendly, structured report. When an active house view is loaded, JIT-load `_parallax/house-view/render_helpers.md` and route every §7 flag through `render_view_conflict()` — do not hand-construct the strings. Per loader.md §5.1 the active-view load preamble (from Step 0) renders at the very top of output. Apply audience render mode per `parallax-conventions.md` §13; default internal_analyst.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the house view preamble (or at the very top if no view): `**<client_name>** stock review`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **The Company** (what they do, how big)
- **Fundamentals** — lens header introducing the factor + financial read. Keep its two subsections explicitly labeled (do not fold them into the header):
  - **The Scores** (simple table with plain-English interpretation; include 52-week trend direction — e.g., "Quality trending up from 5.8 to 7.2"; under `audience=client_safe`, factor rows carry the §13.3 gloss)
    - *If view active:* check §7.3 tension condition (`total_score >= 7.0 AND view.tilts.sectors[stock_sector] <= -1`). If true, render the tension banner via `render_view_conflict(kind="score_tension", ...)` directly below the scores table.
  - **House View Note** (only if view active and stock conflicts with view) — render via `render_view_conflict(kind="blanket", ...)` per loader.md §7.1. This appears HERE — immediately after The Scores — so the reader sees the view lens before reading the rest. Not at the bottom of the output.
  - **Financial Health** (green/yellow/red traffic light metaphor)
- **Technicals** — lens header (the price-action read, kept distinct from Fundamentals). From `get_technical_analysis`: trend direction (`STRONG_POSITIVE`…`STRONG_NEGATIVE`), momentum, and support/resistance levels. State a one-line directional read for the lens. The Technicals read cites price/trend/momentum only — it does not borrow factor scores or financials as evidence. *Fallback:* if `get_technical_analysis` is unavailable or times out, render the lens from the Momentum factor proxy (`get_score_analysis` momentum sub-trend) and prefix it `Technical analysis unavailable — Momentum factor proxy:`. The lens always produces a read; it never silently disappears.
- **Macro Context** (2-3 sentences on the relevant economic environment — skip if no covered markets)
- **Dividends** (yield, consistency, recent changes — or "Not a dividend payer" if none)
- **Risk vs Peers** (risk/return profile relative to peer group)
  - *If view active AND `get_peer_snapshot.suggestion` returned a peer:* check §7.2 condition (peer's sector tilt ≤ -1 in view, or peer ticker on excludes). If true, render the inline token via `render_view_conflict(kind="peer_suggest", ...)` immediately under the Risk vs Peers section. Flag, do not filter — the peer stays in the table.
- **Recent News** (bullets)
- **Analyst View** (price target range, consensus). Always state source: "third-party analyst consensus via Parallax's data provider". Under `audience=client_safe`, render the price-target range only; omit the Buy/Hold/Sell distribution.
- **Bottom Line** (balanced summary — pros and cons, not a recommendation). State each lens's directional read — Fundamentals and Technicals — explicitly. If the two lenses diverge (e.g. constructive fundamentals vs. weak price action), name the divergence rather than averaging it into one blended verdict.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line. Under `audience=client_safe`, append the §13.4 mode line.

Integration note: the underlying figures come from the structured JSON of the MCP tools listed in the workflow — production integrations call those tools directly; this markdown report is the interactive/chat tier.

Append audit log entry per loader.md §6.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

### Step 5 — Translate output (conditional, terminal)

This step runs ONLY when the user supplied a second positional arg AND that arg is not `en`.

**Imperative directive — do not skip.** Capture two things from the rendered English output before invoking the translator. Capture the gated output of the Render step, not the pre-gate draft; translated output is not re-gated:

1. The full body — every section in the Output Format above, in order: The Company, The Scores, House View Note (if rendered), Financial Health, Macro Context, Dividends, Risk vs Peers, Recent News, Analyst View, Bottom Line, audit log entry, Disclaimer. Both the audit log entry (per loader.md §6) and the Disclaimer (per loader.md §5 if view active, otherwise the standard wording at the bottom of this file) are in scope.
2. Which disclaimer variant was rendered (view-aware vs. standard). Used by the boundary check below.

**Variant routing (mechanism is explicit — the translator skill has no parameter slot, only prose; we use a delimited routing block so the translator does not echo it).** Invoke the appropriate translator skill with the input shaped as follows:

```
ROUTING DIRECTIVE — DO NOT TRANSLATE OR ECHO THIS BLOCK:
  target_variant: <variant>
  register: retail
  source_language: en
  begin_content_below_separator: true
---

<rendered prose body>
```

Variant routing table:

- `zh-CN` → `/translate-chinese-finance`, `target_variant: zh-CN`
- `zh-TW` → `/translate-chinese-finance`, `target_variant: zh-TW`
- `zh-HK` → `/translate-chinese-finance`, `target_variant: zh-HK` — the routing block is REQUIRED for HK because otherwise the Chinese translator pauses to ask the user (per its `SKILL.md` Greater-China default rules) and breaks the automated chain.
- `th` → `/translate-thai-finance` — `target_variant` line may be omitted (Thai has no branching), but the routing block (with the marker line and `---` separator) is still REQUIRED so the translator does not echo any leading meta into output.

Pass `register: retail` iff `register=retail` was supplied; otherwise omit the `register:` line so the translator defaults to institutional register.

The translator skill consumes the rendered prose, NOT the raw MCP tool responses. Do not pass `get_company_info` JSON or `get_score_analysis` payloads through the translator — they are structural data, not narrative.

Translator-failure handling:
- If the translator fails or returns an empty/partial result, output the original English with a one-line warning footer: `> Translation to <lang> failed; output shown in English. Re-run if the issue is transient.`
- If the language arg is unrecognized (anything other than the five values listed in Usage), output the original English with: `> Language '<arg>' not supported; output shown in English. Supported: en, zh-CN, zh-TW, zh-HK, th.`
- Translator output replaces the English output in the chat; do not show both.

**Disclaimer boundary check.** Translators are instructed to preserve disclaimer wording per `_parallax/parallax-conventions.md` §9, but compliance is not guaranteed. After translation completes, if the disclaimer is missing from the translated output:

1. **First try a single-section re-translation pass.** Invoke the same translator skill with the same routing block (variant unchanged), passing only the original English disclaimer text as the body. Append the result to the translated output. This keeps the entire output in the target language for the common case (translator merely dropped the disclaimer).

2. **If the re-translation pass fails or returns empty**, fall back to appending the original English disclaimer text — but use the disclaimer that was actually rendered in the English output (view-aware per loader.md §5 if the session has an active house view, otherwise the standard wording). Do NOT re-append the standard disclaimer unconditionally — that would substitute the wrong text in any view-active session.

3. **Audit, do not surface.** When the boundary check fires (either step 1 or step 2), record the event in the existing audit log entry's `notes` field per loader.md §6.2 (e.g., `notes: "disclaimer boundary check fired — re-translated"` or `notes: "disclaimer boundary check fired — english fallback"`). Do NOT add a custom key to the audit entry — loader.md §6.3 forbids skill-specific custom keys; `notes` is the schema-compliant landing spot for free-text traces. Do NOT add a user-visible footer — the appended content is correct either way and a technical English note in an otherwise translated document defeats the purpose of the re-translation pass.
