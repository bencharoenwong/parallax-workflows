---
name: parallax-portfolio-checkup
description: "Individual investor portfolio checkup: health flags, factor scores, redundancy, macro context, and plain-language recommendations via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for client reviews (use /parallax-client-review)."
negative-triggers:
  - Fund manager morning brief → use /parallax-morning-brief
  - Client portfolio review (RIA) → use /parallax-client-review
  - Single stock analysis → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/parallax-conventions.md for fallback patterns and parallel execution
  - JIT-load _parallax/house-view/loader.md FIRST; if active view present, follow §2 (validation), §3 (multipliers), §4 (conflict resolution), §5 (output rendering), §6 (audit). Rules 3 (ground-truth panel) and 4 (divergence assertion) in §5 apply UNIVERSALLY (view or no view — data-integrity requirements).
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
  - JIT-load references/health-flags.md for the 5-flag health system, thresholds, and mixed-exchange fallback
  - Holdings must be in RIC format with weights summing to ~1.0
  - Mixed-exchange portfolios may have partial scoring coverage — apply split-and-merge fallback
  - Plain language output — no finance jargon
---

# Portfolio Checkup

Plain-language portfolio health check with health flags for individual investors.

## Usage

```
/parallax-portfolio-checkup [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"VZ.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation and universal data-integrity rules. JIT-load `references/health-flags.md` for the health flag system.

### Batch 0 — Load Active House View (before Batch A)

Per `loader.md` §1-§2. If view present, capture tilt vector + excludes. If validation fails or no view present, run without view — but rules 3 and 4 in loader.md §5 still apply universally (data-integrity).

### Batch A — Fire scoring + macro calls in parallel

**Path selection first (per conventions §0 — choose exactly ONE scoring path, never fire both):**

- **V2 path** (active view, multi-sector exposure, or per-holding rendering — checkup renders per-holding flags, so V2 is typical): add `get_peer_snapshot` per holding + `get_company_info` per holding. Do NOT call `quick_portfolio_scores`.
- **V1 path** (no view AND portfolio-level aggregate only AND single-sector exposure): add `quick_portfolio_scores` once + `get_company_info` per holding. Do NOT call `get_peer_snapshot` on this path.

Then fire Batch A in parallel. Common calls (both paths):

| Tool | Parameters | Notes |
|---|---|---|
| `check_portfolio_redundancy` | `holdings` | Overlap detection |
| `list_macro_countries` | — | Check which markets are covered |

Path-specific calls:

| Tool | Path | Parameters | Notes |
|---|---|---|---|
| `get_peer_snapshot` | **V2 only** | per holding | Aggregate client-side per loader.md §3b. |
| `get_company_info` | V1 + V2 | per holding | Ground-truth panel oracle per loader.md §5 rule 3 — records `expected_name`. |
| `quick_portfolio_scores` | **V1 only** | `holdings` | Legacy batch path. Forbidden when any V2 selection rule fires. |

**After Batch A**: per loader.md §5 rule 3, cross-reference returned names against `get_company_info` names. On V2, any mismatch in `get_peer_snapshot` is flagged ⚠ MISMATCH and excluded from aggregates. On V1, any mismatch in `quick_portfolio_scores` is re-scored individually via `get_peer_snapshot`.

### Batch B — Macro context (after Batch A)

Derive home markets from RIC suffixes across holdings. Call `macro_analyst` with component="tactical" for each unique covered market (cap at 3).

### Batch C — Health flag evaluation

Per `references/health-flags.md`, evaluate all 5 flags:

1. **Low Score** — Overall ≤ 5.0?
2. **Concentration** — Any single holding >15%? Top-3 >45%?
3. **Redundancy** — ≥ 2 redundant pairs? (flag as low-confidence if coverage <60%)
4. **Value Trap** — Portfolio value score ≤ 3.0?
5. **Macro Misalignment** — Overweight in sectors flagged unfavourable?

If `quick_portfolio_scores` coverage <50%: execute mixed-exchange fallback (split by exchange, re-score, merge).

Assign health status: **Healthy** (0 flags) · **Monitor** (1-2) · **Attention** (3+)

### Step 4 — Interpret in plain language

Explain scores and flags in plain terms:
- High VALUE = tilts toward cheaper stocks
- High QUALITY = strong balance sheets and profitability
- High MOMENTUM = stocks with recent price strength
- High DEFENSIVE = lower volatility, stable businesses

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble)
- **Ground-truth Integrity** (only render if any mismatch detected — table: `input_ticker`, `returned_name`, `expected_name`, status. Mismatched holdings had scores re-derived via `get_peer_snapshot` — per loader.md §5 rule 3.)
- **Portfolio Health Status** (Healthy/Monitor/Attention badge with flag count)
- **Your Portfolio Scorecard** (simple factor table with plain-language labels; flag indicators per holding; scores aggregated over TRUSTED holdings only)
- **Health Flags** (each triggered flag explained in plain language — what it means, why it matters)
- **Overlap Alert** (if redundancy found, explain why; include reliability note if coverage <60%)
- **Macro Context** (2-3 sentences on relevant economic environment — skip if no covered markets)
- **What This Means** (2-3 plain-language paragraphs)
- **Consider** (suggestions prioritized by flag severity, framed as questions not directives)

Append audit log entry per loader.md §6.

Keep tone friendly and educational.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
