---
name: parallax-portfolio-checkup
description: "Individual investor portfolio checkup: health flags, factor scores, redundancy, macro context, and plain-language recommendations via Parallax MCP tools. Holdings as [{symbol, weight}]. NOT for fund manager briefs (use /parallax-morning-brief), not for client reviews (use /parallax-client-review)."
---

<!-- white-label: integration-pattern.md -->

# Portfolio Checkup

## When not to use

- Fund manager morning brief → use /parallax-morning-brief
- Client portfolio review (RIA) → use /parallax-client-review
- Single stock analysis → use /parallax-should-i-buy
- Portfolio with significant ETF allocation → equity scope only in v1; ETF holdings will fail V2 scoring and may silently mismap in V1. ETF-aware health-check is on the v2 roadmap; for now use /parallax-explain-portfolio (which handles ETFs via etf_profile pre-classification) for ETF-heavy portfolios.

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution (§1), symbol cross-validation (§2), parallel execution (§3), and fallback patterns (§4)
- JIT-load references/health-flags.md for the 5-flag health system, thresholds, and mixed-exchange fallback
- Holdings must be in RIC format with weights summing to ~1.0
- Per-holding `get_peer_snapshot` + `get_company_info` cross-validation is the primary scoring path (matches morning-brief V2 pattern). `quick_portfolio_scores` is the V1 fallback — known symbol-mapping bugs for non-US numeric tickers (HK / TW / KR), so retail portfolios with mixed exchanges silently mismap without the cross-validation gate.
- Mixed-exchange portfolios may have partial scoring coverage — apply split-and-merge fallback
- Plain language output — no finance jargon. Surface name mismatches in user-friendly terms ("Some holdings could not be verified") rather than technical jargon.
- JIT-load `_parallax/house-view/loader.md` if an active CIO view is present; this is a portfolio-level skill, so apply §3 (multipliers) to factor scoring of verified holdings, §4 (conflict resolution if user-stated preferences contradict view), §5 (preamble + view-aware sections), §6 (audit log). The view biases the recommendations in **Consider** — view-aligned tilts get implicit support; view-misaligned holdings get a gentle question framing. Health flags themselves are unchanged by the view; the view adds context, not a sixth flag.
- When active view is present, use the view-aware disclaimer per loader.md §5 rule 5; otherwise use the standard disclaimer.
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Plain-language portfolio health check with health flags for individual investors.

## Usage

```
/parallax-portfolio-checkup [{"symbol":"AAPL.O","weight":0.30},{"symbol":"MSFT.O","weight":0.25},{"symbol":"VZ.N","weight":0.20},{"symbol":"JNJ.N","weight":0.25}]
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. JIT-load `_parallax/parallax-conventions.md` for execution mode and fallback patterns. JIT-load `references/health-flags.md` for the health flag system.

### Pre-Workflow — Load Active House View

Per `_parallax/house-view/loader.md` §1 and §2: load and validate any active house view BEFORE running the workflow. If view present and validated, capture the load preamble (banner from `view_status` helper, low-confidence warnings) for rendering at the top of Output Format per §5.1. Capture the tilt vector + excludes — applied in Step A.5 to verified-holdings factor aggregates per §3. If no active view (or any §2 validation failure): run the workflow normally with the standard disclaimer.

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
   - **Mixed-exchange split-and-merge** — V1 coverage also < 50% → split holdings by exchange suffix, score each group, merge per the "Mixed-Exchange Fallback" section of `references/health-flags.md`. This is the last-resort path.

The cross-validation gate runs against whichever path is used, never bypassed.

**`get_company_info` retry / failure handling**: per conventions §4, retry once on first failure. If the second attempt also fails, the holding has no oracle for cross-validation — treat it as **unverified** and exclude it from aggregate factor calculations (same treatment as a ⚠ MISMATCH). Surface the holding in the Verification Note as "could not be verified — Parallax company-info lookup failed" so the user knows it was excluded for a different reason than mismatch.

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

If a view is active, after computing verified-holdings factor aggregates apply loader.md §3 multipliers (sector × factor) before mapping to plain-language interpretation. The plain-language descriptions of factor levels (high VALUE, etc.) describe the tilt-adjusted aggregate; the underlying raw factor scores per holding remain unchanged. Append the §6 audit log entry per loader.md §6.1.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format. The loader returns exactly six keys; any other access (e.g. `branding["voice"]`) raises `KeyError` — structurally enforced by `loader.py`.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** below, then run it through the **shared** render gate in **one Bash step** before replying. Use a private `mktemp` file (never a fixed/predictable path like `/tmp/pcheckup_draft.md` — that is a world-writable-`/tmp` symlink hazard). The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key with `--skill portfolio-checkup` (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/pcheckup.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill portfolio-checkup < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — nothing before it (no "composing", no step notes, no scratch computation), nothing after it.

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / Portfolio Health Status / Portfolio Checkup title). It preserves the active-house-view banner in **every** `view_status` state (active / warning / critical / not-yet-effective / expired) and hoists any async-degraded note rather than dropping it. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

## Output Format

**Begin the response immediately with the rendered report — no preamble.** Do not emit step-completion notes ("Step A.5 complete", "All data gathered", "Composing the checkup"), scratch computation tables, cross-validation status lines, or config-probe results ("white-label: config_not_found") before the report. All intermediate computation stays internal. When no house view and no white-label client are active (the default), the **first line of the output is the Portfolio Health Status header**, in this exact form:

`## Portfolio Health Status: <🟢|🟡|🔴> **<Healthy|Monitor|Attention>** — <N> of 5 flags raised`

(When a house view or white-label client is active, the House View Preamble / Branding Header precede this line per the rules below; the no-preamble rule still applies — those are rendered output, not internal scaffold.)

- **House View Preamble** (only if view active) — render per loader.md §5 rule 1 (banner from Pre-Workflow + low-confidence warnings). Per loader.md §5.1 the preamble goes at the very top — it precedes the Branding Header.
- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line immediately below the House View Preamble (or at the very top if no view): `**<client_name>** portfolio checkup`. Logo handling per integration-pattern.md §5: empty path → text only; URL → embed; absolute local (`/` or `~`) → skip embed and append `Logo on file: <basename>` to Provenance.
- **Portfolio Health Status** (Healthy/Monitor/Attention badge with flag count)
- **Verification Note** *(only render if any cross-validation mismatches were detected)* — plain-language note: "Some holdings (X out of N) could not be matched to verified data and were excluded from aggregate factor analysis: [list of symbols]. The remaining N-X holdings drive the scores below."
- **Your Portfolio Scorecard** (simple factor table with plain-language labels; flag indicators per holding. Mismatched holdings show "—" instead of scores.)
- **Health Flags** (each triggered flag explained in plain language — what it means, why it matters)
- **Verdict sensitivity** (render only when Health Status is Monitor or Attention — i.e. ≥ 1 flag triggered): the 1-2 nearest-boundary flags and their arithmetic flip condition, per `references/health-flags.md` "Verdict sensitivity" (renders `parallax-conventions.md` §11 by reference).
- **Overlap Alert** (if redundancy found, explain why; include reliability note if coverage <60%)
- **Macro Context** (2-3 sentences on relevant economic environment — skip if no covered markets)
- **What This Means** (2-3 plain-language paragraphs)
- **Consider** (suggestions prioritized by flag severity, framed as questions not directives; if view active, suggestions reflect view alignment — view-aligned tilts get implicit support, view-misaligned holdings get gentle question framing per loader.md §3-§4)
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7 markdown column (render per table; do not collapse). If a logo was skipped per the Branding Header rule, append `Logo on file: <basename>` as a second Provenance line.

Keep tone friendly and educational.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

If active view: use the view-aware disclaimer per loader.md §5 rule 5. Otherwise: render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
