---
name: parallax-client-review
description: "RIA/wealth advisor client portfolio review: full analysis, redundancy, health flags, macro context, per-holding drill-down, prioritized recommendations, and AI assessment via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for quick stock checks (use /parallax-should-i-buy)."
negative-triggers:
  - Fund manager morning brief → use /parallax-morning-brief
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). The view shapes the suitability assessment AND the recommendations: holdings misaligned with view get higher priority for trimming, view-aligned holdings get implicit support.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
  - JIT-load references/recommendation-matrix.md for priority classification and drill-down criteria
  - Holdings in RIC format, weights sum to ~1.0
  - analyze_portfolio called twice — once with lens "performance", once with "concentration". WARNING: responses often exceed 180K chars (daily time series). If output is truncated or too large, fall back to `check_portfolio_redundancy` (concentration) + `quick_portfolio_scores` (factor tilt) + individual `get_stock_outlook` with aspect "risk_return" (performance)
  - Per-holding drill-down capped at 8 holdings to manage latency
  - Mixed-exchange portfolios may need split scoring (see shared conventions)
  - Output should be presentation-ready for client meetings
  - get_assessment prompt should incorporate all findings including macro, flags, and recommendations
---

# Client Portfolio Review

Presentation-ready portfolio review with health flags and prioritized recommendations for wealth advisors.

## Usage

```
/parallax-client-review [{"symbol":"AAPL.O","weight":0.25},{"symbol":"BRK-B.N","weight":0.20}] client="conservative retiree, income focus, 10yr horizon" benchmark=SPY.O
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode, fallback patterns, and macro reasoning. JIT-load `_parallax/house-view/loader.md` for active-view validation and integration. JIT-load `references/recommendation-matrix.md` for priority system.

### Batch 0 — Load Active House View (before Batch A)

Per `loader.md` §1-§2. If view present, capture tilt vector, excludes, basis_statement (used to frame Suitability Assessment in firm voice). The view's tilts become an additional layer of recommendation justification: when trimming, "view tilts UW [sector]" is cited alongside health flags. If validation fails or no view present, run review without view.

### Batch A — Portfolio-level analysis (parallel)

| Tool | Parameters | Notes |
|---|---|---|
| `analyze_portfolio` | `holdings`, lens="performance" | Returns/risk metrics |
| `analyze_portfolio` | `holdings`, lens="concentration" | Concentration analysis |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `get_peer_snapshot` | per holding | **Primary scoring source** (V2 path — mandatory when view active, default for multi-sector queries, per conventions §0 selection logic). Aggregate scores client-side per loader.md §3b. |
| `get_company_info` | per holding (parallel) | **Ground-truth oracle** per loader.md §5 rule 3 (required universally). Records `expected_name`. |
| `list_macro_countries` | — | Check market coverage |
| `quick_portfolio_scores` | `holdings` | **Legacy/V1 path only**. Do NOT use when V2 selection logic (conventions §0) applies — i.e., any active view, multi-sector queries, or per-holding score rendering. |

**After Batch A**: cross-check returned names against `get_company_info` names per loader.md §5 rule 3. For `PARALLAX_LOADER_V2=1`, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregate calculations. For V1, any mismatch in `quick_portfolio_scores` is re-scored individually and flagged as UNTRUSTED for the batch factor profile.

### Batch B — Macro context (after Batch A)

Derive home markets from RIC suffixes. Call `macro_analyst` with component="tactical" for each unique covered market (cap 3).

### Batch C — Health flags + drill-down (after A + B)

1. Evaluate 5 health flags per holding: Low Score (≤5.0), Concentration (>15%), Redundancy (≥2 pairs), Value Trap (value ≤3.0), Macro Misalignment.
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

## Output Format

Client-ready report:
- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble)
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

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
