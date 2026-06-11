---
name: parallax-due-diligence
description: "Full research analyst due diligence: all financial statements, Palepu framework, technicals, news, score trends, and full Parallax research report via Parallax MCP tools. Symbol in RIC format. NOT for quick checks (use /parallax-should-i-buy), not for position deep dives without Palepu (use /parallax-deep-dive)."
---

<!-- white-label: integration-pattern.md -->

# Full Due Diligence

## When not to use

- Quick stock evaluation → use /parallax-should-i-buy
- Position deep dive (no Palepu) → use /parallax-deep-dive
- Peer comparison only → use /parallax-peer-comparison

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
- get_financial_analysis (Palepu) is async ~2-5 min
- get_stock_report is async ~1-2 min and is a PAID endpoint
- Wait for each async step before proceeding
- This is the most thorough and expensive workflow — use for serious research only
- JIT-load _parallax/house-view/loader.md and apply §7 (single-stock, read-only consumers) — due-diligence is a single-stock skill, so tilts are NOT applied to scores or to the assessment prompt. Workflow: §2 validation, §7.1 House View Note rendered AFTER the Factor Score Trajectory section (per render_helpers.md template via `render_view_conflict(kind="blanket", ...)`), §7.3 Score-vs-View Tension Banner inline at scores when primary stock total score ≥7 AND its sector tilt ≤-1, §6 audit log entry. §7.2 (peer-suggest token) is N/A here — due-diligence does not surface `get_peer_snapshot.suggestion`.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer.
- Pre-Render step loads white-label branding via `_parallax/white-label/loader.py` → `load_visual_branding()` (the 6-key visual subset wrapper). Voice/typography/etc. are structurally absent — `branding["voice"]` raises `KeyError`. Provenance state-to-text mapping and Branding Header semantics follow integration-pattern.md §5 + §7 — render per that table.

Comprehensive analyst-grade due diligence using all available Parallax tools.

## Usage

```
/parallax-due-diligence AAPL.O
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns.

### Pre-Workflow — Load Active House View

Per `_parallax/house-view/loader.md` §1 and §2: load and validate any active house view BEFORE running the workflow. If view present and validated:

- Capture the load preamble (banner from `view_status` helper, low-confidence warnings if any) for rendering at the very top of Output Format per §5.1.
- Capture the sector tilt vector and excludes — these inform the §7.1 House View Note and §7.3 tension banner after the analytical output is composed.
- Tilts are **NOT applied** to scores, the assessment prompt, or any ranking. Due-diligence is a single-stock skill per §7; the view surfaces as read-only conflict signals, not multipliers.

If no active view (or any §2 validation failure): run the workflow normally with the standard disclaimer.

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — All instant + async data calls (parallel)

Fire all simultaneously:

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | `symbol` | Company profile |
| `get_financials` | `symbol`, `statement="income"` | Income statement (default 4 periods) |
| `get_financials` | `symbol`, `statement="balance_sheet"` | Balance sheet (default 4 periods) |
| `get_financials` | `symbol`, `statement="cash_flow"` | Cash flow (default 4 periods) |
| `get_financials` | `symbol`, `statement="ratios"` | Key ratios (default 4 periods) |
| `get_technical_analysis` | `symbol` | Trend, momentum, support/resistance |
| `get_score_analysis` | `symbol` | 52-week factor score trajectory (server default) |
| `get_news_synthesis` | `symbol` | Async — don't block output |
| `get_financial_analysis` | `symbol` | Async ~2-5 min — Palepu framework |

### Batch B — Full report (after Batch A, user confirmation recommended)

Call `get_stock_report` for comprehensive Parallax research report with PDF/HTML links. This is a **PAID endpoint** (~1-2 min async).

### Post-Workflow — House View consumer obligations

If a view was loaded in Pre-Workflow:

1. From the company's sector (via `get_company_info`) and the captured tilt vector, determine whether a §7 conflict surfaces.
2. Compose §7.1 House View Note via `render_view_conflict(kind="blanket", ...)` — placed AFTER the Factor Score Trajectory section in Output Format. Do NOT reproduce the template inline; invoke the helper per `_parallax/house-view/render_helpers.md`.
3. If primary stock total score ≥ 7 AND its sector tilt ≤ -1, compose §7.3 Tension Banner via `render_view_conflict(kind="score_tension", ...)` — placed BETWEEN the scores table and the §7.1 note in Output Format.
4. Append the §6 audit log entry per loader.md §6.1 (all required fields: `schema_version`, `ts`, `view_id`, `version_id`, `skill`, `action`, `applied`, plus `query_summary` / `conflicts_count` / `output_summary_hash` when `action=="consume"`; and `applied_reason` whenever `applied=false` — for due-diligence the canonical reason string is `"single-stock consumer (loader.md §7.1/§7.2/§7.3)"`).

### Pre-Render — Load white-label branding

Before composing the Output Format, JIT-load `_parallax/white-label/integration-pattern.md` and call `load_visual_branding()` per §2. The loader returns exactly six keys: `client_name`, `colors`, `logos`, `fonts`, `source`, `error`. Set `white_label_active = is_white_label_active(branding)` and `client_name = branding.get("client_name", "")` for use in the Branding Header. See §4 (error states), §5 (substitution semantics), §7 (Provenance template). Any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

## Output Format

Analyst-grade research report. Precision over brevity. Include raw data tables.

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner + low-confidence warnings if any).
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at top of report: `**<client_name>** research report`. Logo: if `branding["logos"]["primary"]` is empty, render text line only; if URL, embed `![<client_name>](<url>)` above the line; if absolute local path (starts with `/` or `~`), skip embed and append `Logo on file: <basename>` to Provenance.
- **Company Overview** (business, sector, market cap, key thesis)
- **Income Statement Analysis** (4-year trends: revenue, margins, EPS)
- **Balance Sheet Analysis** (leverage, liquidity, asset quality)
- **Cash Flow Analysis** (FCF, capex, cash conversion)
- **Key Ratios** (valuation, profitability, efficiency — table format)
- **Palepu Framework** (profitability decomposition, accruals quality, solvency assessment)
- **Technical Stance** (trend, momentum, support/resistance, volume)
- **News Intelligence** (material developments only)
- **Score-vs-View Tension Banner** (only if view active AND total score ≥ 7 AND sector tilt ≤ -1) — inline between the scores table and the Factor Score Trajectory, via `render_view_conflict(kind="score_tension", ...)`.
- **Factor Score Trajectory** (52-week trend: which factors improving/declining)
- **House View Note** (only if view active) — placed AFTER Factor Score Trajectory per loader.md §7 rendering order, via `render_view_conflict(kind="blanket", ...)`.
- **Parallax Research Report** (link to PDF/HTML from get_stock_report)
- **Synthesis & Key Risks** (bull case, bear case, key uncertainties)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

Note: `get_financial_analysis` (~2-5 min) and `get_stock_report` (~1-2 min, paid) are async. Begin assembling output from instant tools while async calls resolve.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
