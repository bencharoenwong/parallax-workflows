---
name: parallax-ai-klarman
description: "Applies Seth Klarman's margin-of-safety framework (per 'Margin of Safety', 1991) to a single stock's current financials via Parallax. Four balance-sheet checks: net cash position, debt vs peers, FCF stability, valuation discount. Includes a distinctive 'no position warranted; cash is valid' output when nothing qualifies. Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format. NOT for portfolio-level health check (use /parallax-portfolio-checkup). Other lenses: /parallax-ai-buffett, /parallax-ai-greenblatt, /parallax-ai-soros, /parallax-ai-ptj. For all five profiles simultaneously use /parallax-ai-consensus."
---

<!-- white-label: integration-pattern.md -->

# Parallax AI Klarman Profile

## When not to use

- Bottom-up factor scoring → use /parallax-ai-buffett
- Mechanical formula screen → use /parallax-ai-greenblatt
- Top-down macro analysis → use /parallax-ai-soros
- Trend-following + macro overlay → use /parallax-ai-ptj
- Cross-profile consensus → use /parallax-ai-consensus
- Full due diligence → use /parallax-due-diligence
- Running backtests → use /backtest

## Gotchas

- Expected Parallax spend: ~5–7 tokens (`_parallax/token-costs.md`): three statements + peer snapshot + company info.
- JIT-load `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/klarman.md` — Step 0.
- Balance-sheet-first: `get_financials` balance_sheet AND cash_flow AND ratios, 4 periods each (one call returns 4 periods). Net cash from the balance sheet (cash − total debt), not from the ratios summary.
- The "no position warranted" output IS valid output — not a failure. Value threshold is intentionally loose (≥ 4) per Lev-Srivastava 2022 — do not tighten without re-anchoring.
- NEVER use first-person impersonation; always "Klarman-style". Disclaimer verbatim with "Seth Klarman" for [Investor].
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Applies Seth Klarman's margin-of-safety framework to a single stock's current balance sheet, cash flow, and peer-relative valuation.

## Usage

```
/parallax-ai-klarman AAPL.O
/parallax-ai-klarman BRKb.N
/parallax-ai-klarman 7203.T
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This dispatcher is generic — all differentiation lives in the profile spec; the contract is `_parallax/AI-profiles/profile-schema.md` §2.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/klarman.md`.
3. `discover-tools`: bind every tool in the profile's `tool_sequence` to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Resolve the RIC per conventions §1 (suffix table).

### Step 2 — Fetch (parallel batches)

`call-tool` together:

| Tool | Parameters | Purpose |
|---|---|---|
| `get_company_info` | `symbol` | Sector, market cap, for peer group selection |
| `get_peer_snapshot` | `symbol` | Factor sub-scores (Value used as backup check) |
| `get_financials` | `symbol`, `statement=balance_sheet` | Cash, total debt, equity (4 periods default) |
| `get_financials` | `symbol`, `statement=cash_flow` | FCF across 4 periods (default) |
| `get_financials` | `symbol`, `statement=ratios` | D/E, P/E, peer medians where available (4 periods default) |

Rely on the 4-period server default, or pass a typed integer at the call site (conventions §0.2).

### Step 3 — Verify

**Cross-validation gate (MANDATORY per spec §6.4).** `get_peer_snapshot.target_company` (no `name` field; peers are `comparison[].company`) against `get_company_info.name`; on mismatch refuse to render and emit:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot target_company: "<name_b>"
Cannot render Klarman-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

Fewer than 4 periods: compute on what is available (minimum 2) and flag the coverage loss; no peer median: absolute thresholds with the note; all four checks unavailable → `DATA_UNAVAILABLE`, never a false `no_match`.

### Step 4 — Compute

The four checks: **1 Net cash** — (cash − total debt) / market cap: PASS ≥ 0, PARTIAL ≥ −0.2, FAIL < −0.2. **2 Debt vs peers** — D/E ≤ peer median × 1.1 PASS, else FAIL (no peer median → absolute D/E < 1.0 with "Peer comparison unavailable"). **3 FCF stability** — positive FCF periods of 4: PASS ≥ 3, PARTIAL 2, FAIL ≤ 1. **4 Valuation discount** — P/E vs peer median (P/B fallback on negative earnings): PASS ≤ × 0.85, PARTIAL ≤ × 1.0, FAIL above. **Backup** — Parallax Value ≥ 4; below 4 flag "⚠️ Parallax Value sub-score suggests valuation may not be attractive even if peer-relative metrics pass". Verdict with N = PASS count: N ≥ 3 and Value ≥ 4 → `match`; N ≥ 3 and Value < 4 → `partial_match` (flag "strong balance sheet but absolute Parallax Value below backup threshold — intangibles-era calibration caveat applies"); N = 2 → `partial_match`; N ≤ 1 → `no_match`; N = 0 and Value < 4 → append *"No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance."*

### Step 5 — Compose (render through the output template)


```
Klarman-style profile applied to <ticker>

Source: Klarman, S. (1991). Margin of Safety: Risk-Averse Value Investing Strategies for the Thoughtful Investor.

Klarman's framework prioritizes survival over return: balance-sheet strength, downside protection via valuation discount, and willingness to hold cash when nothing qualifies.

| Check                        | Target                    | Actual              | Result  |
|------------------------------|---------------------------|---------------------|---------|
| Net cash position            | Net cash ratio ≥ 0        | <value>             | PASS/PARTIAL/FAIL |
| Debt vs peer median          | D/E ≤ peer median × 1.1   | <value> vs <peer>   | PASS/FAIL |
| FCF stability                | Positive ≥ 3 of 4 periods | <count> of 4        | PASS/PARTIAL/FAIL |
| Valuation discount           | P/E ≤ peer median × 0.85  | <value> vs <peer>   | PASS/PARTIAL/FAIL |

Parallax Value sub-score (backup check): <score> / 10

Profile fit: <match / partial_match / no_match> — <count> of 4 checks passed.

Verdict sensitivity: the verdict-relevant input nearest its cutoff is <check or Value backup> (<actual> vs <target>); state the arithmetic crossing that would change the pass count or Value backup status, and state the verdict change only when that crossing changes the overall match / partial / no-match tier.

[Optional: "No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance."]

Workflow derived from: Klarman, S. (1991). Margin of Safety.
Last anchor-tested: 2026-04-07 (BRKb.N, NVDA.O)
Tool sequence: get_company_info, get_peer_snapshot, get_financials(balance_sheet/cash_flow/ratios, 4 periods)
Token cost: ~5 tokens

---
This output is an AI-inferred interpretation of Seth Klarman's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Seth Klarman or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 6 — Render — Emit

**Steps 1–6 are silent.** Perform the ticker resolution, cross-validation, scoring, threshold logic, and verdict computation internally — none of that working appears in your reply. Your **entire visible response consists only of the rendered Step 6 template plus every required Output addition below**. The analytical template begins at the Header line `Klarman-style profile applied to <ticker>`. Before it, render only the leading white-label elements required by `integration-pattern.md` §5, in its prescribed order, including a URL logo and the conditional Branding Header when applicable. If no leading white-label element applies, the analytical Header is the absolute first output. The About This Report footer, AI-interaction disclosure, and standard disclaimer remain required parts of the visible response in the positions specified below. Do NOT add `**Step N**` labels, "Cross-validation passed", "All data verified", a "Let me…" preamble, or any other workflow narration.


## Output additions (white-label branding + §9.2 disclosure)

These additions apply to the rendered output ABOVE in addition to the persona-specific disclaimer shown in the output example. They are required regardless of view state.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top of the rendered output: `**<client_name>** Klarman-style profile`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. The persona-specific disclaimer in the output example characterizes the source of the framing; the §9.2 banner characterizes the LLM-generated synthesis itself.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Failure modes


If balance-sheet data is unavailable for 4 periods, compute the checks on whatever is available (minimum 2 periods) and flag the coverage loss. If peer-median data is unavailable, skip the debt-vs-peers check and note "Peer comparison unavailable — absolute thresholds applied." If all four checks fail due to missing data, return `DATA_UNAVAILABLE` rather than a false `no_match`.


## Done when

- The reply begins at the analytical Header (or the white-label header when active) and contains only the rendered template plus the Output additions; no workflow narration.
- The cross-validation gate passed, or the exact refusal message was emitted and nothing else rendered.
- The verdict line, the citation, the methodology footer with tool sequence and token cost, the persona disclaimer verbatim, `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
