---
name: parallax-credit-lens
description: "Credit risk assessment for publicly traded companies: leverage, coverage, liquidity, solvency (Palepu), Altman Z-score, and credit health signals vs. peer medians. Symbol in RIC format (AAPL.O, JPM.N). NOT for portfolio credit risk (use /parallax-scenario-analysis), not for private companies (requires document ingestion; not covered), not for forensic earnings-quality screening (use /parallax-earnings-quality), not for single-stock fundamental analysis (use /parallax-deep-dive)."
---

<!-- white-label: integration-pattern.md -->

# Credit Lens

## When not to use

- Private company credit analysis (requires document ingestion) → not covered; this skill needs a publicly traded issuer
- Portfolio credit concentration → use /parallax-scenario-analysis
- Single stock fundamental analysis → use /parallax-deep-dive
- Forensic earnings-quality screen → use /parallax-earnings-quality

## Gotchas

- Expected Parallax spend: ~10 tokens: Batch A 4 (three statements + peer snapshot), Batch B 6 (Palepu 5, score analysis 1; telemetry is free).
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §3 parallel execution, §4 / §4.0 fallbacks, §11 verdict sensitivity, §14 host primitives.
- `credit_lens_logic.py` is the pure arithmetic layer: every flag, the Altman Z-score and zone, the Quality-change flag and the overall traffic-light are computed there, never in prose. No MCP calls or file writes go in it. `assemble_report()` is a test-only reference renderer: it omits §9.1 and §9.2 and must not produce client-facing output.
- The published cutoffs in Step 4 mirror the module's constants (`ABSOLUTE_THRESHOLDS`, the Altman zone function, `flag_quality_change`); `tests/test_credit_lens.py` pins the two in agreement. Edit the module first, then the table.
- `get_financial_analysis` is async (2–5 min) and supplies BOTH the solvency (§3) and liquidity (§3a) narratives — one call, two sections; if it fails, both are marked unavailable while the quantitative Liquidity row (from `ratios`) stands.
- Quality factor is a credit-health proxy: a deteriorating Quality score is an early warning of credit stress.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).
- Not a house-view consumer: no loader step, no audit row.

Credit risk assessment for publicly traded companies using Parallax MCP tools.

## Usage

```
/parallax-credit-lens AAPL.O
/parallax-credit-lens JPM.N
/parallax-credit-lens 0001.HK "Hong Kong banking"
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1).

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Steps 1–2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: symbol; optional context text.
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name` (seven-key loader; `branding["voice"]` raises `KeyError` by design).

### Step 1 — Resolve inputs

`run-shell` `validate_ric()` in `credit_lens_logic.py` on the symbol. A plain ticker (AAPL) is resolved to RIC form per conventions §1 (→ AAPL.O) and re-validated. Then `call-tool` `get_company_info` for the identity oracle and market cap.

### Step 2 — Fetch (parallel batches)

**Batch A — core financials (4 tokens).** `call-tool` all four together:

```
get_financials(symbol=<RIC>, statement="balance_sheet")   # Total debt, equity, total assets, working capital, retained earnings
get_financials(symbol=<RIC>, statement="cash_flow")       # Operating CF, Capex, FCF
get_financials(symbol=<RIC>, statement="ratios")          # D/E, D/EBITDA, Interest Cov, margins, peer_median / peer_p75
get_peer_snapshot(symbol=<RIC>)                           # peer medians, factor scores
```

**Batch B — solvency, trend, macro (6 tokens, async).** `call-tool` all three together; `get_financial_analysis` never blocks the rest:

```
get_financial_analysis(symbol=<RIC>)   # Palepu solvency AND liquidity read (async)
get_score_analysis(symbol=<RIC>)       # Quality score 52-week trajectory
get_telemetry()                        # Market regime tag (no symbol parameter)
```

### Step 3 — Verify

- Identity per conventions §2: `get_peer_snapshot.target_company` vs `get_company_info.name`; `get_score_analysis` `data[0].symbol` vs the RIC.
- Input completeness for the helper: zero `total_assets` or `total_liabilities`, or a non-finite value, makes the Altman leg UNAVAILABLE (the module raises; do not substitute zero). A missing `peer_median`/`peer_p75` pair on a peer-relative-only metric makes that row UNAVAILABLE, never GREEN.
- The traffic-light is gate-shaped for its legs (conventions §4.0): an unjudgeable leg is UNAVAILABLE and excluded from the vote; the coverage clause in the header states it.

### Step 4 — Compute

Zero tool calls. `run-shell` `credit_lens_logic.py` for every number: `flag_metric(value, peer_median, peer_p75, metric_key)` per dashboard row (peer-relative and absolute, more conservative wins); `compute_altman_z(AltmanInputs(...))` → score, variant (`Z`, or `Z'` on book equity when market cap is absent) and zone; `quality_change_pts(current, prior)` → `flag_quality_change(...)`; `dashboard_rows(report)`; `build_header(report)` (and `finalize_verdict(report)` when `report.overall_flag` is needed downstream). → Load `references/flagging-rules.md` before building the report: it carries the `metric_key` registry, the peer-p75 direction rule, the Altman fallbacks, and the double-counting traps.

**Published cutoffs** (mirrors of the module constants; the module applies them, this table only documents them for §11 sensitivity lines):

| Leg | Amber | Red |
|---|---|---|
| Debt/EBITDA | > 3.5x | > 5.0x |
| Interest Coverage | < 3.0x | < 1.5x |
| Current Ratio | < 1.2x | < 1.0x |
| Altman Z (public-company variant, Altman 1968) | Grey zone 1.81–2.99 | Distress zone < 1.81 (Safe > 2.99) |
| Quality score change, 52 weeks, 0–10 scale | ≤ −0.5 pts | ≤ −1.5 pts |

Peer-relative rule for every metric: better than `peer_median` → GREEN; between median and the adverse `peer_p75` → AMBER; worse than `peer_p75` → RED. Overall: majority colour wins; ties go to the more conservative colour; UNAVAILABLE legs do not vote.

### Step 5 — Compose

Fill **Output Format** below in order: header via `build_header`, dashboard via `dashboard_rows`, §11 verdict-sensitivity line for the Altman leg only, Palepu narratives, Key Flags naming every unjudged leg; Branding Header per integration-pattern.md §5; About This Report per §7 with the currency line; `parallax-conventions.md §9.2` disclosure; standard disclaimer `parallax-conventions.md §9.1`.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/creditlens.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill credit-lens < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3: the render-gate row for the gate, and the gate-shaped-helper row for the flags — every leg is UNVERIFIED and the skill says so up front; never compute a flag in prose.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is the `## Credit Risk Assessment: …` header, or the Branding Header when active. Structure output in markdown with the following sections:

### 1. **Header** (1 line)
```
## Credit Risk Assessment: [Company] ([RIC]) | Traffic-Light: 🟢/🟡/🔴 | Judged: N of M metrics
```

Emit this with `build_header(report)` rather than by copying the template. The `| Judged: N of M metrics` clause is appended only when a leg is unjudged, and on a routine run several are — so a hand-copied header without it understates the gap on exactly the runs that need it stated.
Overall traffic-light determined by: count of RED flags (→ Red), count of AMBER flags (→ Amber), count of GREEN (→ Green). Majority color wins. If two or more colors tie for the highest count, render the most conservative tied color (Red > Amber > Green) — e.g., a 2-2-2 split renders Red. Compute via `overall_traffic_light(flags)`, which also drops UNAVAILABLE legs from the count and returns UNAVAILABLE when every leg is missing.

**State the coverage whenever any leg is UNAVAILABLE.** Dropping those legs is right for the vote but silent in the header, so a 🟢 can rest on two judged metrics out of six and still read as a full clean bill.

**Call `finalize_verdict(report)` rather than assigning `overall_flag` yourself.** It sets the verdict from `report_flags(report)` — every `metric_rows` flag plus `altman_flag` plus `quality_flag` — and `build_header()` counts that same list, so the verdict and the `| Judged: N of M metrics` count cannot describe different metric sets. Assigning the flag by hand reintroduces exactly that divergence. Populate `quality_flag` and `altman_flag` on the report; they vote, and a leg you leave at its default counts as unjudged.

List which metrics went unjudged, and why, in Key Flags.

This is the normal case, not an edge case: seven of the ten registered keys carry no absolute band, and the `ratios` response supplies peer percentiles for only five metrics, so the five with neither are unjudged on a routine run. Never present a majority verdict drawn from a minority of the metrics without saying so.

### 2. **Metrics Dashboard** (table)
```
| Category      | Signal | Metric Value | Peer Median | Interpretation |
|---------------|--------|--------------|-------------|-----------------|
| Leverage      | 🔴 RED  | D/E 2.1x     | Peer 1.2x   | 75% above peer |
| Leverage      | 🟡 AMBER| D/EBITDA 3.9x | Peer 2.8x  | Above peer |
| Leverage      | ➖ UNAVAILABLE | —     | —           | No peer data and no absolute band |
| Coverage      | 🟢 GREEN| Int Cov 5.2x | Peer 3.1x   | Top quartile |
| Coverage      | ➖ UNAVAILABLE | —     | —           | No peer data and no absolute band |
| Liquidity     | 🟡 AMBER| Curr Ratio 1.3x | Peer 1.8x | Below median |
| Liquidity     | ➖ UNAVAILABLE | —     | —           | No peer data and no absolute band |
| Profitability | 🟢 GREEN| EBITDA Margin 28% | Peer 22% | Above peer |
| Profitability | ➖ UNAVAILABLE | —     | —           | No peer data and no absolute band |
| Profitability | ➖ UNAVAILABLE | —     | —           | No peer data and no absolute band |
| Altman Z      | 🟡 AMBER| Z = 2.1      | —           | Grey Zone |
| Quality Trend | 🔴 RED  | –1.8 pts (52w) | —         | Deteriorating |
```

Twelve rows: ten registered metrics plus the two module-owned legs. **Category repeats** — it is a grouping label, not the row identity. Five rows read `➖ UNAVAILABLE` on a routine run because those metrics carry no absolute band and `ratios` returns no peer pair for them; that is the normal shape, not a failure.

**Build the table with `dashboard_rows(report)`, not from `metric_rows` directly.** It returns your metric rows plus the Altman and Quality rows, which it renders from `altman_flag` / `quality_flag`. Those two are legs in their own right: supplying them as rows as well makes each vote twice, and doubling two legs flips real verdicts — three RED metrics against two GREEN is RED, but with both GREEN legs doubled it becomes 3 RED against 4 GREEN and renders GREEN.

Every `MetricRow` you build needs `metric_key` set to the registry key it was flagged with. `report_flags()` identifies a leg by that key, not by its display label, and raises on a missing key, an unregistered key, a reserved key, or the same key twice. Labels are free text; the key is the identity.

### 2a. **Verdict sensitivity** (one line)
State the Altman Z-score's nearest band boundary (2.99 Safe/Grey or 1.81 Grey/Distress) and the arithmetic flip condition, per `parallax-conventions.md` §11. Example: "Altman Z = 2.85 is within the Grey Zone, 0.14 below the 2.99 Safe threshold; a Z rise above 2.99 would move this leg to Safe." Applies only to the Altman Z band — the overall traffic-light header is a multi-metric majority vote, not a single published numeric cutoff, and is out of scope for this line.

### 3. **Solvency Assessment** (narrative)
Output the Palepu solvency section from `get_financial_analysis`. If unavailable, note: `[Solvency assessment unavailable — tool error]`.

### 3a. **Liquidity Assessment** (narrative)
Output the Palepu liquidity section from the same `get_financial_analysis` response. This explains *why* the Liquidity row in the Metrics Dashboard reads as it does — working-capital cycle, cash conversion, near-term obligations — and is not a restatement of the current/quick ratio. Do not omit it because the ratio already appears above. If unavailable, note: `[Liquidity assessment unavailable — tool error]`.

### 4. **Key Flags** (bulleted list)
List every RED and AMBER flag with one-line explanation:
- 🔴 RED: Debt/EBITDA 5.2x exceeds peer 75th percentile (3.8x) and absolute threshold (5.0x)
- 🟡 AMBER: Quality score down 1.4 pts over 52 weeks — monitor for further deterioration
- 🔴 RED: Interest Coverage 2.1x below absolute threshold (3.0x); limited debt service cushion

### 5. **Quality Trend** (one sentence)
[Quality score 52-week trajectory + interpretation from `get_score_analysis`]
Example: "Quality score deteriorated 1.4 points over the past 52 weeks, signaling a potential credit health decline."

### 6. **Macro Context** (one sentence)
[Market regime from `get_telemetry` + one sentence on credit implication]
Example: "Current market regime is recessionary — a challenging environment for credit quality; elevated default risk across all sectors."

### 7. **Branding Header** (only if `white_label_active` AND `client_name != ""`)
Single line at the very top of the rendered output: `**<client_name>** credit lens`. Logo handling per integration-pattern.md §5.

### 8. **About This Report** (always present)
One line stating branding state per integration-pattern.md §7, plus the unconditional §7 currency line: `Currency: figures as reported by source data; no base-currency conversion applied.` If a logo was skipped, append `Logo on file: <basename>` as a further About This Report line.

### 9. **Footer**

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.


## Failure modes

- Symbol not found or not RIC-resolvable: stop with the conventions §1 message; suggest checking the exchange suffix.
- `get_financial_analysis` fails or times out: continue; mark **both** §3 `[Solvency assessment unavailable — tool error]` and §3a `[Liquidity assessment unavailable — tool error]`; the Liquidity dashboard row (from `ratios`) is unaffected.
- `report_flags()` raises (missing, unregistered, reserved or duplicate `metric_key`): a construction error in the row list — fix the rows and re-render; never catch and continue.
- Peer pair missing or inverted for a metric: absolute rule only where one exists, else UNAVAILABLE; say so in Key Flags.
- Market cap absent: Z' on book equity with the substitution stated; no book equity either → Altman leg UNAVAILABLE and no §2a line.
- Host lacks `run-shell`: every flag leg UNVERIFIED (conventions §14.3); the skill states this before any table.

## Done when

- Header emitted by `build_header` with the `Judged: N of M` clause whenever any leg is unjudged; dashboard has twelve rows from `dashboard_rows`; first line is the header or the Branding Header.
- Every RED/AMBER flag and every UNAVAILABLE leg is named in Key Flags with its reason.
- §2a sensitivity line present for the Altman leg (or explicitly skipped when the leg is unavailable).
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure, the §9.1 disclaimer, and the About This Report currency line are present.
- Expected spend stated (Gotchas).

## Callouts (interpretation caveats)

- **Quality score is a credit proxy**: A deteriorating Quality score (a 52-week change of -1.5 pts or worse on the 0-10 scale) is an early warning of credit stress and should be flagged as RED even if other metrics are healthy.
- **Altman Z thresholds shift by industry**: Manufacturing thresholds may differ from retail/financial. The fixed thresholds are generic — note industry caveats in output if appropriate.
- **Peer comparisons assume comparable size/structure**: A mega-cap's peer medians may not be relevant to an analyst evaluating a small-cap. Call this out if significant size mismatch is detected.
- **Palepu solvency assessment includes accruals quality**: High accruals (earnings not backed by cash) is a red flag independent of traditional credit metrics.
