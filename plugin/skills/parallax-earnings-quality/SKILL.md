---
name: parallax-earnings-quality
description: "Forensic earnings quality analysis: revenue recognition patterns, accruals, quality sub-scores, manipulation risk, and hidden risk detection via Parallax MCP tools. Symbol in RIC format. NOT for general stock analysis (use /parallax-deep-dive), not for full due diligence (use /parallax-due-diligence), not for a quick stock check (use /parallax-should-i-buy), not for credit-risk scoring (use /parallax-credit-lens)."
---

<!-- white-label: integration-pattern.md -->

# Earnings Quality Analysis

## When not to use

- General stock analysis → use /parallax-deep-dive
- Full due diligence → use /parallax-due-diligence
- Quick stock check → use /parallax-should-i-buy
- Credit / solvency scoring → use /parallax-credit-lens

## Gotchas

- Expected Parallax spend: ~24 tokens (`_parallax/token-costs.md`): Palepu 5, assessment 10, news 5, plus the 1-token calls.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §3 parallel execution, §4 fallbacks, §14 host primitives.
- `get_financial_analysis` (Palepu) is async ~2–5 min and is the core of the forensic read; compose from the instant tools while it resolves (conventions §5).
- A quality score of 10 does not mean no risk — read the sub-components. Cross-reference news for context on every red flag. Output is actionable risk flags, not a full financial review.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Not a house-view consumer: no loader step, no §7 surface, no audit row.

## Usage

```
/parallax-earnings-quality AAPL.O
/parallax-earnings-quality 7203.T "concerned about revenue recognition"
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–4) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: symbol; optional concern text.
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name` (seven-key loader; `branding["voice"]` raises `KeyError` by design).

### Step 1 — Resolve inputs

`call-tool` `get_company_info` with the RIC (plain ticker → conventions §1).

### Step 2 — Fetch (parallel batches)

**Batch A** — `call-tool` all together:

| Tool | Parameters | Notes |
|---|---|---|
| `get_score_analysis` | `symbol` | Quality score trajectory (default 52-week lookback) |
| `get_financials` | `symbol`, `statement="income"` | Revenue/margin trends (default 4 periods) |
| `get_financials` | `symbol`, `statement="cash_flow"` | Cash conversion (default 4 periods) |
| `get_financials` | `symbol`, `statement="ratios"` | Accrual ratios |
| `get_financial_analysis` | `symbol` | Async ~2–5 min — Palepu forensic analysis |
| `get_news_synthesis` | `symbol` | Async — accounting news, auditor changes |

### Step 3 — Verify

- Identity: `get_score_analysis` `data[0].symbol` against the requested RIC (conventions §2); `get_company_info.name` is the oracle for the narrative.
- Failed or empty calls: §0.1 retry classification, then §4. The traffic light is a display classification of Parallax's own quality data, not a gate on the name; §4.0 does not apply, but a Risk Summary cannot be rendered without the Palepu result — state `pending` rather than inventing a colour.

### Step 4 — Compute

No deterministic helper. Then `call-tool` `get_assessment` (async, after Batch A) with a prompt on earnings-quality concerns, revenue recognition, accrual anomalies, cash-flow-vs-earnings divergence, and the operator's stated concern, feeding in every Batch A finding.

### Step 5 — Compose

Fill **Output Format** below in order; Branding Header per integration-pattern.md §5; `parallax-conventions.md §9.2` disclosure; standard disclaimer `parallax-conventions.md §9.1`.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/earnq.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill earnings-quality < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.

## Output Format

- **Risk Summary** (red/yellow/green traffic light for overall earnings quality)
- **Quality Score Trend** (52-week trajectory with inflection points flagged)
- **Forensic Findings** (from Palepu analysis — accruals, revenue quality, cash conversion)
- **Red Flags** (specific items that warrant investigation)
- **News Context** (any accounting-related developments)
- **AI Assessment** (synthesized risk opinion)
- **Recommended Actions** (what to monitor, what warrants deeper investigation)
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** earnings quality review`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- `get_financial_analysis` pending after the async window: Forensic Findings and the Risk Summary colour render `Analysis pending — service temporarily unavailable`; Quality Score Trend and News Context still render.
- `get_assessment` timeout: AI Assessment renders the §4 async placeholder; Red Flags are still listed from the Palepu and ratio data.
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- Every Output Format section rendered or marked pending/unavailable with its reason; first line is the Branding Header or `## Risk Summary`.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
