---
name: parallax-pair-finder
description: "Long/short equity pair builder: given one leg, suggest top-3 counter-leg candidates from peers; given both legs, report residual factor / sector / macro / dollar / beta exposure. Symbols in RIC format. NOT for single-stock analysis (use /parallax-deep-dive), not for peer comparison tables (use /parallax-peer-comparison), not for portfolio analysis (use /parallax-morning-brief), not for long-only screening (use /parallax-thematic-screen)."
---

<!-- white-label: integration-pattern.md -->

# Pair Finder

## When not to use

- Single stock deep dive → use /parallax-deep-dive
- Generic peer table only → use /parallax-peer-comparison
- Multi-position portfolio analysis → use /parallax-morning-brief
- Long-only stock screening → use /parallax-thematic-screen

## Gotchas

- Expected Parallax spend: ~8 tokens single-pair evaluate, ~15 for a 3-candidate suggestion run (`_parallax/token-costs.md`); price series are free.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §3 parallel execution, §4/§4.0 fallbacks, §14 host primitives. JIT-load `references/residual-math.md` for factor-net, beta and hedge-ratio formulas; `references/modes.md` for the per-mode batch tables.
- JIT-load `_parallax/coverage-matrix.md`: equities price via `export_price_series`, the benchmark ETF via `etf_daily_price` — separate endpoints; `etf_daily_price` returns `[]` for a multi-symbol call if any symbol is uncovered, so always one call per benchmark.
- Suggestion mode uses a single `export_peer_comparison` call so factor scores are cross-sectionally comparable; evaluate mode MUST flag score comparability when the short is not in the long's peer set.
- v1 scope: domicile/listing-currency only (no revenue geography), dollar- and beta-neutral ratios only (no share counts), within-sector suggestions only; evaluate mode accepts cross-sector pairs but flags them.
- **Output gate (HARD HALT):** no hedge ratios when the benchmark series is null or has < 60 observations; never substitute pair-relative regression beta with a caveat — that pattern is banned for primary deliverables (Step 3).
- Liquidity disclaimer is mandatory in every output: ADV / borrow / float are not validated by Parallax.
- JIT-load `_parallax/house-view/loader.md` if a view is present: dual-single-stock consumer per §7 — tilts are NOT applied; §7.3 tension banner per leg, §7.1 note once per pair, §6 audit once per invocation; §7.2 is N/A (the candidate set comes from `export_peer_comparison`).
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Long/short equity pair construction for fundamental PMs. Given one leg of a thesis, suggest the other leg from peers and report what residual exposure survives the hedge. Given both legs, report the residual.

## Usage

Three invocation modes:

```bash
# Mode 1 — Find short candidate for a long thesis
/parallax-pair-finder NVDA.O long
/parallax-pair-finder NVDA.O long --candidates=3 --with-history

# Mode 2 — Find long candidate for a short thesis
/parallax-pair-finder INTC.O short

# Mode 3 — Evaluate a pair the PM already has
/parallax-pair-finder long=NVDA.O short=AMD.O
/parallax-pair-finder long=NVDA.O short=AMD.O --with-history
```

**Flags:** `--candidates=N` (default 3, suggestion modes only); `--with-history` (adds 60d→180d realized correlation, pair vol, max drawdown, hit rate); `--benchmark=<ticker>` (explicit benchmark after a HALT); `--no-beta` (dollar-neutral only).

**Default selection criterion (v1):** closest peer with worst total score for short candidates; closest peer with best total score for long candidates (same-sector relative-value framing).

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This is a multi-mode skill: Step 1 selects the mode; `references/modes.md` carries each mode's batch tables; the spine is the same.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` and `references/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named in `references/modes.md` (both modes) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args and detect the mode: `<symbol> long` → Mode 1; `<symbol> short` → Mode 2; `long=<symbol> short=<symbol>` → Mode 3; anything else → ask the operator which mode (`ask-operator`).
4. `load-reference` `_parallax/house-view/loader.md`; run §1–§2. If a view is present, capture the load preamble and the sector tilt vector for the Step 5 per-leg §7 surfacing.
5. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.
6. `load-reference` `references/residual-math.md` and `references/modes.md`.

### Step 1 — Resolve inputs

RICs per conventions §1 (`get_company_info` empty → try `.O`, then `.N`, then ask). Benchmark from the primary leg's `market` via the canonical mapping in `references/modes.md` (other markets: `etf_search(market=…, query="MSCI", recommendation="HOLD")`, highest AUM). 180-day window: `end_date = today`, `start_date = today − 180 days`.

### Step 2 — Fetch (parallel batches)

Per `references/modes.md`: **Batch A** identification + peer set + macro coverage (`get_company_info`, `export_peer_comparison` (`format="json"`), `list_macro_countries`); **in-process candidate selection** (suggestion) or **score-comparability resolution** (evaluate, with one `get_peer_snapshot(short)` fallback when the short is outside the long's peer set); **Batch B/C** beta inputs — `export_price_series(days=180, format="json")` per equity leg and `etf_daily_price` for the benchmark ETF, one call per benchmark (asset-class split per coverage-matrix); **macro** `macro_analyst(component="tactical")` per distinct leg market; **`--with-history`**: 365-day series per leg.

### Step 3 — Verify

- `export_peer_comparison` failure: retry once, then `get_peer_snapshot(primary)` with comparability marked best-effort.
- A leg with < 90 days of prices: that pair degrades to dollar-neutral sizing only (per-leg degradation, never a whole-skill halt).
- Benchmark empty: one `etf_search` discovery retry. Then the **output gate (HARD HALT, gate-shaped per conventions §4.0)** before any beta-neutral ratio renders — refuse, do not degrade:

```
HARD GATE — refuse, do not degrade:
  if benchmark_series is null OR len(benchmark_series.observations) < 60:
    ABORT skill output. Render exactly:

      ⚠ Cannot produce beta-neutral hedge ratios.
        Benchmark: <benchmark_ticker> for market <primary_market>
        Returned: <N> observations from etf_daily_price (need ≥ 60 for stable beta)
        Failure path: <which fallback step ran last — initial-fetch / etf_search-discovery>

      Operator action — pick one:
        (a) Re-run with explicit benchmark: /parallax-pair-finder <symbol> <side> --benchmark=<alt-ticker>
        (b) Run with --no-beta to get dollar-neutral suggestions only (factor / sector residuals still computed)
        (c) Escalate to API team if etf_daily_price coverage for this market is genuinely missing

    DO NOT render Batch D, Batch E, the comparison table, or any per-pair detail.
    DO NOT emit hedge ratios under any other label (no "pair-relative regression" substitution).
```

Rationale: a hedge ratio computed against the wrong benchmark is a confidence-building lie; a footnote does not change a PM's sizing decision. The pair-relative regression formula in `references/residual-math.md` §3a is reference math only in v1, not a runtime fallback.

### Step 4 — Compute

Per `references/residual-math.md`: net factor scores (long − short per pillar), sector and domicile residuals, beta per leg over the 180-day window against the benchmark, beta-neutral ratio = `β_long / β_short`, dollar-neutral 1:1; macro residual as the qualitative difference of the legs' tactical stances; realized stats under `--with-history`. Every number comes from the series and the formulas, never from memory.

### Step 5 — Compose

Fill **Output Format** below in order for the detected mode: House View Preamble per loader.md §5.1; Branding Header per integration-pattern.md §5; per-leg §7.3 banner and one §7.1 note per pair via `render_view_conflict()` when a view is active; the score-comparability flag always; the liquidity caveat always; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 rule 5 when a view is active, otherwise the bespoke pair-finder disclaimer below; audit entry per loader.md §6.1 once per invocation.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/pairfinder.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill pair-finder < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout (or, on a HALT, exactly the gate message). The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row; beta math is arithmetic over fetched series and needs no shell). No Step 7.

## Output Format

**Begin the response immediately with the rendered report — no preamble.** In suggestion mode the first expected line is `#### 1. Verdict` (or the HARD HALT message); in evaluate mode it is the **Pair** line; the House View Preamble / Branding Header precede either when active.

**House View Preamble** (only if view active) — render per loader.md §5 rule 1 at the very top, before the mode-specific output. Per loader.md §5.1.

**Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** pair finder`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.

### Suggestion mode (Mode 1 / Mode 2)

Tiered: verdict → comparison table → per-pair detail.

#### 1. Verdict (top of output)

One-line ranked recommendation:

> **Top pair: `<long>` / `<short>` (rank 1 of N).** Cleanest residual: `<one-line idiosyncratic thesis>`. Sector-neutral within `<sector>`; net factor tilt: `<top-2 factor residuals>`.

If only one candidate viable (e.g., others lacked beta history): say so explicitly.

#### 2. Comparison table

| Rank | Long | Short | Net Total | Net Value | Net Quality | Net Momentum | Net Defensive | Net Tactical | Sector Resid. | Domicile Resid. | $-neutral | β-neutral | Idiosyncratic Thesis |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | NVDA.O | ARM.O | +2.7 | +1 | +1 | +2 | +5 | +3 | 0 | 0 | 1:1 | 0.94:1 | Long defensive moat vs ARM royalty risk |
| 2 | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

(Sector residual is "0" when both legs share the same sector. Domicile residual is "0" when both share the same `market` field.)

#### 3. Per-pair detail (one block per candidate)

For each candidate, render:

- **Pair identification**: long ric + name + sector/industry; short ric + name + sector/industry; market cap ratio
- **Net factor scores**: 5-pillar table (long − short for each)
- **Sector / domicile residual**: "Both legs are `<sector>` / `<industry>` / `<market>`" if neutral, else explicit description
- **Macro residual**: from `macro_analyst` — primary market regime stance
- **Sizing**:
  - Dollar-neutral: 1:1 notional
  - Beta-neutral: `<ratio>` dollars short per dollar long (β_long / β_short = `<num>`)
- **Idiosyncratic thesis residual**: 1-2 sentence narrative — "After this pair, you are net long `<top factor>` and `<sector/macro>`; the bet is `<plain English>`."
- **(`--with-history` only)** Realized correlation `<corr>`, pair vol `<vol>` annualized, max drawdown `<dd>`, hit rate `<hr>`.

#### 4. Mandatory disclaimers (bottom)

- *Liquidity caveat: hedge ratios assume executable liquidity. Average daily volume, short borrow, and float are not validated by Parallax — verify externally before sizing.*
- *Score comparability flag* (suggestion mode: always "same_universe — single peer-comparison call"; evaluate mode: render the flag from Step A.5).
- Standard Parallax informational-not-investment-advice disclaimer (see `_parallax/parallax-conventions.md` §7).

### Evaluate mode (Mode 3)

Single-pair report — no comparison table:

- **Pair**: `<long>` / `<short>` — sector / industry / market for each
- **Net factor scores** (5-pillar table)
- **Sector residual** (== 0 if same sector, else "cross-sector exposure: `<long_sector>` long / `<short_sector>` short")
- **Domicile / currency residual** (== 0 if same market, else "cross-currency exposure: `<long_market>` long / `<short_market>` short")
- **Macro residual** (per-leg regime stance + delta if cross-market)
- **Sizing**: dollar-neutral and beta-neutral
- **Idiosyncratic thesis residual** (1-2 sentences)
- **(`--with-history`)** Realized stats
- **Score comparability flag** (always render — same_universe or cross_universe)
- Liquidity disclaimer + standard disclaimer

### About This Report (always present, bottom of output)

One line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.


## Failure modes

- Mode not detectable: ask, do not guess.
- Benchmark unavailable after discovery: the HARD HALT message with the three operator options; no comparison table, no per-pair detail.
- Leg with insufficient history: dollar-neutral only for that pair, stated in its row.
- Cross-universe scores in evaluate mode: the comparability flag renders prominently.
- Macro market uncovered: "macro context unavailable for this market".
- House-view banner states `malformed` / `expired` / `critical`: the banner renders verbatim (conventions §0.3 item 4).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- First line is the House View Preamble, the Branding Header, or the mode's first section (`#### 1. Verdict` in suggestion mode; the Pair line in evaluate mode).
- No beta-neutral ratio rendered unless the benchmark series passed the gate; every degraded pair says why.
- Score-comparability flag and liquidity caveat present; when a view is active, the `view_status` banner appears verbatim and the audit entry is appended once.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1-family disclaimer are present; expected spend stated (Gotchas).

## Disclaimer

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

*This is informational analysis based on Parallax factor scores. Hedge ratios assume executable liquidity; ADV, short borrow, and float are not validated by Parallax — verify externally before sizing. All outputs should be reviewed by qualified professionals before any investment decisions.*
