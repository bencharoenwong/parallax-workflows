---
name: parallax-portfolio-checkup
description: "Individual investor portfolio checkup: health flags, factor scores, redundancy, macro context, and plain-language recommendations via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for client reviews (use /parallax-client-review)."
negative-triggers:
  - Fund manager morning brief → use /parallax-morning-brief
  - Client portfolio review (RIA) → use /parallax-client-review
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution (§1), symbol cross-validation (§2), parallel execution (§3), and fallback patterns (§4)
  - JIT-load references/health-flags.md for the 5-flag health system, thresholds, and mixed-exchange fallback
  - Holdings must be in RIC format with weights summing to ~1.0
  - Per-holding `get_peer_snapshot` + `get_company_info` cross-validation is the primary scoring path (matches morning-brief V2 pattern). `quick_portfolio_scores` is the V1 fallback — known symbol-mapping bugs for non-US numeric tickers (HK / TW / KR), so retail portfolios with mixed exchanges silently mismap without the cross-validation gate.
  - Mixed-exchange portfolios may have partial scoring coverage — apply split-and-merge fallback
  - Plain language output — no finance jargon. Surface name mismatches in user-friendly terms ("Some holdings could not be verified") rather than technical jargon.
---

# Portfolio Checkup

Plain-language portfolio health check with health flags for individual investors.

## Usage

```
/parallax-portfolio-checkup [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"VZ.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `references/health-flags.md` for the health flag system.

### Batch 0 — Tool Loading

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Batch A — V2 scoring + redundancy + market coverage (parallel)

**Fire ALL rows below in a single tool-call turn.** Every row is independent. For per-holding rows (`get_peer_snapshot`, `get_company_info`), fan out one call per holding **within the same turn** so all N×2 holding-level calls run concurrently with the portfolio-level calls. Sequential per-holding loops are the largest latency leak in this skill — do not introduce one.

| Tool | Parameters | Notes |
|---|---|---|
| `get_peer_snapshot` | per holding — **all N calls fan out in parallel within Batch A** | **Primary scoring source** (V2 path). Aggregate factor scores client-side. |
| `get_company_info` | per holding — **all N calls fan out in parallel within Batch A** | **Ground-truth name oracle** for cross-validation per conventions §2. Records `expected_name` to cross-check against `get_peer_snapshot.target_company`. |
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `list_macro_countries` | — | Check which markets are covered |

`quick_portfolio_scores` is **NOT** fired in Batch A. It is reserved for the V1 fallback path in Step A.5 below; firing it unconditionally violates conventions §2 (V1 known to silently mismap symbols for non-US numeric tickers) and would consume tokens for output that the V2 path supersedes.

### Step A.5 — Cross-validation gate + fallback decision (sequential, MUST complete before Batch B)

This step gates Batch B and Batch C; do not start them until A.5 is complete.

1. **Cross-validation** (per conventions §2): for each holding, compare `get_peer_snapshot.target_company` (or its `name` field) against `get_company_info.name`. Mismatches are flagged ⚠ MISMATCH and **excluded from aggregate factor calculations**; their per-position scores are not displayed.
2. **Compute V2 coverage**: weight share of holdings that returned non-empty `get_peer_snapshot` AND passed cross-validation.
3. **Fallback ladder** — apply the first tier whose precondition holds:
   - **V2 (primary)** — V2 coverage ≥ 50% → use V2-aggregated scores; do NOT fire V1.
   - **V1 fallback** — V2 coverage < 50% → fire `quick_portfolio_scores` once; cross-validate its returned names against the **already-cached** `get_company_info.name` from Batch A (do NOT re-fire `get_company_info`); mismatched V1 holdings are re-scored individually via `get_peer_snapshot`.
   - **Mixed-exchange split-and-merge** — V1 coverage also < 50% → split holdings by exchange suffix, score each group, merge per `references/health-flags.md` §4. This is the last-resort path.

The cross-validation gate runs against whichever path is used, never bypassed.

### Batch B — Macro context (after Step A.5)

Derive home markets from RIC suffixes across **verified, non-mismatched** holdings (the set Step A.5 cleared). Call `macro_analyst` with component="tactical" for each unique covered market (cap at 3).

### Batch C — Health flag evaluation (after Step A.5)

Per `references/health-flags.md`, evaluate all 5 flags using the verified-holdings factor scores produced by Step A.5. All "portfolio aggregate" calculations below are computed over the verified set only — mismatched holdings are excluded.

1. **Low Score** — Portfolio overall (verified-holdings weighted average) ≤ 5.0?
2. **Concentration** — Any single holding >15%? Top-3 >45%? (computed over original holdings, not just verified — concentration is a structural property)
3. **Redundancy** — ≥ 2 redundant pairs? (flag as low-confidence if `check_portfolio_redundancy` coverage <60%)
4. **Value Trap** — Portfolio value score (verified-holdings weighted average) ≤ 3.0?
5. **Macro Misalignment** — Overweight in sectors flagged unfavourable in Batch B?

Assign health status: **Healthy** (0 flags) · **Monitor** (1-2) · **Attention** (3+)

### Step 4 — Interpret in plain language

Explain scores and flags in plain terms:
- High VALUE = tilts toward cheaper stocks
- High QUALITY = strong balance sheets and profitability
- High MOMENTUM = stocks with recent price strength
- High DEFENSIVE = lower volatility, stable businesses

## Output Format

- **Portfolio Health Status** (Healthy/Monitor/Attention badge with flag count)
- **Verification Note** *(only render if any cross-validation mismatches were detected)* — plain-language note: "Some holdings (X out of N) could not be matched to verified data and were excluded from aggregate factor analysis: [list of symbols]. The remaining N-X holdings drive the scores below."
- **Your Portfolio Scorecard** (simple factor table with plain-language labels; flag indicators per holding. Mismatched holdings show "—" instead of scores.)
- **Health Flags** (each triggered flag explained in plain language — what it means, why it matters)
- **Overlap Alert** (if redundancy found, explain why; include reliability note if coverage <60%)
- **Macro Context** (2-3 sentences on relevant economic environment — skip if no covered markets)
- **What This Means** (2-3 plain-language paragraphs)
- **Consider** (suggestions prioritized by flag severity, framed as questions not directives)

Keep tone friendly and educational.

> *"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
