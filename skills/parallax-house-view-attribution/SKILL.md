---
name: parallax-house-view-attribution
description: "Ex-post house-view performance attribution: did the active (or an archived) view add value over its effective window? Reconstructs the tilted-vs-neutral portfolio decision from the reasoning-chain archive, fetches realized returns via Parallax MCP tools, and decomposes the active return into per-tilt-group contributions (Shapley) plus a selection residual. Read-only against the view; emits a report bundle and one `attribution` audit row. NOT for forward-looking drift monitoring (use /parallax-judge-house-view), not for internal-consistency checks (use /parallax-stress-house-view), not for single-period LP letters (use /parallax-cio-letter-prep), not for drawdown decomposition of an arbitrary portfolio (use /parallax-explain-portfolio)."
---

# House View Attribution

## When not to use

- Is the view stale vs current signals? → use /parallax-judge-house-view
- Is the view internally consistent? → use /parallax-stress-house-view
- LP letter with period attribution → use /parallax-cio-letter-prep
- "Why is my portfolio down?" → use /parallax-explain-portfolio
- Ex-ante "did the view change the output at all?" → the paired-leg protocol in /parallax-house-view-diff

## Gotchas

- READ-ONLY against the view: never writes view.yaml / prose.md / provenance.yaml. Output is one report bundle + one `action="attribution"` audit row (`applied=false` ALWAYS) via `audit_chain.append_entry`.
- JIT-load `_parallax/house-view/loader.md` §6 for the `attribution` action's conditional fields (`attributed_view_id`, `attributed_version_id`, `attribution_window`, `attribution_summary`, `report_hash`).
- Reconstruction source is the reasoning-chain archive (`~/.parallax/reasoning-chains/`), NOT audit.jsonl — §6.3 forbids holdings arrays on audit rows, so consume rows carry no weights. If consumer runs emitted no chains in the window, coverage is honestly zero: report "N of M chains usable; cannot attribute" rather than inventing a portfolio.
- "Neutral" is pinned as *same holdings, all loader.md §3 weight multipliers at 1.00×* (score-proportional when per-holding base scores are recoverable, else equal-weight tagged `approximate`). It is NOT a market benchmark — do not substitute one; that would make the number unfalsifiable against the view's actual decision surface.
- `export_price_series` is trailing-365-days only (no start/end anchor). Windows starting >365 days ago: refuse with "window start > 365 days ago — export_price_series cannot reach it; attribute a sub-window or archive prices externally."
- A single-window ex-post diff is directional evidence, NOT statistical validation. Render the §5.1a heuristic_phase0 calibration disclosure verbatim in the report and never claim significance. Promotion to `empirical_phase1` is a signed-manifest operator action (the manifest cites this run's `report_hash` as `backtest_ref`) — this skill never touches `calibration_status`.
- Factor and style tilts affect composite re-ranking / universe filtering, not weight multipliers — their effect lands in `selection_residual_bps` by construction. Say so in the report; do not fold the residual into a tilt group.
- The reference portfolio is whatever the chains recorded — do not let the caller cherry-pick a subset of chains without recording the exclusion in the report ("chains_used" vs chains found).

## Usage

```
/parallax-house-view-attribution                       # attribute the active view over its effective window
/parallax-house-view-attribution --view <view_id>      # attribute an archived view (from .archive/)
/parallax-house-view-attribution --window 2026-04-01 2026-06-30   # explicit sub-window
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas. JIT-load `_parallax/house-view/loader.md` (§6 audit format) and this skill's `attribution.py` (pure math layer — all reconstruction, counterfactual, and Shapley logic lives there; do not re-derive it inline).

### Phase 0 — Resolve target view + window

Default: the active view (`~/.parallax/active-house-view/view.yaml`, validated per loader.md §2 — an expired view is still attributable; validation here is integrity, not applicability). With `--view <view_id>`: resolve from `.archive/<view_id>-<version_id>/` (latest version unless one is named). Window = `[effective_date, min(valid_through_or_computed_expiry, today)]`, clipped by `--window`. Refuse windows starting >365 days ago (export_price_series limit).

### Phase 1 — Gather chains

`attribution.load_window_chains(view_id, window_start, window_end)`. Cross-check against `audit.jsonl` consume rows (count of `applied=true` consumes in-window vs chains found) and report the coverage fraction. Zero usable chains → halt with `InsufficientProvenance` message; append the audit row with `attribution_summary.segments = 0` and a `notes` explanation.

### Phase 2 — Segment by version

`attribution.segment_by_version(chains)` — a view superseded mid-window is attributed per-segment and summed. Note each segment's version_id in the report.

### Phase 3 — Market data (MCP)

For every holding across segments: `export_price_series` (total-return closes — same TR convention as parallax-cio-letter-prep; never mix raw closes) over each segment's sub-window; compute per-holding period returns. `analyze_portfolio` on the chain weights is the server-side cross-check when available — flag if local math diverges materially, mirroring the cio-letter-prep canonical-server rule. Classify each holding via `get_peer_snapshot` / `get_company_info` into schema keys (`sector`, `region`, `themes`) for `holding_meta`; unclassifiable holdings get multiplier 1.0 (their effect lands in the residual — never guess a sector). Holdings with no price data are dropped with weights renormalized (§3b partial-result semantics) and counted in `holdings_dropped`.

### Phase 4 — Attribute

Per segment: `attribution.attribute_segment(chain, returns, holding_meta)` (uses the latest chain per segment as the decision record; note in the report when a segment had multiple chains and which was used — or attribute each chain and average, stating the choice). Then `attribution.merge_segments(...)` for the run-level summary: tilted-vs-neutral active bps, per-tilt-group Shapley contributions, selection residual, counterfactual quality.

### Phase 5 — Render + audit

Write the bundle to `~/.parallax/attribution-reports/<view_id>-<window_start>_<window_end>-<6-char-nonce>/` (dir `0700`, files `0600`):
- `report.md` — evidence-shaped: window + segments table, per-tilt contribution table (group, bps, direction vs the tilt's intent), selection residual with its explanation, coverage/drops, counterfactual quality, and the §5.1a calibration disclosure verbatim.
- `report.json` — the `attribution_summary` object plus per-segment detail.
- `audit_entry.json` — copy of the appended row.

Compute `report_hash = sha256(report.md bytes)`. Append ONE audit row per loader.md §6 via `audit_chain.append_entry`: `action="attribution"`, `applied=false`, `attributed_view_id`, `attributed_version_id`, `attribution_window`, `attribution_summary` (with `reference_portfolio_hash` = sha256 of the sorted chain run_ids used, and `chains_used`), `report_hash`. Emit a reasoning chain via `chain_emit.emit_phase_0_chain` (`skill_version="parallax-house-view-attribution@1.0.0"`, `final_portfolio={"weights": {}}`).

## Output Format

Lead with the verdict sentence: "Over [window], the view's tilts contributed [±N] bps vs neutral ([quality] counterfactual; [K] segments, [C] holdings covered, [D] dropped)." Then the per-tilt table, the residual line, coverage notes, and the report-bundle path as a `file://` URL.

**AI-interaction disclosure:** render `parallax-conventions.md §9.2` immediately above the disclaimer (this is an operator-facing analysis report — same reasoning as the judge's §9.2 treatment; no config-artifact exemption).

Use the view-aware disclaimer per loader.md §5 rule 5 (the analyzed view is named even when expired), with one added sentence: *"Attribution is a single-window ex-post estimate under a heuristic multiplier model; it is not statistical validation of the view or the tilt calibration."*
