# Phase 2 — Stress-test market assumptions (layers 1–4)

Loaded when Phase 2 fires, after the Assumption Map has been played back and corrected (Phase 1).
This phase produces the Pass-1 factual reads that Phase 5 (Pass 2, client conditioning) will later
re-weight but never overwrite.

## Market selection

Pick relevant markets per `_parallax/parallax-conventions.md` §6 (home market + revenue geography
+ commodity exposure + supply-chain dependency), **capped at 3**. If the thesis names no tickers,
derive markets from the thesis's own macro claims (e.g., a thesis about "US rate cuts" needs
`United States`; a thesis about "China reopening consumer demand" needs `China`).

Call `list_macro_countries` first if market coverage is in doubt — 15 markets, publicly-traded
equities only (see Known Limitations below). A macro or sector claim about an uncovered market is
marked `out-of-scope` in the Assumption Map, not guessed.

## Known Limitations — asset-class coverage & routing

Parallax scores **public equities + broad equity/country ETFs**, and provides **country-level
macro** narrative. It does **not** score coins, currency pairs, individual bonds, spot commodities,
or derivatives as instruments. This shapes how a non-equity thesis leg is classified — the routing
below keeps such legs from being either fabricated or wrongly dumped to `out-of-scope`.

**Rates / FX legs are `partial`, not `out-of-scope`.** A thesis leg about bond yields, the curve,
duration, or the dollar is testable as a *country-level regime read* via `macro_analyst`
`fixed_income` (rates/curve) or `currency` (FX) — route it there and classify
Supported/Contradicted on the macro *direction*. State the boundary in the break condition: the
regime is read, the specific instrument (a given bond, a given FX pair) is not — so trajectory and
instrument-level basis stay unverified. Only mark `out-of-scope` when even the country-level macro
is silent or the market isn't covered.

**Do not use asset-class-proxy ETFs as a backdoor to scores.** Non-equity ETFs (bond, gold,
crypto) are unreliable here: some symbols aren't in the identifier set at all, others resolve to a
RIC but return no profile/factor scores, and a commodity ETF may return price with **null** factor
scores. Never present a null/absent-score ETF as a scored read. Broad equity/country ETFs (SPY-type)
are the reliable ETF surface; asset-class proxies are not.

**Crypto / options / futures / private assets** remain `out-of-scope` as instruments — reachable
only through their *equity* expressions (e.g. crypto-adjacent or commodity-producer equities), which
are then tested as ordinary layer-3 positions in Phase 3, never as the underlying asset.

**Disclose coverage early — the Coverage Notice.** The `testability` of every assumption is known at
Phase 1 (`assumption-decomposition.md`), so the coverage picture exists before any deep analysis runs.
Surface it **up front**, as the **Coverage Notice** rendered right under Thesis Restatement (SKILL.md
Output Format), classifying each leg **full** (scored equity / broad equity-country ETF / country
macro) · **partial** (rates or FX regime read only — instrument not scored) · **out-of-scope**
(crypto / options / futures / spot commodities / private, reachable only via equity expressions). If a
thesis is largely partial or out-of-scope — e.g. a pure FX or single-bond call, or a crypto thesis with
no equity expression — the reader must learn that at the top, not infer it from a page of Unconfirmed
rows at the end. This is honesty about resolution, not a refusal to run: a partial-coverage thesis is
still analyzed as far as the country-macro read allows, with the boundary stated.

*(Coverage last live-probed 2026-07-04 against the connected MCP; re-probe if Parallax announces new
asset-class support.)*

## Batch — fire in parallel

For each selected market:

| Tool | Parameters | Use for |
|---|---|---|
| `get_telemetry` | `fields: ["regime_tag","signals","commentary.headline","commentary.mechanism","divergences"]` | Current regime baseline. **Async, ~15-30s** — do not block the rest of the batch on it. |
| `macro_analyst` | `market: "<market>"`, `component` per which layers the thesis needs: `"macro_indicators"` (inflation, growth, surprise-index reads — **fire this whenever the thesis makes an explicit inflation or Fed-path claim**, e.g. "disinflation continues" or "the Fed keeps cutting"), `"tactical"` (regime/rates/growth), `"fixed_income"` (**the rates/curve/duration path** — yield-curve shape, term-premium, front-end vs. long-end, foreign-demand; fire this for any bond-yield or duration thesis leg), `"currency"` (**the FX path** — dollar/DXY level and regime, carry, mean-reversion; fire this for any currency thesis leg), `"factors"` (macro-level factor tilts), `"sectors"` (sector demand/pricing power claims), `"news"` (theme/sector-level news — **this is how theme news gets tested, not `get_news_synthesis`**, which is symbol-only and belongs to Phase 3) | Layer 1–4 assumption testing, one call per (market × component) |

Fire every (market × component) combination simultaneously — these are independent per
`_parallax/parallax-conventions.md` §3. A thesis touching 2 markets across 3 components is 6
parallel `macro_analyst` calls plus 2 `get_telemetry` calls, not a serial loop. **A CPI/inflation
or rate-path claim without a `macro_indicators` call is an Unconfirmed masquerading as a guess** —
don't classify A1/A2-style macro claims off `tactical` alone if the thesis's own wording turns on
the inflation trajectory specifically.

## Classification

For each layer-1–4 assumption in the Assumption Map, read the relevant `macro_analyst` /
`get_telemetry` output and classify:

- **Supported** — the current data points the same direction as the claim.
- **Contradicted** — the current data points the opposite direction.
- **Unconfirmed** — the data is silent, ambiguous, or the market is `out-of-scope`. **Never
  fabricate a read to force a Supported/Contradicted call** — Unconfirmed is a legitimate,
  frequent outcome and should be reported as such.

**Read staleness.** `macro_analyst` output carries its own `report_date`, which can lag `today`
(and lag `get_telemetry`'s date) by days to a couple of weeks. When the macro report materially
predates today, surface that `report_date` in **Confidence & Caveats** — the same staleness
discipline Phase 3 applies to news cards. A classification built on a two-week-old macro read is
still valid, but the reader must be able to see how old the signal behind it is.

## Cross-component & tag/narrative consistency

`macro_analyst` components are generated semi-independently, so two components of the *same*
`report_date` can disagree on the same figure (e.g., `macro_indicators` citing one payrolls print
while `factors` cites another), and `get_telemetry`'s single `regime_tag` can diverge from its own
`commentary.headline`/`mechanism`. When reads conflict:

- **Classify on the direction the sources agree on, not the disputed level.** If both point to a
  softening labor market but disagree on the exact print, the *direction* is the
  Supported/Contradicted signal; the specific number is not.
- **Prefer the narrative mechanism over a single summary tag** when `get_telemetry`'s `regime_tag`
  and its `commentary` diverge — a one-word tag ("Broad risk-on") compresses away nuance the
  mechanism ("mixed_rotation", "concentrated deleveraging") preserves.
- **Surface the discrepancy in Confidence & Caveats**, with both values, so the reader sees the
  conflict rather than a falsely precise single figure.

Never resolve a conflict by silently picking the number that better fits the thesis.

## Point-in-time reads vs. multi-period claims

A macro read is a *snapshot*; a thesis claim is often a *trajectory* ("inflation decelerating for
three straight quarters", "margins expanding all year"). `macro_analyst` tests the current-state
**edge** of such a claim, not its full history. Classify on that edge — a current re-acceleration
Contradicts a "still decelerating" claim — but state in the break condition (and in Confidence &
Caveats) that the multi-period trajectory itself is not directly verified by a point-in-time read.
Do not present a snapshot as if it confirmed the whole trend.

## The stress step

For every assumption classified Supported or Contradicted (Unconfirmed assumptions have no break
condition to state — there's nothing confirmed to break), state:

1. **The adverse condition** that would flip Supported → false, in plain language (e.g., "the Fed
   holds rates through year-end instead of cutting").
2. **Magnitude** — how far the break condition would need to move the world (a 25bp surprise vs.
   a full regime reversal are different severities). Use the `macro_analyst` / `get_telemetry`
   data itself to calibrate this, not a generic guess.
3. **Time-to-play-out** — over what horizon the break condition would plausibly resolve (weeks,
   quarters, multi-year). **Both magnitude and time-to-play-out are required fields** — Phase 5
   cannot re-weight severity for a specific investor without them (time-to-play-out is compared
   against the client's horizon; magnitude is compared against their risk capacity).
4. **Base severity** — the client-invariant severity if this break condition fires: how much of
   the thesis's conclusion it takes down. This is the number Phase 5 re-weights; it is never
   itself a function of who holds the position.

## Output shape carried forward

Each layer-1–4 assumption exits Phase 2 with: `status` (Supported/Contradicted/Unconfirmed),
`break_condition` (text), `magnitude` (text + rough scale), `time_to_play_out` (text + rough
scale), `base_severity` (high/med/low). This record is what Phase 4 synthesizes and what Phase 5
re-weights — keep it structured, don't let it collapse into prose before Phase 4.
