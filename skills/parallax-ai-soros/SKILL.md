---
name: parallax-ai-soros
description: "Applies George Soros's top-down reflexivity framework (per 'The Alchemy of Finance', 1987) to current Parallax data. Triggers: 'trade ideas based on current macro regime', 'regime-driven stock picks', 'reflexivity-lens stock ideas'. Two modes: basket mode surfaces regime themes and ranked exposure candidates (informational); single-ticker mode runs the same macro workflow and checks ticker exposure via dual channels (industry exposure AND telemetry basket theme). Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format. NOT for bottom-up factor analysis (use /parallax-deep-dive), not for theme screens without a persona lens (use /parallax-thematic-screen), not for a macro read without a persona lens (use /parallax-macro-outlook). Other lenses: /parallax-ai-buffett, /parallax-ai-greenblatt, /parallax-ai-klarman, /parallax-ai-ptj. For all five profiles simultaneously use /parallax-ai-consensus."
---

<!-- white-label: integration-pattern.md -->

# Parallax AI Soros Profile

## When not to use

- Bottom-up factor scoring → use /parallax-ai-buffett
- Mechanical formula screen → use /parallax-ai-greenblatt
- Balance-sheet-first checks → use /parallax-ai-klarman
- Trend-following + macro overlay on one ticker → use /parallax-ai-ptj
- Cross-profile consensus → use /parallax-ai-consensus
- Full macro outlook without a persona lens → use /parallax-macro-outlook
- Theme screen without a persona lens → use /parallax-thematic-screen
- Morning brief for a portfolio → use /parallax-morning-brief

## Gotchas

- Expected Parallax spend: ~25–30 tokens single-ticker, ~30–40 basket (`_parallax/token-costs.md`); `macro_analyst` is 5 per market, capped at 5 markets.
- JIT-load `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/soros.md` — Step 0.
- Two modes — basket (no ticker) and single-ticker dual-channel — share the macro workflow. The dual-channel logic is load-bearing: a single-channel flag is `partial_match`, never `match`.
- Channel B basket membership is best-effort name-matching against `divergences[*].basket_name`; per-ticker basket lookup is not a documented `get_telemetry` field.
- `build_stock_universe` is async and broad queries time out: thematic queries MUST be sector-scoped and size-bounded (good: "US energy exporters benefiting from dollar weakness").
- NEVER use first-person impersonation of Soros — always "Soros-style" or "reflexivity lens identifies". Disclaimer verbatim with "George Soros" for [Investor].
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Top-down reflexivity lens: regime identification → thematic exposure → ranked exposure candidates (informational) OR single-ticker dual-channel check.

## Usage

```
/parallax-ai-soros                         # basket mode — regime themes + ranked ideas
/parallax-ai-soros AAPL.O                  # single-ticker mode — dual-channel exposure check
/parallax-ai-soros --markets US,JP,EU      # basket mode with explicit market list
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This dispatcher is generic — all differentiation lives in the profile spec; the contract is `_parallax/AI-profiles/profile-schema.md` §2.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/soros.md`.
3. `discover-tools`: bind every tool in the profile's `tool_sequence` to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Mode: zero tickers → **basket mode**; exactly one → **single-ticker mode**; more → reject: "Soros profile takes zero or one ticker. Use /parallax-ai-consensus for multi-ticker." Single-ticker: resolve the RIC per conventions §1 and `call-tool` `get_company_info` (sector, industry). Markets: `--markets` if given, else US, JP, EU plus the top-2 EM by telemetry divergence (cap 5).

### Step 2 — Fetch (parallel batches)

**Macro workflow (both modes):** `call-tool` `list_macro_countries` and `get_telemetry` together; then `macro_analyst(component=tactical)` for each selected market together. Identify 1–3 regime themes where macro and telemetry agree on direction (e.g. "Fed cutting + dollar weakening → EM equities and commodities").

**Basket mode:** per theme, `build_stock_universe` with a sector-scoped thematic query (timeout → retry ONCE narrower; then skip the theme); cap each theme's candidates at the top 20 by `composite_score`; `get_peer_snapshot` for the top 3–5 per theme, all together.

**Single-ticker mode:** per theme, `build_stock_universe` with the theme's sector-scoped query (same retry rule); `get_peer_snapshot` on the ticker when it surfaces during universe resolution.

### Step 3 — Verify

Cross-validation gate per `profile-schema.md §2 Step 2` for every ticker surfaced: `target_company` (top level; no `name` field — peers are `comparison[].company`) against `get_company_info.name`; refuse to render on mismatch. `list_macro_countries` failure → derive markets from RIC-suffix defaults (conventions §6) and note degradation; `macro_analyst` failing for some markets → proceed with ≥ 2 successes; `get_telemetry` failure → Channel B is `UNAVAILABLE` (not `NOT_FLAGGED`).

### Step 4 — Compute

**Basket mode:** rank names within each theme by momentum + macro sensitivity → `trade_ideas`.

**Single-ticker mode — dual-channel exposure check.** **Channel A (industry), two independent sub-paths, either sufficient to FLAG:** A1 universe membership — the ticker appears in a theme's `build_stock_universe` result (timeout/empty → A1 `NOT_FLAGGED`, Channel A not yet resolved); A2 classification match — the ticker's sector/industry from `get_company_info` matches a theme's target sector (evaluable without the universe build). Channel A `FLAGGED` if A1 OR A2; `NOT_FLAGGED` only if both are negative. **Channel B (telemetry basket):** the ticker falls in a regime basket surfaced by `get_telemetry` → `FLAGGED` / `NOT_FLAGGED` / `UNAVAILABLE`. **Verdict:** both `FLAGGED` → `match`; exactly one `FLAGGED` (other `NOT_FLAGGED` or `UNAVAILABLE`) → `partial_match`; neither → `no_match`. `match` is NEVER reached when Channel B is `UNAVAILABLE`.

### Step 5 — Compose (render through the output template)


**Basket mode output:**

```
Soros-style regime themes and exposure candidates (informational)

Source: Soros, G. (1987). The Alchemy of Finance. | Drobny, S. (2006). Inside the House of Money.

Reflexivity framework: identify regime break or narrative-fundamentals divergence → surface exposed industries → the names with strongest thematic exposure.

Markets analyzed: <list>

## Theme 1: <name>
Macro thesis: <one paragraph — regime break or tactical opportunity>
Theme direction (analytical read): <positive / negative / rotation>
Currency/rate context: <brief>

Ranked exposure candidates (informational, per conventions §12 — not trade instructions):
| Rank | Ticker | Industry | Momentum | Rationale |
|------|--------|----------|----------|-----------|
| 1    | XXX.N  | ...      | 7.2      | ...       |
| ...  | ...    | ...      | ...      | ...       |

## Theme 2: <name>
[same structure]

Workflow derived from: Soros (1987); Drobny (2006).
Last anchor-tested: 2026-04-07 (NVDA.O, TSLA.O)
Tool sequence: list_macro_countries, macro_analyst × N, get_telemetry, build_stock_universe × N, get_peer_snapshot × M
Token cost: ~25-40 tokens

---
This output is an AI-inferred interpretation of George Soros's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by George Soros or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

**Single-ticker mode output:**

```
Soros-style profile applied to <ticker>

Source: Soros, G. (1987). The Alchemy of Finance.

Reflexivity framework: top-down regime identification → thematic exposure check. Single-ticker mode answers "is this stock in an industry and basket theme the current regime analysis flags?"

Current regime themes (1-3): <list with one-line theses>

Ticker exposure check (dual-channel):

  Channel A — Industry exposure
    <ticker>'s sector/industry: <sector>
    Industry appears in theme(s): <theme names or NONE>
    Status: FLAGGED / NOT FLAGGED

  Channel B — Telemetry basket theme
    Telemetry baskets surfaced: <list>
    <ticker> falls in basket(s): <basket names or NONE>
    Status: FLAGGED / NOT FLAGGED

Profile fit: <match / partial_match / no_match>
  - match: both channels flagged (genuine thematic exposure)
  - partial_match: one channel flagged (industry OR basket, not both)
  - no_match: neither channel flagged (Soros-style lens has no current view)

Workflow derived from: Soros (1987); Drobny (2006).
Last anchor-tested: 2026-04-07 (NVDA.O, TSLA.O)
Tool sequence: list_macro_countries, macro_analyst × N, get_company_info, get_telemetry, get_peer_snapshot
Token cost: ~25-30 tokens (single-ticker mode)

---
This output is an AI-inferred interpretation of George Soros's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by George Soros or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 6 — Render — Emit

**Steps 1–5 are silent.** Perform the ticker resolution, cross-validation, regime analysis, and verdict computation internally — none of that working appears in your reply. Your **entire visible response consists only of the selected Step 5 rendered template plus every required Output addition below**. In basket mode, the analytical template begins at the Header line `Soros-style regime themes and exposure candidates (informational)`; in single-ticker mode, it begins at `Soros-style profile applied to <ticker>`. Before the analytical Header, render only the leading white-label elements required by `integration-pattern.md` §5, in its prescribed order, including a URL logo and the conditional Branding Header when applicable. If no leading white-label element applies, the mode-specific analytical Header is the absolute first output. The About This Report footer, AI-interaction disclosure, and standard disclaimer remain required parts of the visible response in the positions specified below. In both modes, do NOT add `**Step N**` labels, "Cross-validation passed", "All data verified", a "Let me…" preamble, or any other workflow narration.


## Output additions (white-label branding + §9.2 disclosure)

These additions apply to the rendered output ABOVE in addition to the persona-specific disclaimer shown in the output example. They are required regardless of view state.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top of the rendered output: `**<client_name>** Soros-style regime view`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. The persona-specific disclaimer in the output example characterizes the source of the framing; the §9.2 banner characterizes the LLM-generated synthesis itself.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Failure modes


If `list_macro_countries` fails, derive covered markets from RIC suffix defaults per `parallax-conventions.md §6` and note degradation.

If `macro_analyst` fails for a subset of markets, proceed with remaining markets as long as ≥2 succeeded.

If `get_telemetry` fails (e.g., "Admin org not configured"), single-ticker mode cannot perform Channel B. Fall back to industry-exposure-only evaluation on Channel A. **In this fallback state, maximum verdict is `partial_match`** — a single-channel `FLAGGED` result can never be `match` because `match` requires BOTH channels. Note "Channel B: UNAVAILABLE (telemetry env)" in the output.

If `build_stock_universe` returns no names or times out for any theme: for basket mode, report themes without rankings. For single-ticker mode, Channel A sub-path A1 (universe membership) is `NOT_FLAGGED`, but sub-path A2 (sector/industry classification match) must STILL be evaluated independently from `get_company_info` data. Channel A overall is `NOT_FLAGGED` only if A2 also fails to match. This is the critical non-regression: a `build_stock_universe` timeout does NOT automatically collapse Channel A to `NOT_FLAGGED`.


## Done when

- The reply begins at the analytical Header (or the white-label header when active) and contains only the rendered template plus the Output additions; no workflow narration.
- The cross-validation gate passed, or the exact refusal message was emitted and nothing else rendered.
- The verdict line, the citation, the methodology footer with tool sequence and token cost, the persona disclaimer verbatim, `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
