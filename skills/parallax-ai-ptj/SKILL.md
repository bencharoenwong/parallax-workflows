---
name: parallax-ai-ptj
description: "Applies Paul Tudor Jones's trend-following + macro-overlay framework (per Schwager's 'Market Wizards', 1989) to evaluate single-stock technical setup, macroeconomic regime alignment, and volatility-driven risk/reward asymmetry. Evaluates ticker across three independent conviction channels (Technical, Macro, Volatility). Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format. NOT for bottom-up factor analysis (use /parallax-deep-dive), not for a macro read without a ticker (use /parallax-macro-outlook). Other lenses: /parallax-ai-buffett, /parallax-ai-greenblatt, /parallax-ai-klarman, /parallax-ai-soros. For all five profiles simultaneously use /parallax-ai-consensus."
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

- Expected Parallax spend: ~14–16 tokens with one macro market, ~20–25 with three (`_parallax/token-costs.md`).
- JIT-load `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/ptj.md` — Step 0.
- Single-ticker only — reject multiple tickers with a redirect to /parallax-ai-consensus. Channels T, M, V are evaluated independently; `match` needs all 3 flagged, `partial_match` 2.
- `get_technical_analysis` is async and may time out — Channel T falls back to the Momentum factor proxy. `macro_analyst` needs `list_macro_countries` first; cap 3 markets (home + up to 2 exposure markets).
- NEVER use first-person impersonation ("PTJ would buy") — always "PTJ-style lens identifies" or "Profile flags". Disclaimer verbatim with "Paul Tudor Jones" for [Investor].
- Cross-validation gate is NON-BYPASSABLE — a name mismatch between `get_company_info` and `get_peer_snapshot` halts rendering.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Trend-following + macro-overlay framework: technical momentum validation → macro regime check → volatility-based risk/reward asymmetry assessment.

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

**Batch A:** `call-tool` `list_macro_countries` and `get_company_info` together; from them pick the home market plus up to 2 exposure markets by sector (e.g. China or Taiwan for semiconductors, Saudi Arabia for energy), cap 3.

**Batch B (all together):** `get_technical_analysis` (trend direction, momentum, volatility regime, levels — Channel T); `macro_analyst(market=<home>, component="tactical")` (Channel M); `get_score_analysis` (52-week factor trends incl. the Momentum sub-trend — Channel T sub-signal); `get_stock_outlook(aspect="risk_return")` (upside %, downside %, risk score — Channel V); `get_peer_snapshot` (`target_company` for the gate; Momentum factor score — Channel V).

**Batch C (after B):** `macro_analyst(component="tactical")` for the exposure markets, together.

### Step 3 — Verify

Cross-validation gate per `profile-schema.md §2 Step 2`: `get_peer_snapshot.target_company` against `get_company_info.name`; on mismatch emit the standard error and halt:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot returned: "<name_b>"
Cannot render PTJ-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

Unavailable inputs mark their channel `UNAVAILABLE` (never `NOT_FLAGGED`) per Failure modes.

### Step 4 — Compute

Thresholds from `profiles/ptj.md`. **Channel T:** `FLAGGED` when trend ∈ {POSITIVE, STRONG_POSITIVE} AND momentum trend ↑; `PARTIAL` when exactly one sub-signal is positive; `NOT_FLAGGED` when trend ∈ {NEGATIVE, STRONG_NEGATIVE} or momentum ↓; technical timeout → proxy Momentum ≥ 6 AND trend ↑ with the note "Technical analysis unavailable — Channel T uses factor proxy". **Channel M:** `FLAGGED` when the home tactical view is risk-on OR an exposure market's themes name the sector; `PARTIAL` neutral or mixed; `NOT_FLAGGED` risk-off with no favourable exposure theme. **Channel V:** `FLAGGED` when analyst upside ≥ 15% AND Momentum ≥ 5; `PARTIAL` upside 8–15%, or Momentum ≥ 5 with upside < 8%; `NOT_FLAGGED` upside < 8% or Momentum < 5. **Verdict:** 3 `FLAGGED` → `match` (Grade A); 2 `FLAGGED` → `partial_match` (Grade B; 2 + 1 `PARTIAL` → B/C); 0–1 → `no_match` (Grade C/D). Grade: A = 3 flagged, B = 2, C = 1 or 2+ partial, D = 0.

### Step 5 — Compose (render through the output template)


```
PTJ-style profile applied to <ticker>

Source: Schwager, J. D. (1989). Market Wizards: Interviews with Top Traders.

Trend-following + macro-overlay framework: technical momentum validation → macro regime alignment → volatility-based asymmetry assessment.

Ticker exposure check (tri-channel):

  Channel T — Technical setup
    Trend direction: <POSITIVE / NEGATIVE / etc.>
    Momentum trend (52-week): <↑ / → / ↓>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED

  Channel M — Macro regime
    Home market: <market>
    Tactical view: <risk-on / risk-off / neutral>
    Sector alignment: <aligned / partial / misaligned>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED

  Channel V — Volatility and asymmetry
    Analyst upside to target: <X%>
    Momentum factor score: <score/10>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED

Profile fit: <match / partial_match / no_match>
  - match: all three channels flagged (tri-channel alignment)
  - partial_match: two channels flagged (two-signal alignment)
  - no_match: zero or one channel flagged (insufficient confluence; capital preservation)

Setup quality: <Grade A / B / C / D>

Workflow derived from: Schwager (1989); Covel (2004).
Last anchor-tested: 2026-04-07 (NVDA.O, JPM.N)
Tool sequence: list_macro_countries, get_company_info, get_technical_analysis, macro_analyst × N (N ≤ 3), get_score_analysis, get_stock_outlook, get_peer_snapshot
Token cost: ~20-25 tokens (3 macro markets) / ~14-16 tokens (1 macro market)

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
Evaluate Channel T using `get_peer_snapshot.Momentum` >= 6 AND `get_score_analysis.momentum_trend` = ↑. Note in output: "Channel T: Technical analysis unavailable — using factor proxy (Momentum score + trend direction)." Channel T maximum verdict remains FLAGGED/PARTIAL/NOT_FLAGGED based on proxy data.

**If `macro_analyst` fails for home market:**
Proceed with up to 2 exposure-market macro calls. If ≥1 succeeds, evaluate Channel M based on exposure markets. If all macro calls fail, Channel M is UNAVAILABLE (not NOT_FLAGGED). Maximum verdict becomes partial_match (single-channel + available channels).

**If `get_stock_outlook(risk_return)` fails:**
Channel V cannot be evaluated. Mark as UNAVAILABLE. Verdict maximum is partial_match if other channels succeed.

**If `get_peer_snapshot` fails (cross-validation blocking):**
Cannot complete cross-validation gate. Halt rendering with error message per Step 4.

**If all three channels return UNAVAILABLE:**
Halt rendering: "Insufficient data to evaluate PTJ-style framework. Service temporarily unavailable."


## Done when

- The reply begins at the analytical Header (or the white-label header when active) and contains only the rendered template plus the Output additions; no workflow narration.
- The cross-validation gate passed, or the exact refusal message was emitted and nothing else rendered.
- The verdict line, the citation, the methodology footer with tool sequence and token cost, the persona disclaimer verbatim, `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
