---
name: parallax-thematic-screen
description: "Thematic stock screen: build a universe from natural language, score top picks, compare peers, and check financials via Parallax MCP tools. NOT for single stock analysis (use /parallax-should-i-buy), not for portfolio review (use /parallax-client-review)."
negative-triggers:
  - Single stock analysis → use /parallax-should-i-buy
  - Portfolio review → use /parallax-client-review
  - Peer comparison of known stock → use /parallax-peer-comparison
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - JIT-load _parallax/house-view/loader.md FIRST. Rules 3 (ground-truth panel) and 4 (divergence assertion) in §5 apply UNIVERSALLY (view or no view — data-integrity requirements). Rules 1-2 and 5 apply when a view is active. Multi-sector theme queries can collapse to a single sector — divergence assertion must fire regardless of view. The user-supplied theme is sovereign per §4 — render conflict banner if theme contradicts view tilts.
  - When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer
  - build_stock_universe searches ~65K company descriptions by semantic similarity
  - Default top_n is 5 — adjust for broader or narrower screens
  - get_peer_snapshot called once per top pick (N calls) — fire in parallel
  - get_financials called for top 3 only
---

# Thematic Screen

Discover investment opportunities by theme using Parallax's semantic universe builder.

## Usage

```
/parallax-thematic-screen "AI infrastructure companies"
/parallax-thematic-screen "clean energy utilities" top_n=10
/parallax-thematic-screen "gene therapy pure plays"
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `_parallax/house-view/loader.md` for active-view validation and conflict resolution.

### Phase A — Setup (parallel, ~2–3 tokens)

Fire both in parallel:

1. **Load Active House View** — Per `loader.md` §1-§2. If view present, capture tilt vector + excludes. Resolve user theme vs view per §4: theme is sovereign, but conflicts surface as banners (e.g., theme="AI infrastructure" + view says `tech: -2` → screen runs as requested with "House view is UW tech; screen run per your explicit theme" banner).
2. **Build Universe** — Resolve user theme vs. view per loader.md §4. If view present AND `PARALLAX_LOADER_V2=1`, follow `loader.md` §3 "Application (V2)": decompose tilts into parallel per-sector calls, merge, and dedupe. If V1, prepend tilt context to the query and call `build_stock_universe` once. Filter results against `tilts.excludes`.

**After Phase A:** Proceed to Phase B with completed universe.

### Phase B — Inline Validation (no new tool calls)

3. **Divergence assertion** (per loader.md §5 rule 4 — required universally, view or no view) — REQUIRED for V1 paths. If the query named N≥2 sectors/themes, compute `max_sector_share / total` in returned candidates. If > 0.6, emit fail-loud warning: "universe collapsed to single sector despite multi-sector request." If `PARALLAX_LOADER_V2=1`, the divergence assertion is used to verify the merge quality but is less likely to trigger a hard failure.
4. **Apply freeform excludes** — if view active and `tilts.excludes_freeform` non-empty (per loader.md §3 "Free-form excludes handling"), drop candidates matching any pattern against `get_company_info` name/description/sector.

**After Phase B:** Proceed to Phase C with validated universe.

### Phase C — Scoring & Analytics (parallel, ~3–4 tokens)

Fire all three in parallel:

**C1. Ground-truth check + Score Top Picks** (per loader.md §5 rule 3 — required universally) — For the top N results, call `get_peer_snapshot` AND `get_company_info` per candidate in parallel. Record `returned_name` (snapshot `target_company`) and `expected_name` (info `name`). Treat any row where `returned_name ≠ expected_name` as UNTRUSTED (do not rank, flag ⚠ MISMATCH). If view active, re-rank trusted rows by `composite × multiplier(holding's sector)` per loader.md §3.

**C2. Compare Peers** — For the highest-scored TRUSTED stock, call `export_peer_comparison` with format "json".

**C3. Quick Financials** — For the top 3 trusted picks, call `get_financials` with statement "summary". Append audit log entry per loader.md §6.

## Output Format

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (preamble)
- **Theme: [theme]** (brief investment thesis; note view conflict inline if applicable)
- **Universe Built** (how many stocks found, key sectors; note any exclusions applied; surface divergence-assertion result per loader.md §5 rule 4)
- **Top Picks** (table: `input_ticker`, `returned_name` (from scoring tool), `expected_name` (from get_company_info), sector, overall score, key factor strengths; if view active, add "Tilt Effect" column. **Flag any row where `returned_name ≠ expected_name` with ⚠ MISMATCH and exclude its scores from ranking** — per loader.md §5 rule 3.)
- **Comparison Matrix** (peer comparison for lead candidate)
- **Financial Snapshot** (revenue, margins, growth for top 3 trusted picks)
- **Implementation Notes** (liquidity considerations, position sizing guidance)

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise:

> These are analytical outputs based on Parallax factor scores, not investment advice.
