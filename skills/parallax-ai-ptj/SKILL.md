---
name: parallax-ai-ptj
description: "Applies Paul Tudor Jones's trend-following + macro-overlay framework (per Schwager's 'Market Wizards', 1989) to evaluate single-stock technical setup, macroeconomic regime alignment, and an analyst-upside/Momentum proxy. Evaluates a ticker across three related channels (Technical, Macro, and the legacy Volatility label); the last does not measure volatility. Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format. NOT for bottom-up factor analysis (use /parallax-deep-dive), not for a macro read without a ticker (use /parallax-macro-outlook). Other lenses: /parallax-ai-buffett, /parallax-ai-greenblatt, /parallax-ai-klarman, /parallax-ai-soros. For all five profiles simultaneously use /parallax-ai-consensus."
---

<!-- white-label: integration-pattern.md -->

# Parallax AI PTJ Profile

## When not to use

- Bottom-up factor scoring → use /parallax-ai-buffett
- Mechanical formula screen → use /parallax-ai-greenblatt
- Balance-sheet-first checks → use /parallax-ai-klarman
- Top-down regime themes and baskets → use /parallax-ai-soros
- Macro regime screening without ticker focus → use /parallax-macro-outlook
- Cross-profile consensus, or multiple tickers → use /parallax-ai-consensus

## Gotchas

- Preserve the requested RIC(s), each observation’s source as-of date and unavailable fields. Generation time is not a substitute for a missing data date. Any handoff carries this provenance; a prior rendered profile is not a fresh or independent observation.

- Expected Parallax spend: **5.30 + 5M credits**, M = selected tactical markets (1–3): **10.30 / 20.30 credits** for one / three markets. Base: info 0.05 + technical narrative 5 + score history 0.1 + analyst targets 0.05 + snapshot 0.1. Coverage is free; explicit tactical components never trigger overview reassembly. Extra successful identity-resolution reads add 0.05 per symbol (`_parallax/token-costs.md`).
- JIT-load `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/ptj.md` — Step 0.
- Single-ticker only — reject multiple tickers with a redirect to /parallax-ai-consensus. Channels T, M, V are evaluated separately but share inputs; `match` needs all 3 flagged, `partial_match` 2.
- `get_technical_analysis` is async and may time out — Channel T falls back to the Momentum factor proxy. `macro_analyst` needs `list_macro_countries` first; cap 3 markets (home + up to 2 exposure markets).
- NEVER use first-person impersonation ("PTJ would buy") — always "PTJ-style lens identifies" or "Profile flags". Disclaimer verbatim with "Paul Tudor Jones" for [Investor].
- Cross-validation gate is NON-BYPASSABLE — a name mismatch between `get_company_info` and `get_peer_snapshot` halts rendering.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Trend-following + macro-overlay framework: technical momentum validation → macro regime check → analyst-upside/Momentum proxy assessment (not measured volatility).

## Usage

```
/parallax-ai-ptj AAPL.O                    # single-ticker mode — tri-channel evaluation
/parallax-ai-ptj JPM.N                     # evaluate ticker for PTJ-style confluence
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This dispatcher is generic — all differentiation lives in the profile spec; the contract is `_parallax/AI-profiles/profile-schema.md` §2.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/ptj.md`.
3. `discover-tools`: bind every tool in the profile's `tool_sequence` to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Exactly one ticker; more → reject: "PTJ profile evaluates single stocks. Use /parallax-ai-consensus for multi-ticker comparison." Resolve the RIC per conventions §1.

### Step 2 — Fetch (parallel batches)

**Batch A:** `call-tool` `list_macro_countries` and `get_company_info` together; from them pick the home market plus up to 2 exposure markets by sector (e.g. China or Taiwan for semiconductors, Canada or Brazil for energy; every pick must be a `list_macro_countries` market), cap 3.

**Batch B (all together):** `get_score_analysis` (52-week factor trends incl. the Momentum sub-trend — Channel T sub-signal); `get_stock_outlook(aspect="analyst_targets")` (sell-side `current`/`high`/`low`/`mean`/`median` price targets, from which upside is computed — Channel V; `aspect="risk_return"` is a different endpoint returning trailing return/volatility, not an analyst target); `get_peer_snapshot` (`target_company` for the gate; Momentum factor score — Channel V).

**Batch B2 (after the Step 3 gate passes, all together):** `get_technical_analysis` (LLM-authored prose narrative on trend/momentum/volatility/levels, read qualitatively — Channel T; the tool returns no machine trend enum, only `executive_summary` and `technical_analysis.trend_analysis` free text); `macro_analyst(market=<home>, component="tactical")` (Channel M). These calls bill (5 credits each), so they never run in the same turn as `get_peer_snapshot` (conventions §3); a halted run makes neither call.

**Batch C (after B2):** `macro_analyst(component="tactical")` for the exposure markets, together.

### Step 3 — Verify

Cross-validation gate per `profile-schema.md §2 Step 2`: `get_peer_snapshot.target_company` against `get_company_info.data.name`; on mismatch emit the standard error and halt:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot returned: "<name_b>"
Cannot render PTJ-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

Unavailable inputs mark their channel `UNAVAILABLE` (never `NOT_FLAGGED`) per Failure modes.

### Step 4 — Compute

Thresholds come from `profiles/ptj.md`; preserve them. **Channel T:** evaluate the documented bullish-prose/upward-Momentum predicates. Both positive → `FLAGGED`; exactly one positive without an overlapping negative predicate → `PARTIAL`; a clearly negative case → `NOT_FLAGGED`. If the original positive/partial and bearish/down predicates conflict, render `UNAVAILABLE — ambiguous profile rules`; do not invent precedence. Technical timeout with Momentum ≥ 6 AND upward trend is the documented proxy and is capped at `PARTIAL`; if that proxy cannot be evaluated or does not qualify, the missing technical channel remains `UNAVAILABLE`. Label the proxy. **Channel M:** `FLAGGED` for the documented risk-on/sector-tailwind predicate, `PARTIAL` for neutral/mixed, `NOT_FLAGGED` for risk-off without favorable exposure; absent macro evidence → `UNAVAILABLE`. **Channel V — analyst-upside/Momentum proxy:** require finite analyst mean/current and Momentum, with current > 0. Compute upside `(mean − current) / current`. Apply existing predicates: `FLAGGED` upside ≥ 15% AND Momentum ≥ 5; `PARTIAL` upside 8–15% OR Momentum ≥ 5 with upside < 8%; `NOT_FLAGGED` upside < 8% OR Momentum < 5. Where predicates overlap (including the 15% boundary), render `UNAVAILABLE — ambiguous profile rules` rather than choosing a winner or retuning a threshold. Missing/invalid inputs also give `UNAVAILABLE`. This proxy does not measure volatility, downside distribution or risk/reward asymmetry; T and V share Momentum evidence. **Verdict:** any required channel `UNAVAILABLE` → final `skipped`, retaining available observations. With all channels evaluable: 3 `FLAGGED` → `match`; 2 → `partial_match`; 0–1 → `no_match`. Avoid a separate letter grade where its legacy rules conflict.

### Step 5 — Compose (render through the output template)


```
PTJ-style profile applied to <ticker>

Source: Schwager, J. D. (1989). Market Wizards: Interviews with Top Traders.

Trend-following + macro-overlay rubric: technical momentum, macro context, and an analyst-upside/Momentum proxy. Channels share inputs and are not independent confirmations.

Ticker exposure check (tri-channel):

  Channel T — Technical setup
    Trend direction: <bullish / bearish / mixed — qualitative read from get_technical_analysis's prose>
    Momentum trend (52-week): <↑ / → / ↓>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED / UNAVAILABLE

  Channel M — Macro regime
    Home market: <market>
    Tactical view: <risk-on / risk-off / neutral>
    Sector alignment: <aligned / partial / misaligned>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED / UNAVAILABLE

  Channel V — Analyst-upside/Momentum proxy
    Analyst upside to target: <X%>
    Momentum factor score: <score/10>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED / UNAVAILABLE

Profile fit: <match / partial_match / no_match / skipped>
  - match: all three channels flagged (tri-channel alignment)
  - partial_match: two channels flagged (two-signal alignment)
  - no_match: zero or one channel flagged (insufficient confluence; capital preservation)

Setup quality: <Grade A / B / C / D>

Workflow derived from: Schwager (1989); Covel (2004).
Last anchor-tested: 2026-04-07 (NVDA.O, JPM.N)
Tool sequence: list_macro_countries, get_company_info, get_score_analysis, get_stock_outlook, get_peer_snapshot, get_technical_analysis, macro_analyst × N (N ≤ 3)
Parallax credit estimate: 20.30 credits (3 macro markets) / 10.30 credits (1 macro market)

---
This output is an AI-inferred interpretation of Paul Tudor Jones's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Paul Tudor Jones or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 6 — Render — Emit

**Steps 1–5 are silent.** Perform the ticker resolution, cross-validation, scoring, threshold logic, and verdict computation internally — none of that working appears in your reply. Your **entire visible response consists only of the rendered Step 5 template plus every required Output addition below**. The analytical template begins at the Header line `PTJ-style profile applied to <ticker>`. Before it, render only the leading white-label elements required by `integration-pattern.md` §5, in its prescribed order, including a URL logo and the conditional Branding Header when applicable. If no leading white-label element applies, the analytical Header is the absolute first output. The About This Report footer, AI-interaction disclosure, and standard disclaimer remain required parts of the visible response in the positions specified below. Do NOT add `**Step N**` labels, "Cross-validation passed", "All data verified", a "Let me…" preamble, or any other workflow narration. If `run-shell` is unavailable nothing changes: this family has no gate script — the template is the gate.


## Output additions (white-label branding + §9.2 disclosure)

These additions apply to the rendered output ABOVE in addition to the persona-specific disclaimer shown in the output example. They are required regardless of view state.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top of the rendered output: `**<client_name>** PTJ-style profile`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. The persona-specific disclaimer in the output example characterizes the source of the framing; the §9.2 banner characterizes the LLM-generated synthesis itself.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Failure modes


**If `get_technical_analysis` times out (async tool):**
Evaluate Channel T using `get_peer_snapshot.Momentum` >= 6 AND `get_score_analysis.momentum_trend` = ↑. Note in output: "Channel T: Technical analysis unavailable — using factor proxy (Momentum score + trend direction)." A qualifying proxy is capped at PARTIAL per the profile spec. Missing or nonqualifying proxy evidence leaves T UNAVAILABLE; final fit is skipped when any required channel remains unavailable.

**If `macro_analyst` fails for home market:**
Proceed with up to 2 exposure-market macro calls. If ≥1 succeeds, evaluate Channel M based on exposure markets. If all macro calls fail, Channel M is UNAVAILABLE (not NOT_FLAGGED). Final verdict is skipped when required Channel M remains unavailable; retain the other observations.

**If `get_stock_outlook(analyst_targets)` fails, or succeeds with `data.status != "available"`, or null `mean`/`current`:**
Channel V cannot be evaluated. Mark as UNAVAILABLE (never NOT_FLAGGED). Final verdict is skipped; retain other channel observations without treating missing evidence as no_match.

**If `get_peer_snapshot` fails (cross-validation blocking):**
Cannot complete cross-validation gate. Halt rendering with error message per Step 4.

**If all three channels return UNAVAILABLE:**
Halt rendering: "Insufficient data to evaluate PTJ-style framework. Service temporarily unavailable."


## Done when

- The reply begins at the analytical Header (or the white-label header when active) and contains only the rendered template plus the Output additions; no workflow narration.
- The cross-validation gate passed, or the exact refusal message was emitted and nothing else rendered.
- The verdict line, the citation, the methodology footer with tool sequence and credit cost, the persona disclaimer verbatim, `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
