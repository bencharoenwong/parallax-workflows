---
name: parallax-deep-dive
description: "Deep dive on a single position: company profile, peer comparison, financials, score trends, macro context, technicals, dividends, news, and AI assessment via Parallax MCP tools. Symbol in RIC format. NOT for quick stock checks (use /parallax-should-i-buy), not for portfolio-level analysis (use /parallax-morning-brief), not for statement-level forensic audit or Palepu framework analysis (use /parallax-due-diligence), not for peer-set comparison only (use /parallax-peer-comparison), not for a client-branded rendering of the full research report (use /parallax-white-label-stock-report)."
---

<!-- white-label: integration-pattern.md -->

# Position Deep Dive

## When not to use

- Quick stock check → use /parallax-should-i-buy
- Portfolio analysis → use /parallax-morning-brief
- Full due diligence with Palepu → use /parallax-due-diligence
- Peer comparison only → use /parallax-peer-comparison
- Client-branded full research report → use /parallax-white-label-stock-report

## Gotchas

- Expected Parallax spend: ~45 tokens (`_parallax/token-costs.md`): assessment 10, technicals 5, three macro markets 15, plus the 1-token calls.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4 fallbacks, §14 host primitives, §15 translation.
- JIT-load `_parallax/house-view/loader.md` FIRST; if an active view is present follow §2 (validation), §7.1/§7.2/§7.3 (single-stock conflict surfacing), §6 (audit). Do NOT apply tilts. The `get_assessment` prompt carries the active view (basis_statement + relevant tilts) so the assessment addresses alignment in prose — that is this skill's primary alignment surface; the §7 inline flags are additive. Route every §7 token through `render_view_conflict()` per `_parallax/house-view/render_helpers.md`.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- `get_assessment` is async (30–90 s) and LLM-backed; its section carries its own contextual AI disclosure in addition to `parallax-conventions.md §9.2`.
- Technical Stance always renders: on `get_technical_analysis` failure use the Momentum factor proxy with the documented prefix.
- A `lang=` value other than `en` makes Step 7 mandatory (conventions §15).

Thorough single-position analysis for fund managers using Parallax MCP tools.

## Usage

```
/parallax-deep-dive AAPL.O
/parallax-deep-dive MSFT.O "Is the AI capex cycle sustainable?"
/parallax-deep-dive MSFT.O "Is the AI capex cycle sustainable?" lang=zh-HK register=retail
```

Accepts RIC format. For plain tickers, resolve per conventions §1. The free-text question stays the second positional argument; keyword args: `lang=<code>` (`en` default; `zh-CN`, `zh-TW`, `zh-HK`, `th`) and optional `register=retail` (passed only when translation is requested; absent means institutional register).

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–4) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: symbol; optional question; `lang=`; `register=`.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture tilt vector, excludes and `basis_statement` for (a) the Step 4 assessment prompt and (b) the §7.1/§7.2/§7.3 flags in Step 5. Do NOT apply tilts.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name` (seven-key loader; `branding["voice"]` raises `KeyError` by design).

### Step 1 — Resolve inputs

`call-tool` `get_company_info` with the symbol; if a plain ticker was given, resolve per conventions §1 with the `.HK`/numeric ambiguity cross-check.

### Step 2 — Fetch (parallel batches)

**Batch A** — `call-tool` all of the following together:

| Tool | Parameters | Notes |
|---|---|---|
| `get_peer_snapshot` | `symbol` | Factor scores + peer ranking |
| `get_financials` | `symbol`, `statement="summary"` | Revenue/income narrative |
| `get_financials` | `symbol`, `statement="ratios"`, `periods` as int 1 (latest period only, non-default — conventions §0.2) | Key ratios: margins, ROE, P/E |
| `get_score_analysis` | `symbol` | 52-week factor trend (server default) |
| `get_technical_analysis` | `symbol` | Trend, momentum, support/resistance |
| `get_stock_outlook` | `symbol`, `aspect="analyst_targets"` | Price targets |
| `get_stock_outlook` | `symbol`, `aspect="recommendations"` | Buy/hold/sell |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` | Risk/return vs peers |
| `get_stock_outlook` | `symbol`, `aspect="dividends"`, `limit` as int 8 (non-default; default is 20 — conventions §0.2) | Dividend history |
| `get_news_synthesis` | `symbol` | Async — never blocks output (§5) |

**Batch B** — after Step 1: `list_macro_countries`; relevant markets per conventions §6 (home + revenue geographies + commodity/supply chain), cap at 3; `macro_analyst` with `component="tactical"` per covered market.

### Step 3 — Verify

- Identity cross-check per conventions §2 (`get_peer_snapshot.target_company` vs `get_company_info.name` after normalization; `get_score_analysis` `data[0].symbol` vs the requested RIC). On divergence, warn and treat `get_company_info` as truth.
- Outlook coverage per conventions §4; failed or empty calls per §0.1 retry classification then §4. No gate is rendered, so §4.0 does not apply.

### Step 4 — Compute

No deterministic helper. The computed conditions are the house-view flags (§7.3 tension: `total_score ≥ 7` AND sector tilt ≤ −1; §7.2 peer-suggest conflict) evaluated exactly as `loader.md` states.

Then `call-tool` `get_assessment` (async, after Batches A and B) with a prompt carrying **all** findings — factor scores, score trends, key ratios, technical stance, macro context, dividend profile, risk/return vs peers, the user's question if any — AND the active view when present (basis_statement + tilts on this stock's sector/region/themes).

**When a view is active the assessor MUST end with three bullet lists**, not a free-form alignment paragraph: (1) tilts that support this position, one line each; (2) tilts that contradict it, one line each; (3) active tilts NOT incorporated, with the reason in one clause each. This decomposition is mandatory (MAS FEAT P13/14, SR 11-7 traceability — the assessor's influence on a CIO decision must be auditable from the prose). Prose without the three lists → re-run with a stricter prompt before rendering.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble and Branding Header per loader.md §5.1 and integration-pattern.md §5; §7 flags via `render_view_conflict()`; Assessment section header with its italic AI-disclosure parenthetical verbatim; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6. Apply §4 fallbacks rather than omitting a section silently.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/deepdive.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill deep-dive < "$DRAFT"; rm -f "$DRAFT"
```

The entire final English message is that command's stdout, or the sole input to Step 7. The stderr `[render-gate] WARN:` line is diagnostics: never include or translate it. If `run-shell` is absent, apply conventions §14.3 (render-gate row).

### Step 7 — Translate (conditional)

Only when `lang=` is present and not `en`. Translate per `parallax-conventions.md` §15 (routing block §15.2, failure footers §15.3, disclaimer boundary check §15.4). Skill-specific: the body is the gated Step 6 stdout including the audit entry and disclaimer; the Assessment section's italic AI-disclosure parenthetical is in translation scope — translate it, never drop it; pass `register: retail` only when `register=retail` was supplied.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Step 0 + low-confidence warnings if any). Per loader.md §5.1, the load preamble goes "at the very top" — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view active): `**<client_name>** deep dive`. Logo handling per integration-pattern.md §5: empty path → text line only; URL → embed `![<client_name>](<url>)`; absolute local path (starts with `/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Company Overview** (3 sentences)
- **Macro Environment** (regime context for relevant markets, factor implications)
- **Factor Profile** (table: each factor score with peer rank + 52-week trend direction)
  - *If view active:* check §7.3 tension condition (`total_score >= 7.0 AND view.tilts.sectors[stock_sector] <= -1`). If true, render banner via `render_view_conflict(kind="score_tension", ...)` directly below the factor table.
- **House View Note** (only if view active and stock conflicts with view) — render via `render_view_conflict(kind="blanket", ...)` per loader.md §7.1. Rendered HERE — immediately after Factor Profile — so the view lens appears before the rest of the analysis. Not at the bottom.
- **Financial Highlights** (key ratios, trends)
- **Dividend Profile** (yield, payout ratio, consistency — or "Not a dividend payer")
- **Risk/Return Profile** (volatility, Sharpe context vs peers)
  - *If view active AND `get_peer_snapshot.suggestion` returned a peer:* check §7.2 condition (peer's sector tilt ≤ -1 in view, or peer ticker on excludes). If true, render inline token via `render_view_conflict(kind="peer_suggest", ...)` under the Risk/Return section. Flag, do not filter — the peer stays in the table.
- **Technical Stance** (trend, key levels, momentum)
- **News Catalyst Watch** (material items only)
- **Assessment** *(AI-generated — Perplexity deep-research synthesis)* — includes macro + trend data; if view active, MUST end with the three-bullet tilt decomposition per Batch C contract. This is deep-dive's primary alignment surface. Render the section header with the italic parenthetical verbatim — it's the contextual-proximity AI disclosure per HKMA/SFC Nov 2024 Circular; the document-level banner (§5 rule 6) is not sufficient for the Perplexity-backed non-deterministic content in this specific section.
- **Risk Factors** (what could go wrong)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

Append audit log entry per loader.md §6.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. (The Assessment section already carries its own contextual-proximity AI disclosure per HKMA/SFC Nov 2024 Circular; the document-level §9.2 banner is rendered here in addition, covering the synthesis across all sections.)

If active view: use the view-aware disclaimer per loader.md §5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- `get_technical_analysis` unavailable: Technical Stance renders from the Momentum factor proxy with the prefix `Technical analysis unavailable — Momentum factor proxy:`; the lens never disappears.
- `get_assessment` timeout or missing the three-list decomposition under an active view: re-run once with a stricter prompt; if still absent, render the Assessment section as `Analysis pending — service temporarily unavailable` (conventions §4 async rule); never substitute model prose for the assessor's decomposition.
- News or macro pending: placeholders per conventions §5 / §6; output is not blocked.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked unavailable with its reason; first line is the House View Preamble, the Branding Header, or `## Company Overview`.
- When a view is active: the `view_status` banner appears verbatim; the Assessment ends with the three tilt lists.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; the Assessment header carries its italic AI-disclosure parenthetical.
- Audit log entry appended per loader.md §6 (every consume event, including the no-view case).
- Translation (if requested) completed per §15, or the §15.3 footer explains why not.
