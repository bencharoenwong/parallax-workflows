---
name: parallax-due-diligence
description: "Full research analyst due diligence: all financial statements, Palepu framework, technicals, news, score trends, and full Parallax research report via Parallax MCP tools. Symbol in RIC format. NOT for quick checks (use /parallax-should-i-buy), not for position deep dives without Palepu (use /parallax-deep-dive), not for peer-set comparison only (use /parallax-peer-comparison), not for a client-branded rendering of the research report (use /parallax-white-label-stock-report), not for forensic earnings-quality screening alone (use /parallax-earnings-quality)."
---

<!-- white-label: integration-pattern.md -->

# Full Due Diligence

## When not to use

- Quick stock evaluation → use /parallax-should-i-buy
- Position deep dive (no Palepu) → use /parallax-deep-dive
- Peer comparison only → use /parallax-peer-comparison
- Forensic earnings-quality screen only → use /parallax-earnings-quality
- Client-forwardable deliverable → use /parallax-client-review (portfolio) or /parallax-white-label-stock-report (single name)

## Gotchas

- Expected Parallax spend: ~31 tokens (`_parallax/token-costs.md`): four financial statements, Palepu 5, full report 10 (paid), plus the 1-token calls. The most expensive single-stock workflow — serious research only.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4 fallbacks, §14 host primitives.
- JIT-load `_parallax/house-view/loader.md`; this is a single-stock consumer per §7: tilts are NOT applied to scores or to any prompt. Surface §7.1 (House View Note after Factor Score Trajectory) and §7.3 (tension banner) via `render_view_conflict()` per `_parallax/house-view/render_helpers.md`; §7.2 is N/A (this skill does not surface `get_peer_snapshot.suggestion`). Audit per §6 with `applied_reason` `"single-stock consumer (loader.md §7.1/§7.2/§7.3)"`.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- `get_financial_analysis` (Palepu) is async ~2–5 min; `get_stock_report` is async ~1–2 min and PAID. Begin composing from the instant tools while they resolve (conventions §5).
- No `audience=client_safe` mode: if invoked with it, render one line — "This skill produces an internal analyst working document and has no client-safe mode; for a client-facing deliverable use /parallax-client-review or /parallax-white-label-stock-report." — then proceed in internal_analyst mode.

Comprehensive analyst-grade due diligence using all available Parallax tools.

## Usage

```
/parallax-due-diligence AAPL.O
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: symbol; reject `audience=client_safe` with the Gotchas line.
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the load preamble, the sector tilt vector and excludes for §7.1/§7.3 in Step 5. Tilts are NOT applied. On §2 validation failure, run without the view and use the standard disclaimer.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name` (seven-key loader; `branding["voice"]` raises `KeyError` by design).

### Step 1 — Resolve inputs

`call-tool` `get_company_info` with the RIC; for a plain ticker resolve per conventions §1.

### Step 2 — Fetch (parallel batches)

**Batch A** — `call-tool` all together:

| Tool | Parameters | Notes |
|---|---|---|
| `get_financials` | `symbol`, `statement="income"` | Income statement (default 4 periods) |
| `get_financials` | `symbol`, `statement="balance_sheet"` | Balance sheet (default 4 periods) |
| `get_financials` | `symbol`, `statement="cash_flow"` | Cash flow (default 4 periods) |
| `get_financials` | `symbol`, `statement="ratios"` | Key ratios (default 4 periods) |
| `get_technical_analysis` | `symbol` | Trend, momentum, support/resistance |
| `get_score_analysis` | `symbol` | 52-week factor score trajectory (server default) |
| `get_news_synthesis` | `symbol` | Async — never blocks output |
| `get_financial_analysis` | `symbol` | Async ~2–5 min — Palepu framework |

**Batch B** — after Batch A: `ask-operator` to confirm the paid call, then `call-tool` `get_stock_report` (async ~1–2 min) for the full research report with PDF/HTML links. If `ask-operator` is unavailable on this host, apply conventions §14.3: render the question, stop, and treat the report section as not requested.

### Step 3 — Verify

- Identity cross-check per conventions §2: `get_score_analysis` `data[0].symbol` against the requested RIC; company name from `get_company_info` is the oracle for every narrative section.
- Failed or empty calls: §0.1 retry classification, then §4 display-section rule. No gate is rendered, so §4.0 does not apply.

### Step 4 — Compute

No deterministic helper. The computed condition is the §7.3 tension flag (`total_score ≥ 7` AND sector tilt ≤ −1), evaluated exactly as `loader.md` states.

### Step 5 — Compose

Fill **Output Format** below in order: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; §7.3 banner between the scores table and Factor Score Trajectory and §7.1 note after it, both via `render_view_conflict()`; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit entry per loader.md §6.1 (all required fields; `applied=false` with the canonical `applied_reason`).

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/duediligence.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill due-diligence < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row). This skill has no Step 7; it does not translate.

## Output Format

Analyst-grade research report. Precision over brevity. Include raw data tables.

- **Scope note** — internal analyst working document; not designed for client forwarding.
- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner + low-confidence warnings if any).
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at top of report: `**<client_name>** research report`. Logo: if `branding["logos"]["primary"]` is empty, render text line only; if URL, embed `![<client_name>](<url>)` above the line; if absolute local path (starts with `/` or `~`), skip embed and append `Logo on file: <basename>` to About This Report.
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
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

Note: `get_financial_analysis` (~2-5 min) and `get_stock_report` (~1-2 min, paid) are async. Begin assembling output from instant tools while async calls resolve.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- `get_financial_analysis` pending after the async window: the Palepu Framework section renders `Analysis pending — service temporarily unavailable` (conventions §4); the rest of the report stands.
- `get_stock_report` declined, pending or failed: the Parallax Research Report section states which, with no link; never fabricate a link.
- `get_technical_analysis` unavailable: Technical Stance renders from the Momentum factor proxy with the documented prefix.
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked unavailable with its reason; first line is the Scope note, the House View Preamble, or the Branding Header.
- When a view is active: the `view_status` banner appears verbatim; §7.1 note and (if triggered) §7.3 banner are present in their documented positions.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present.
- Audit log entry appended per loader.md §6 (every consume event, including the no-view case).
- Expected spend stated (Gotchas); the paid report call was operator-confirmed or explicitly not made.
