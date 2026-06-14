---
name: parallax-client-review
description: "RIA/wealth advisor client portfolio review: full analysis, redundancy, health flags, macro context, per-holding drill-down, prioritized recommendations, and AI assessment via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for quick stock checks (use /parallax-should-i-buy)."
---

<!-- white-label: integration-pattern.md -->

# Client Portfolio Review

## When not to use

- Fund manager morning brief → use /parallax-morning-brief
- Single stock analysis → use /parallax-should-i-buy

## Gotchas

- JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
- JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). The view shapes the suitability assessment AND the recommendations: holdings misaligned with view get higher priority for trimming, view-aligned holdings get implicit support.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
- JIT-load references/recommendation-matrix.md for priority classification and drill-down criteria
- Holdings in RIC format, weights sum to ~1.0
- analyze_portfolio called twice — once for performance/returns fields, once for concentration/attribution fields (split to manage response size). **Required call shape:** `portfolio=[{date: <today ISO>, symbol: <ric>, weight: <w>}, ...]` with `fields=[...]`. The parameters `holdings` and `lens` do not exist in the deployed schema. **Fallback** (on MCP schema validation error OR truncated/oversized response): `check_portfolio_redundancy` (concentration) + `quick_portfolio_scores` (factor tilt) + individual `get_stock_outlook` with `aspect="risk_return"` (performance).
- Per-holding drill-down capped at 8 holdings to manage latency
- Mixed-exchange portfolios may need split scoring (see shared conventions)
- Output should be presentation-ready for client meetings
- get_assessment prompt should incorporate all findings including macro, flags, and recommendations
- Pre-Render step loads white-label branding via `_parallax/white-label/loader.py` → `load_visual_branding()` (the 6-key visual subset wrapper). Voice/typography/etc. are structurally absent from the returned dict — `branding["voice"]` raises `KeyError`. Provenance state-to-text mapping and Branding Header semantics follow `_parallax/white-label/integration-pattern.md` §5 + §7 — that doc is the canonical specification; client-review's Output Format bullets reference it rather than reproducing the table.
- Branding Header uses `**<client_name>** portfolio review` (skill-specific framing), not the generic `**<client_name>** report` template in integration-pattern.md §5. Intentional divergence — do not "fix" to match the generic template.

Presentation-ready portfolio review with health flags and prioritized recommendations for wealth advisors.

## Usage

```
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] client="conservative retiree, income focus, 10yr horizon"
```

**Note on `benchmark=` parameter.** The current workflow body does NOT consume a `benchmark=` parameter — the example above intentionally omits it. If a future revision adds benchmark-relative attribution: pass benchmarks as **plain ETF tickers** (e.g., `SPY`, `QQQ`, `EWJ`) and route through `etf_daily_price` — NOT `export_price_series`. The two endpoints are separate. Equity tickers (with RIC suffix like `.O` or `.N`) go through `export_price_series`; ETFs (plain ticker) go through `etf_daily_price`. Mixing them silently fails-empty.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and integration. JIT-load `references/recommendation-matrix.md` for priority system.

### Batch 0 — Tool Loading & Active House View

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Per `loader.md` §1-§2. If view present, capture tilt vector, excludes, basis_statement (used to frame Suitability Assessment in firm voice). The view's tilts become an additional layer of recommendation justification: when trimming, "view tilts UW [sector]" is cited alongside health flags. If validation fails or no view present, run review without view.

### Batch A — Portfolio-level analysis (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `portfolio=[{date: <today ISO>, symbol: <ric>, weight: <w>}]`, `fields=["performance_metrics","rolling_metrics","drawdown_analysis","portfolio_summary","time_period_returns"]` | Returns/risk metrics. Build portfolio array from provided holdings; use today's date as as-of date (point-in-time review). |
| `analyze_portfolio` | `portfolio=[{date: <today ISO>, symbol: <ric>, weight: <w>}]`, `fields=["concentration_metrics","sector_allocation","company_contribution"]` | Concentration and attribution analysis. Two separate calls with distinct field subsets to stay under the 180K-char response ceiling. |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `get_peer_snapshot` | per holding | **Primary scoring source** for `PARALLAX_LOADER_V2=1`. Aggregate scores client-side per `loader.md` §3b. |
| `get_company_info` | per holding (parallel) | **Ground-truth oracle** per loader.md §5 rule 3 (required universally). Records `expected_name`. |
| `list_macro_countries` | — | Check market coverage |
| `quick_portfolio_scores` | `holdings` | **Legacy/V1 path only**. Do NOT use if `PARALLAX_LOADER_V2=1` and view active. |

**After Batch A**: cross-check returned names against `get_company_info` names per loader.md §5 rule 3. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. For V1, any mismatch in `quick_portfolio_scores` is re-scored individually and flagged as UNTRUSTED for the batch factor profile.

### Batch B — Macro context (after Batch A)

Derive home markets from RIC suffixes. Call `macro_analyst` with component="tactical" for each unique covered market (cap 3).

### Batch C — Health flags + drill-down (after A + B)

1. Evaluate the 5 health flags **per holding** — binding flag conditions in `references/recommendation-matrix.md` (same taxonomy and threshold values as `parallax-portfolio-checkup/references/health-flags.md`, whose canonical portfolio-level weighted-average definitions apply to portfolio-checkup, not here): Low Score (holding total score ≤5.0), Concentration (holding weight >15%, or holding among the top-3 when their combined weight >45%), Redundancy (holding is part of a redundant pair), Value Trap (holding value score ≤3.0), Macro Misalignment (holding's sector has a negative tactical outlook). Per-holding flag counts drive priority and drill-down selection.
2. **House-view alignment** (if view active): add View Misalignment (>25% off view-tilted target) and View Excluded (on tilts.excludes) as additional flags. Surface a portfolio-level "view alignment score" (% of weight in view-aligned positions).
3. Flag redundancy as low-confidence if coverage <60%.
4. Assign health status: **Healthy** (0) · **Monitor** (1-2) · **Attention** (3+). View Excluded counts as Attention regardless of other flags.
5. Select up to 8 holdings for drill-down per `references/recommendation-matrix.md`: weight >10%, any flag (including View flags), or macro-misaligned. Prioritize by flag count then weight.

For each drill-down holding (parallel):

| Tool | Parameters |
|---|---|
| `get_score_analysis` | `symbol`, `weeks` as int 26 (26-week lookback, non-default — see conventions §0.2) |
| `get_stock_outlook` | `symbol`, `aspect="risk_return"` |
| `get_peer_snapshot` | `symbol` |

**Ground-truth re-verification per drill-down holding** (per loader.md §5 rule 3): cross-check `get_peer_snapshot.target_company` against the `get_company_info.name` already captured in Batch A. If mismatch at drill-down time (can occur when the Batch A and Batch C queries bind differently), flag ⚠ MISMATCH and extract the queried stock's scores from `get_peer_snapshot.peer_list[]` by symbol match, not from the target_company field.

News (selective, async): `get_news_synthesis` for holdings >10% weight AND flagged, or in sectors with active macro developments. Cap at 5.

### Batch D — Recommendations + Assessment (after A + B + C)

1. Per `references/recommendation-matrix.md`, assign each flagged holding a priority (High/Medium/Low) and action type (trim/exit/hold/investigate/reweight). Every recommendation must cite a specific finding. View Excluded → Exit (priority High). View Misalignment → Trim or Reweight (priority Medium unless paired with other flags).
2. Call `get_assessment` with comprehensive prompt incorporating: portfolio composition, factor scores, health flags (including View flags), macro context, per-holding drill-down findings, recommendations, client context, AND active house view (basis_statement + tilt vector + excludes if present).
3. Append audit log entry per loader.md §6.

### Pre-Render — Load white-label branding

Before composing the Output Format, JIT-load `_parallax/white-label/integration-pattern.md` and call `load_visual_branding()` per §2. The loader returns exactly six keys: `client_name`, `colors`, `logos`, `fonts`, `source`, `error`. Set `white_label_active = is_white_label_active(branding)` and `client_name = branding.get("client_name", "")` for use in the Branding Header. See §4 (error states), §5 + §6 (substitution semantics), §7 (Provenance template). Any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`. Apply §5 + §7 when composing the Output Format below.

`white_label_active` is the rendering flag. `client_name` may be `""` on legacy configs — tolerate without erroring (skip the Branding Header in that case per integration-pattern.md §5).

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** below, then run it through the shared render gate in **one Bash step** before replying. Use a private `mktemp` file (never a fixed/predictable path — `/tmp` symlink hazard). The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/clientrev.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill client-review < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — nothing before it (no step/batch-completion notes, no scratch computation, no "no active house view" / white-label config-probe narration), nothing after it.

**Degraded-state rule:** if an async tool (e.g. `get_assessment`, `get_news_synthesis`) times out or returns no data, render the pending/unavailable note INSIDE the relevant section or the Provenance line — NOT as a preamble above the report — so it is part of the rendered body and survives the gate. (The gate also hoists a leaked degraded note as a backstop.)

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / this skill's title or first rendered section), preserving the active-house-view banner in every `view_status` state. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

## Output Format

Client-ready report:
- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble). Per loader.md §5.1, the load preamble goes "at the very top" — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view active): `**<client_name>** portfolio review`. For the logo: if `branding["logos"]["primary"]` is empty (`""`, e.g., on the `logo_missing` partial-success path), render the text line only — no image, no extra Provenance note. If it is a URL (starts with `http://` / `https://`), embed `![<client_name>](<url>)` above the text line. If it starts with `/` or `~` (absolute local path, not embeddable in chat-delivered markdown per integration-pattern.md §5), skip the image embed and append `Logo on file: <basename>` as a second Provenance line.
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status. Mismatched holdings had scores re-derived via `get_peer_snapshot` symbol-match — per loader.md §5 rule 3.)
- **Portfolio Summary** (AUM breakdown, sector allocation, top 5 holdings; if view active, view-alignment score)
- **Health Status** (Healthy/Monitor/Attention badge with flag summary)
- **Performance vs Benchmark** (key metrics)
- **Factor Analysis** (scores with macro context interpretation for this client type; if view active, compare against view-target factor)
- **Concentration & Redundancy** (flagged issues; coverage reliability note if applicable)
- **House View Alignment** (only if view active) — table of view tilt direction vs current portfolio exposure per sector/region/factor; flagged misalignments
- **Per-Holding Analysis** (for drill-down holdings: score trend, risk profile, flags, news highlights; view conflicts called out)
- **Suitability Assessment** (alignment with client goals AND with active house view if present; cite basis_statement)
- **Recommended Actions** (prioritized High/Medium/Low per recommendation-matrix.md, with specific action types; rationale cites view tilts where applicable)
- **Appendix: Methodology** (brief Parallax scoring note)
- **Provenance** (always present): one line stating branding state. Format is the markdown column of integration-pattern.md §7 (render per table; do not collapse) so `schema_unavailable` correctly stays in the white-label branch rather than falling back to default Parallax. If a logo was skipped per the Branding Header rule above, append `Logo on file: <basename>` as a second Provenance line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
