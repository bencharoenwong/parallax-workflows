---
name: parallax-thematic-screen
description: "Thematic stock screen and idea analysis: build a stock universe from a theme, score top picks, layer optional macro context and regime signals, compare peers, and check financials via Parallax MCP tools. Triggers: 'screen for [theme]', 'trade ideas around X', 'thematic ideas for Y', 'stocks in Z theme', 'new ideas in [sector]'. NOT for single stock analysis (use /parallax-should-i-buy), not for portfolio review (use /parallax-client-review)."
---

<!-- white-label: integration-pattern.md -->

# Thematic Screen

## When not to use

- Single stock analysis → use /parallax-should-i-buy
- Portfolio review → use /parallax-client-review
- Peer comparison of known stock → use /parallax-peer-comparison

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
- JIT-load _parallax/house-view/loader.md FIRST. Rules 3 (ground-truth check) and 4 (divergence assertion) in §5 apply UNIVERSALLY (view or no view — data-integrity requirements). Rules 1-2 and 5 apply when a view is active. Multi-sector theme queries can collapse to a single sector — divergence assertion must fire regardless of view. The user-supplied theme is sovereign per §4 — render conflict banner if theme contradicts view tilts.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
- build_stock_universe searches ~65K company descriptions by semantic similarity
- Default top_n is 5 — adjust for broader or narrower screens
- get_peer_snapshot called once per top pick (N calls) — fire in parallel
- get_financials called for top 3 only
- macro_analyst depends on list_macro_countries — fire as Phase A step 3 batch per conventions (3a → 3b). Cap at 3 markets per screen. Skip step 3 if invoked with `--no-macro` or if no covered markets are relevant to the theme.
- get_telemetry may return "Admin org not configured" or fail — graceful skip per parallax-conventions.md. If unavailable, omit the Regime Signal sub-line in the Macro Context section (do NOT abort the screen). No `--no-telemetry` flag is exposed: failure is already safe (telemetry-None → no Regime Signal sub-line) and the single-call latency does not justify a separate flag surface.
- Macro context renders as SOFT annotation. When house view is active, view tilts remain sovereign per loader.md §4 — macro_analyst output supplements but never silently re-ranks. When no view is active, macro context may drive country/sector emphasis in the Output Format only; ranking is still composite-driven.
- If the user-supplied theme is itself a macro-condition phrase, macro overlay may read as self-confirming. Render a banner suggesting /parallax-macro-outlook for macro-first analysis, then proceed. **Trigger criterion (deterministic, case-insensitive):** theme string contains any of `rates`, `inflation`, `recession`, `tariff`, `tariffs`, `yield curve`, `currency`, `USD`, `dollar`, `credit spread`, `GDP`, `monetary policy`, `fiscal`, `Fed`, `central bank`, `regime`, `cycle`, AND does not also contain a sector/industry word (`tech`, `energy`, `healthcare`, `financials`, `industrials`, `materials`, `utilities`, `staples`, `discretionary`, `REIT`, `biotech`, `software`, etc.). List is a starting heuristic; extend per deployment context.
- Telemetry semantics: `get_telemetry` returns BASKET-LEVEL regime signals (`regime_tag`, `divergences[]` with basket-level z-scores, `commentary.headline`) — NOT per-ticker confidence. The schema does not expose per-name signal. Render only: (a) `regime_tag`, (b) top 1-3 divergence basket names with sign, (c) `commentary.headline` — in the Macro Context section. Do NOT tag individual Top Picks rows with a "Confidence" annotation derived from telemetry; any per-name tag would be hallucinated from basket-level data. Do NOT propagate raw proprietary framework-component names or factor-decomposition values from telemetry even if exposed.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.
- Optional `audience=` argument: `client_safe | internal_analyst`; precedence follows `parallax-conventions.md` §13.1.

Discover investment opportunities by theme using Parallax's semantic universe builder.

## Usage

```
/parallax-thematic-screen "AI infrastructure companies"
/parallax-thematic-screen "trade ideas around energy transition"
/parallax-thematic-screen "thematic ideas for onshoring beneficiaries" top_n=10
/parallax-thematic-screen "clean energy utilities" --no-macro
/parallax-thematic-screen "gene therapy pure plays"
/parallax-thematic-screen "AI infrastructure companies" audience=client_safe
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation and conflict resolution.

### Pre-flight: house-view drift check

JIT-load `_parallax/house-view/auto-on-load-judge-pattern.md` and follow
its protocol. If the protocol surfaces a banner, render it before
proceeding to this skill's main workflow.

Skip this pre-flight if invoked with `--skip-drift-check` or if no active
house view exists.

### Phase A — Setup (parallel, universe 5 + list 1 + telemetry 1 + macro 5×markets (0-3) tokens)

Fire steps 1, 2, and 4 in parallel (independent). Step 3 is a dependent two-step sub-batch: step 3a (`list_macro_countries`) starts in parallel with steps 1/2/4, and step 3b (`macro_analyst` per market) fires only after step 3a returns.

1. **Load Active House View** — Per `loader.md` §1-§2. If view present, capture tilt vector + excludes. Resolve user theme vs view per §4: theme is sovereign, but conflicts surface as banners (e.g., theme="AI infrastructure" + view says `tech: -2` → screen runs as requested with "House view is UW tech; screen run per your explicit theme" banner).
2. **Build Universe** — Resolve user theme vs. view per loader.md §4. If view present AND `PARALLAX_LOADER_V2=1`, follow `loader.md` §3 "Application (V2)": decompose tilts into parallel per-sector calls, merge, and dedupe. If V1, prepend tilt context to the query and call `build_stock_universe` once. Filter results against `tilts.excludes`.
   - **Fallback on timeout:** If `build_stock_universe` times out (exceeds 30s), retry once with a narrower query (e.g., single primary sector from theme, or drop secondary modifiers). If second attempt still times out or returns empty, set `universe = []` and `universe_status = "unavailable"`, continue to Phase B with the empty candidate list, and flag the unavailable state in Output Format under "Universe Built". Do NOT call `check_portfolio_redundancy` as a placeholder — it requires portfolio input and will fail or return nonsense. Do not abort the screen.
3. **Macro Context** (skip if `--no-macro` flag set). Two-step batch (per parallax-conventions.md "Dependent calls"):
   - **Step 3a:** Call `list_macro_countries` to enumerate covered markets (returns canonical names like "United States", "Japan").
   - **Step 3b:** Infer up to 3 relevant markets from the theme (e.g., "onshoring beneficiaries" → US + Japan; "China consumer recovery" → China; geo-agnostic themes like "AI infrastructure" → US plus one other major covered market relevant to the theme). **Cross-reference inferred markets against the step 3a result; only use names that match verbatim in the covered list (e.g., "United States" not "US")** — `macro_analyst` requires exact-string match per parallax-conventions.md §0.2 and fails with parameter validation error otherwise. Drop unmatched inferences silently. If no markets remain after matching, set `macro_context = None`. Call `macro_analyst(market=<m>, component="tactical")` for each matched market in parallel. If all return unavailable, set `macro_context = None` and continue. Cap strictly at 3 markets per parallax-conventions.md.
4. **Telemetry** — Call `get_telemetry` for BASKET-LEVEL regime signal context (`regime_tag`, `divergences[]`, `commentary.headline` — see gotchas for the schema). Per parallax-conventions.md graceful fallback: if it returns "Admin org not configured" or otherwise fails, set `telemetry = None` and continue. Do NOT abort the screen. Telemetry does NOT expose per-name confidence — it's basket-level only, used to enrich the Macro Context section in Output Format, never to tag individual Top Picks rows.

**After Phase A:** Proceed to Phase B with completed universe (or placeholder if unavailable). Carry forward `macro_context` and `telemetry` for Phase C scoring annotation and Output Format rendering.

### Phase B — Inline Validation (no new tool calls)

5. **Divergence assertion** (per loader.md §5 rule 4 — required universally, view or no view) — REQUIRED for V1 paths. If the query named N≥2 sectors/themes, compute `max_sector_share / total` in returned candidates. If > 0.6, emit fail-loud warning: "universe collapsed to single sector despite multi-sector request." If `PARALLAX_LOADER_V2=1`, the divergence assertion is used to verify the merge quality but is less likely to trigger a hard failure.
6. **Apply freeform excludes** — if view active and `tilts.excludes_freeform` non-empty (per loader.md §3 "Free-form excludes handling"), drop candidates matching any pattern against `get_company_info` name/description/sector.

**After Phase B:** Proceed to Phase C with validated universe.

### Phase C — Scoring & Analytics (sequential coordination, ~2×top_n + 4 tokens)

**C1. Ground-truth check + Score Top Picks** (per loader.md §5 rule 3 — required universally) — For the top N results, call `get_peer_snapshot` AND `get_company_info` per candidate in parallel. Record `returned_name` (snapshot `target_company`) and `expected_name` (info `name`). Treat any row where `returned_name ≠ expected_name` as UNTRUSTED (do not rank, flag ⚠ MISMATCH). If view active, re-rank trusted rows by `composite × multiplier(holding's sector)` per loader.md §3.

**After C1 completes, fire C1.5, C2, and C3 in parallel** (C1.5 does NOT gate C2 or C3 — rank is established by C1 and is composite-driven, so the highest-scored trusted row for C2 and the top-3 for C3 are known the moment C1 completes):

**C1.5. Annotation (no re-rank, concurrent with C2/C3):** Reference implementation of the **Concurrent Annotation Pattern** documented in `_parallax/parallax-conventions.md §3.1`. Tags computed in this step annotate the Output Format only. **They MUST NOT change rank order, alter Top Picks membership, or override the composite score from C1.** Rank is composite-driven (per loader.md §3) to preserve auditability — Macro Tag is a read-only annotation on the rank C1 produced.

- If `macro_context` is present from Phase A.3, tag each trusted row with `macro_tag ∈ {with-regime, against-regime, orthogonal}` derived from the trusted row's primary market exposure and the corresponding `macro_analyst` tactical output. **Primary market exposure source (deterministic):** read `get_company_info.country` (already fetched in C1) and normalize to the canonical macro-market name returned by `list_macro_countries` (e.g., "US"/"USA" → "United States"). If `country` is missing, empty, or does not normalize to any market in `macro_context`, set `macro_tag = orthogonal` and continue — never infer market from sector or LLM judgement.

Skill authors copying this pattern: do not introduce a sort or filter step driven by `macro_tag`. Re-ranking by annotation breaks auditability and is the documented anti-pattern this phase exists to prevent. **Downstream consumers (chained skills, exporters, dashboards) MUST also preserve all annotated rows in the Top Picks output — Macro Tag is a read-only annotation, NEVER a filter predicate.** Row-preservation is a contract that applies to annotated tables; the output consumption contract below governs section-header parsing.

**C2. Compare Peers** — For the highest-scored TRUSTED stock (determined from C1 results, not C1.5), call `export_peer_comparison` with format "json".

**C3. Quick Financials** — For the top 3 trusted picks (determined from C1 results, not C1.5), call `get_financials` with statement "summary".

**After C1.5, C2, and C3 complete:** Append audit log entry per loader.md §6.

**Output consumption contract:** downstream consumers (Codex matcher, chained skills, exporters) MUST parse Output Format by section header name, not by positional order. The addition of `Macro Context` between `Theme` and `Universe Built` is non-breaking for any header-name-based parser.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format. The loader returns exactly seven keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** thematic screen`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to About This Report.
- **Theme: [theme]** (brief investment thesis; note view conflict inline if applicable; if theme string is itself a macro-condition phrase, render the macro-self-confirming banner per gotchas and suggest `/parallax-macro-outlook`)
- **Macro Context** (rendered if `macro_context` OR `telemetry` is present from Phase A) — one line per covered market (max 3) from macro_analyst: `<market>: <tactical takeaway from macro_analyst>`. State explicitly whether this is supplementary (house view active, view is sovereign) or primary (no view active). If `telemetry` is present, append a "Regime Signal" sub-line: `<regime_tag> | top divergence baskets: <basket names with sign, max 3> | <commentary.headline>`. Do NOT extend beyond what the tools returned — no LLM-confabulated narrative bridging the macro view to the theme.
- **Plain-Language Summary** (under `audience=client_safe` only): 2-3 sentences describing the theme read and top-pick rationale for a non-specialist reader; factor names carry the §13.3 gloss, no cutoff arithmetic, framed per §12 as informational with no directives.
- **Universe Built** (how many stocks found, key sectors; note any exclusions applied; surface divergence-assertion result per loader.md §5 rule 4)
- **Top Picks** (table: `input_ticker`, `returned_name` (from scoring tool), `expected_name` (from get_company_info), sector, overall score, key factor strengths; under `audience=client_safe`, factor-strength cells carry the §13.3 gloss; if view active, add "Tilt Effect" column; if `macro_context` present, add "Macro Tag" column showing `with-regime / against-regime / orthogonal`. **Flag any row where `returned_name ≠ expected_name` with ⚠ MISMATCH and exclude its scores from ranking** — per loader.md §5 rule 3. **Rank is composite-driven regardless of Macro Tag** — that column annotates, not sorts. Do NOT add a per-name Confidence column — telemetry is basket-level only and any per-row confidence would be hallucinated.)
- **Comparison Matrix** (peer comparison for lead candidate)
- **Financial Snapshot** (revenue, margins, growth for top 3 trusted picks)
- **Implementation Notes** (liquidity considerations, concentration/threshold arithmetic per conventions §12 — no position-sizing instructions; concentration/threshold arithmetic renders in internal_analyst mode only per §13.2)
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
