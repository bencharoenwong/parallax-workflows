---
name: parallax-ai-greenblatt
description: "Applies Joel Greenblatt's Magic Formula (per 'The Little Book That Beats the Market', 2006; academic replication Gray & Carlisle 2012) to Parallax data. Two modes: universe mode returns a top-decile ranked basket; ticker-check mode reports whether a single stock falls in the top decile of its peer universe by combined ROC + earnings yield rank. Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts no args (universe mode) or a single ticker. NOT for portfolio-level health check (use /parallax-portfolio-checkup). Other lenses: /parallax-ai-buffett, /parallax-ai-klarman, /parallax-ai-soros, /parallax-ai-ptj. For all five profiles simultaneously use /parallax-ai-consensus."
---

<!-- white-label: integration-pattern.md -->

# Parallax AI Greenblatt Profile

## When not to use

- Bottom-up factor scoring without the mechanical formula → use /parallax-ai-buffett
- Balance-sheet-first special situations → use /parallax-ai-klarman
- Top-down macro analysis → use /parallax-ai-soros
- Trend-following + macro overlay → use /parallax-ai-ptj
- Cross-profile consensus → use /parallax-ai-consensus
- Full due diligence → use /parallax-due-diligence
- Running backtests → use /backtest

## Gotchas

- Expected Parallax spend: ~10–15 tokens ticker-check, ~10–30 universe mode (`_parallax/token-costs.md`); `build_stock_universe` is 5 of that.
- JIT-load `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/greenblatt.md` — Step 0.
- Universe mode is the default with no ticker; ticker-check mode with exactly one. Exclude financials and utilities from the default universe per Greenblatt's original rule.
- `build_stock_universe` is async and broad queries time out: queries MUST be sector-scoped (default `"US large-cap consumer staples"`); a broad request runs sector-by-sector and merges.
- NEVER use first-person impersonation — always "Greenblatt-style" or "Magic Formula". Disclaimer verbatim with "Joel Greenblatt" for [Investor]. Public book + academic replication only — no `get_assessment`, no `score_total`.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Applies Joel Greenblatt's Magic Formula (ROC rank + earnings yield rank, combined, top decile) to Parallax data.

## Usage

```
/parallax-ai-greenblatt                    # universe mode — default US equity universe
/parallax-ai-greenblatt AAPL               # ticker-check mode — is AAPL in the top decile?
/parallax-ai-greenblatt AAPL.O             # RIC format also accepted
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This dispatcher is generic — all differentiation lives in the profile spec; the contract is `_parallax/AI-profiles/profile-schema.md` §2.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/greenblatt.md`.
3. `discover-tools`: bind every tool in the profile's `tool_sequence` to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Mode: no ticker → **universe mode**; exactly one → **ticker-check mode**; more → reject: "Greenblatt profile takes zero or one ticker. For multi-ticker checks use /parallax-ai-consensus." Ticker-check: resolve the RIC per conventions §1 and `call-tool` `get_company_info` for sector/industry.

### Step 2 — Fetch (parallel batches)

1. `call-tool` `build_stock_universe` with a sector-scoped query — universe mode: the default or `--universe "<theme>"`; ticker-check: a peer universe derived from the ticker's sector (e.g. Technology Hardware → `"US large-cap technology hardware"`). Timeout → retry ONCE narrower; second timeout → `INSUFFICIENT_UNIVERSE`, no verdict.
2. Cap the universe at the top 30 by `composite_score`.
3. `call-tool` `get_financials(statement=ratios)` for each of the 30 together (ROC via `return_on_invested_capital` when direct ROC is absent; earnings yield = `1 / enterprise_value_ebit`).
4. Universe mode: `get_peer_snapshot` for the top-3 basket members (pedagogy). Ticker-check: `get_peer_snapshot` on the target.

### Step 3 — Verify

Cross-validation gate per `profile-schema.md §2 Step 2`: `target_company` (top level; no `name` field — peers are `comparison[].company`) against `get_company_info.name`; refuse to render on mismatch (ticker-check: the target; universe: each top-3 member). Names whose `get_financials(ratios)` failed are dropped from the ranking and the coverage loss noted in the methodology footer. A universe under 10 names is expanded once, else `INSUFFICIENT_UNIVERSE`.

### Step 4 — Compute

Rank each candidate on ROC and on earnings yield independently; sum the ranks; sort ascending. Universe mode: the top 10% (3 of 30) is the Magic Formula basket. Ticker-check verdict: top 10% → `match`; top 25% → `partial_match`; below → `no_match`.

### Step 5 — Compose (render through the output template)


**Universe mode output:**

```
Greenblatt-style basket (Magic Formula)
Source: Greenblatt, J. (2006). The Little Book That Beats the Market.
Secondary: Gray, W., Carlisle, T. (2012). Quantitative Value.

Universe: <query>
Universe size: <N>

Top decile by combined ROC + earnings yield rank:

| Rank | Ticker  | ROC rank | EY rank | Combined | Sector          |
|------|---------|----------|---------|----------|-----------------|
| 1    | XXX.N   | 2        | 5       | 7        | Consumer Disc.  |
| 2    | YYY.O   | 4        | 3       | 7        | Technology      |
| ...  | ...     | ...      | ...     | ...      | ...             |

Workflow derived from: Greenblatt, J. (2006). The Little Book That Beats the Market; Gray & Carlisle (2012).
Last anchor-tested: 2026-04-06 (CSCO.O, MSFT.O, NVDA.O)
Tool sequence: build_stock_universe, get_peer_snapshot × N, get_financials(ratios) × N
Token cost: ~10-30 tokens (universe mode) / ~10-15 tokens (ticker-check mode)

---
This output is an AI-inferred interpretation of Joel Greenblatt's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Joel Greenblatt or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

**Ticker-check mode output:**

```
Greenblatt-style profile applied to <ticker>
Source: Greenblatt, J. (2006). The Little Book That Beats the Market.

Peer universe: <sector peers>
Universe size: <N>

<Ticker> ranking:
  ROC rank:            <R> of <N> (<percentile>th percentile)
  Earnings yield rank: <R> of <N> (<percentile>th percentile)
  Combined rank:       <R> of <N> (<percentile>th percentile)

Profile fit: <match/partial_match/no_match> — <ticker> is in the [top 10% | top 25% | below top 25%] of the peer universe by Greenblatt combined rank.

Verdict sensitivity: combined rank sits at the <percentile>th percentile, <D> positions from the [top-10% match | top-25% partial] cutoff; the verdict flips to the adjacent tier if the combined rank crosses that boundary.

Workflow derived from: Greenblatt, J. (2006). The Little Book That Beats the Market; Gray & Carlisle (2012).
Last anchor-tested: 2026-04-06 (CSCO.O, MSFT.O, NVDA.O)
Tool sequence: get_peer_snapshot, get_financials(ratios) × N
Token cost: ~10-15 tokens

---
This output is an AI-inferred interpretation of Joel Greenblatt's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Joel Greenblatt or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 6 — Render — Emit

**Steps 1–6 are silent.** Perform the ticker resolution, cross-validation, scoring, threshold logic, and verdict computation internally — none of that working appears in your reply. Your **entire visible response consists only of the selected Step 6 rendered template plus every required Output addition below**. In universe mode, the analytical template begins at the Header line `Greenblatt-style basket (Magic Formula)`; in ticker-check mode, it begins at `Greenblatt-style profile applied to <ticker>`. Before the analytical Header, render only the leading white-label elements required by `integration-pattern.md` §5, in its prescribed order, including a URL logo and the conditional Branding Header when applicable. If no leading white-label element applies, the mode-specific analytical Header is the absolute first output. The About This Report footer, AI-interaction disclosure, and standard disclaimer remain required parts of the visible response in the positions specified below. In both modes, do NOT add `**Step N**` labels, "Cross-validation passed", "All data verified", a "Let me…" preamble, or any other workflow narration.


## Output additions (white-label branding + §9.2 disclosure)

These additions apply to the rendered output ABOVE in addition to the persona-specific disclaimer shown in the output example. They are required regardless of view state.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top of the rendered output: `**<client_name>** Greenblatt-style screen`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. The persona-specific disclaimer in the output example characterizes the source of the framing; the §9.2 banner characterizes the LLM-generated synthesis itself.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Failure modes


If `build_stock_universe` returns fewer than 10 names, the top-decile calculation is unreliable. Expand the universe query once; if expansion fails, return `INSUFFICIENT_UNIVERSE` and decline to render a verdict. In ticker-check mode, this means the /parallax-ai-consensus meta-skill should treat the profile as `skipped`.

If `get_financials(ratios)` fails for a subset of universe members, drop those names from the ranking and note the coverage loss in the methodology footer.


## Done when

- The reply begins at the analytical Header (or the white-label header when active) and contains only the rendered template plus the Output additions; no workflow narration.
- The cross-validation gate passed, or the exact refusal message was emitted and nothing else rendered.
- The verdict line, the citation, the methodology footer with tool sequence and token cost, the persona disclaimer verbatim, `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
