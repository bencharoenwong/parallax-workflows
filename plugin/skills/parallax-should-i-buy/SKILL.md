---
name: parallax-should-i-buy
description: "Quick stock evaluation: company overview, Parallax factor scores, financial health, score trends, macro context, dividends, news, and analyst outlook. Plain language output. Accepts plain ticker (AAPL) or RIC (AAPL.O). NOT for portfolio analysis (use /parallax-morning-brief), not for full due diligence (use /parallax-due-diligence), not for a position deep dive with AI assessment (use /parallax-deep-dive), not for peer-set comparison (use /parallax-peer-comparison), not for methodology-only questions (use /parallax-score-explainer), not for backtesting (use /backtest)."
---

<!-- white-label: integration-pattern.md -->

# Should I Buy

## When not to use

- Portfolio-level analysis → use /parallax-morning-brief
- Full research report → use /parallax-due-diligence
- Position deep dive with AI assessment → use /parallax-deep-dive
- Peer comparison deep dive → use /parallax-peer-comparison
- Methodology-only explanation → use /parallax-score-explainer
- Running backtests → use /backtest

## Gotchas

- Expected Parallax spend: ~29 tokens (`_parallax/token-costs.md`), which already includes the two macro markets; each market is 5 of the 29.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4 fallbacks, §14 host primitives, §15 translation.
- JIT-load `_parallax/house-view/loader.md` FIRST; if an active view is present follow §2 (validation), §7.1/§7.2/§7.3 (single-stock conflict surfacing), §6 (audit). Do NOT apply tilts — single-stock skills surface conflicts only; peer suggestions are flagged, never filtered. Route every §7 token through `render_view_conflict()` per `_parallax/house-view/render_helpers.md`; never hand-construct the string.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report) — load happens in Step 0, rendering in Step 5.
- `get_stock_outlook` has 4 aspects — analyst_targets, recommendations, risk_return, dividends; coverage rule per conventions §4 "Stock outlook coverage".
- `explain_methodology` is free — use it for any factor score ≥ 8 or ≤ 3.
- A language argument other than `en` makes Step 7 mandatory (conventions §15); the routing block shape and the disclaimer boundary check live there.

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

Every host interaction below is a host primitive from `parallax-conventions.md` §14; the per-host binding is in §14.2 and the fail-open rule per primitive in §14.3. Parallax callables are whatever `discover-tools` returns this session — never a remembered namespace (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–4: `get_company_info`, the Batch A and Batch B tools, `explain_methodology`) to the exact callable and schema the connector exposes now (conventions §0.0–§0.1).
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: symbol; optional language (`en` default); optional `register=`; optional `audience=` (conventions §13.1 precedence).
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the tilt vector and excludes for §7.1/§7.2/§7.3 surfacing in Step 5. Do NOT apply tilts.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`. The loader returns exactly seven keys (`load_visual_branding()`); `branding["voice"]` raises `KeyError` by design.

### Step 1 — Resolve inputs

`call-tool` `get_company_info` with the plain ticker or RIC. If empty, retry with exchange suffixes per conventions §1. For `.HK` and numeric codes, apply the §1 ambiguity cross-check. On the fund/OEIC pattern, apply the §1 fallback and stop.

### Step 2 — Fetch (parallel batches)

**Batch A** — once the RIC is confirmed, `call-tool` all of the following together:

| Tool | Parameters | Notes |
|---|---|---|
| `get_peer_snapshot` | `symbol` | Factor scores + peer ranking |
| `get_financials` | `symbol`, `statement="summary"` | Revenue/income narrative |
| `get_score_analysis` | `symbol` | 52-week factor trend (server default) |
| `get_technical_analysis` | `symbol` | Trend direction, momentum, support/resistance — feeds the Technicals lens. Async, may time out (fallback in Output Format) |
| `get_stock_outlook` | `symbol`, `aspect="analyst_targets"` | Price targets |
| `get_stock_outlook` | `symbol`, `aspect="recommendations"` | Buy/hold/sell |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` | Risk/return vs peers |
| `get_stock_outlook` | `symbol`, `aspect="dividends"`, `limit` as int 8 (non-default; default is 20 — conventions §0.2) | Dividend history |
| `get_news_synthesis` | `symbol` | Async — never blocks output (§5) |

**Batch B** — after Step 1 (needs company info for market reasoning): `list_macro_countries`; identify relevant markets (home market + key revenue geographies) per conventions §6, cap at 2; `macro_analyst` with `component="tactical"` per relevant covered market. If no covered market is relevant, the macro section is skipped.

### Step 3 — Verify

- Identity cross-check per conventions §2: `get_peer_snapshot.target_company` against `get_company_info.name` after normalization; `get_score_analysis` `data[0].symbol` against the requested RIC. On divergence, warn and treat `get_company_info` as the source of truth; never present mismatched scores as the intended security.
- Outlook coverage per conventions §4 "Stock outlook coverage": 0–1 of the four aspects returned → the Dividends and Analyst View sections carry the §4 "materially incomplete" flag.
- Every failed or empty call: retry classification per §0.1, then the §4 display-section rule. This skill renders no gate (no pass/fail verdict on the name), so §4.0 does not apply.

### Step 4 — Compute

No deterministic helper: this skill renders Parallax's own figures and never derives new numbers. The only computed conditions are the house-view flags — §7.3 tension (`total_score ≥ 7` AND the stock's sector tilt ≤ −1) and §7.2 peer-suggest conflict — evaluated exactly as `loader.md` states. `call-tool` `explain_methodology` for any factor score ≥ 8 or ≤ 3.

### Step 5 — Compose

Fill **Output Format** below, in order. Branding Header and About This Report per integration-pattern.md §5/§7; house-view flags via `render_view_conflict()`; audience mode per conventions §13; AI-interaction disclosure per `parallax-conventions.md §9.2`; disclaimer per loader.md §5 when a view is active, otherwise `parallax-conventions.md §9.1`. Apply the §4 fallbacks for any missing section rather than omitting it silently.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3, with this skill's key (`<skill-dir>` is the absolute path of the directory this SKILL.md was loaded from; `_parallax/` is its sibling):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/shouldibuy.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill should-i-buy < "$DRAFT"; rm -f "$DRAFT"
```

The entire final English message is exactly that command's stdout, or the sole input to Step 7. The stderr `[render-gate] WARN:` line is diagnostics: never include it, never translate it; it means the opening drifted from the Output Format start — fix and re-run. If `run-shell` is absent on this host, apply conventions §14.3 (render-gate row).

### Step 7 — Translate (conditional)

Only when the language argument is not `en`. Translate per `parallax-conventions.md` §15: routing block shape (§15.2), failure footers (§15.3), disclaimer boundary check (§15.4). Skill-specific inputs: the body is the gated Step 6 stdout in Output Format order (The Company through the disclaimer, including the audit line); pass `register: retail` only when `register=retail` was supplied; the translator consumes rendered prose, never raw tool JSON.

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


## Failure modes

- Ticker unresolved after conventions §1 (two suffix attempts): stop and ask for the RIC; fund/OEIC pattern → the §1 fallback message, no raw error.
- `get_technical_analysis` timeout: Technicals lens renders from the Momentum factor proxy with the documented prefix; the lens never disappears.
- 0–1 `get_stock_outlook` aspects: Dividends and Analyst View flagged materially incomplete (conventions §4).
- News or macro pending: placeholder per conventions §5 / §6; output is not blocked.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked unavailable with its reason, except Macro Context, which is skipped when no covered market is relevant (Step 2 Batch B). First line is `## The Company` or the Branding Header / House View Preamble.
- When a view is active, the `view_status` banner string appears verbatim in the output (conventions §0.3 item 4).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present.
- Audit log entry appended per loader.md §6 (every consume event, including the no-view case with its `applied_reason`).
- Expected spend stated (Gotchas) and not exceeded without a stated reason.
- Translation (if requested) completed per §15, or the §15.3 footer explains why not.
