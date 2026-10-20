---
name: parallax-house-view-attribution
description: "Retrospective hypothetical house-view weight diagnostic: compare a recorded recommendation with neutral weights over a stated historical price-return window, then decompose the model-implied difference. Does not reconstruct executed holdings or establish realized view value-add. Read-only against the view; emits a local report bundle and one attribution audit row. NOT for forward-looking drift monitoring (use /parallax-judge-house-view), internal-consistency checks (use /parallax-stress-house-view), or an LP performance letter (use /parallax-cio-letter-prep)."
---

# House View Attribution

**Method boundary:** this source-only skill produces a retrospective hypothetical diagnostic. Reasoning chains record recommendations, not executed trades. The current helper does not bind decision timestamps to subsequent holding intervals. Never describe its numbers as realized portfolio performance, causal view value-add, prospective evidence, or a backtest. Legacy helper/audit keys such as `active_return_bps` and `realized_contribution_bps` remain for compatibility; render them with hypothetical labels.

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
- "Neutral" is pinned as *same recorded names, all loader.md §3 weight multipliers at 1.00×* (score-proportional when per-holding base scores are recoverable, else equal-weight tagged `approximate`). `exact` describes recoverable score weights only, not an exact causal counterfactual. This same-name comparison cannot measure the return of excluded or unselected names.
- `export_price_series` is trailing-365-days only (no start/end anchor). Windows starting >365 days ago: refuse with "window start > 365 days ago — export_price_series cannot reach it; attribute a sub-window or archive prices externally."
- Render the §5.1a heuristic_phase0 calibration disclosure verbatim. This retrospective diagnostic is not statistical validation or a qualifying prospective backtest; never use it to claim empirical calibration. This skill never touches `calibration_status`.
- `selection_residual_bps` is the unexplained recorded-vs-model weight difference on the same names. It does not identify causal selection, factor, style or exclusion effects. Keep it separate from the model's tilt-group decomposition.
- Supported scope is a long-only equity recommendation with finite, nonnegative weights summing to 1. ETF/fund, short, leveraged or unclassified holdings are unsupported here: stop and name the unsupported leg before price calls. Verify asset class from discovered metadata; do not assume every RIC is an equity.
- Returns are each equity's local-currency price returns, without dividends or FX. Mixed-currency comparisons are hypothetical local-return diagnostics, never a base-currency portfolio return. Report every holding's price currency and the known/unknown currency basis; do not invent conversion. If the user needs base-currency or total-return attribution, explain the missing capability.
- Every host interaction is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). `attribution.py` is the math layer (`run-shell`); never re-derive its reconstruction, counterfactual, or Shapley logic inline. Expected Parallax spend: `_parallax/token-costs.md`.
- The reference portfolio is whatever the chains recorded — do not let the caller cherry-pick a subset of chains without recording the exclusion in the report ("chains_used" vs chains found).

## Usage

```
/parallax-house-view-attribution                       # hypothetical diagnostic for the active view
/parallax-house-view-attribution --view <view_id>      # hypothetical diagnostic for an archived view
/parallax-house-view-attribution --window 2026-04-01 2026-06-30   # explicit sub-window
```

## Workflow

Report-producer shape: the spine headings below; `attribution.py` and its tests name the old phases (`Phase 5` = the bundle write) as identifiers. No render-gate script: the bundle files are the deterministic output.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/house-view/loader.md` (§6 audit format) and this skill's `attribution.py` (pure math layer — all reconstruction, counterfactual, and Shapley logic lives there; do not re-derive it inline).
3. `discover-tools`: bind `export_price_series`, `analyze_portfolio`, `get_peer_snapshot`, `get_company_info` to the exact callables and schemas exposed now (conventions §0.0–§0.1).
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call; `run-shell` = `Bash`.
   <!-- /host-note -->
4. `read-config`: `$PARALLAX_HOUSE_VIEW_DIR` (else `~/.parallax/active-house-view/`) and `~/.parallax/reasoning-chains/`.

### Step 1 — Resolve inputs

**Target view and window.** Default: the active view (`~/.parallax/active-house-view/view.yaml`, validated per loader.md §2 — an expired view is still attributable; validation here is integrity, not applicability). With `--view <view_id>`: resolve from `.archive/<view_id>-<version_id>/` (latest version unless one is named). Window = `[effective_date, min(valid_through_or_computed_expiry, today)]`, clipped by `--window`. Refuse windows starting >365 days ago (export_price_series limit).

**Chains.** `attribution.load_window_chains(view_id, window_start, window_end)`. Cross-check against `audit.jsonl` consume rows (count of `applied=true` consumes in-window vs chains found) and report the coverage fraction. Zero usable chains → halt with `InsufficientProvenance` message; append the audit row with `attribution_summary.segments = 0` and a `notes` explanation.

**Record selection.** List the available chains with their decision timestamps, version IDs and coverage. Ask for one record when the intended recommendation is ambiguous; do not silently pick the latest or average records. Run one record against the explicitly stated historical window. State whether its timestamp is before, within or after that window. Even a pre-window timestamp does not prove execution. Multi-record/version time segmentation is not implemented: do not sum overlapping full-window results or use `segment_by_version` as an effective-interval constructor.

### Step 2 — Fetch (parallel batches)

For each verified equity: `export_price_series` accepts only trailing `days` (capped at 365), not historical start/end parameters. Fetch enough history to retain the last actual close on or before window start, plus closes through window end. Require a valid start anchor and end coverage; do not silently shorten the window. Record actual price dates and currency. Split adjustment is not established: a known split without verified adjusted history makes the leg unavailable. Compute local price returns only; absent dividend/FX contributions can move the relative comparison in either direction. `analyze_portfolio` is a cross-check only when its dates, recorded weights, asset coverage, currency and return basis match; otherwise mark it non-comparable rather than declaring a reconciliation failure. Classify sector/region/themes using dated metadata; disclose when only current classification is available. Unclassifiable dimensions get multiplier 1.0, never a guessed sector.

### Step 3 — Verify

- Coverage: chains found vs `applied=true` consume rows in-window (Step 1); report the fraction.
- Missing price legs may be dropped only in an explicitly labeled covered-subset diagnostic. Report each dropped name and its original recorded and neutral weight, plus the original covered-weight fraction of BOTH legs before renormalization. Never present the subset number as a full-book result. Zero covered weight in either leg: halt. Preserve these details in the report; do not add holdings arrays or new fields to the audit schema.
- Server cross-check: compare only on the same verified basis; otherwise report why it is non-comparable.
- Never guess a sector: an unclassifiable holding keeps multiplier 1.0 and lands in the residual.

### Step 4 — Compute

Run `attribution.attribute_segment(selected_chain, returns, holding_meta)` once. The helper rejects nonfinite/boolean observations and unsupported weights. Use `attribution.merge_segments([result])` only for the existing single-record audit summary shape. Render a hypothetical recorded-minus-neutral price-return difference, model-implied Shapley decomposition and unexplained weight residual. No time stitching or multi-record return aggregation is supported by this workflow.

### Step 5 — Compose

Assemble `report.md` and `report.json`: hypothetical-method label, requested/actual price window, selected run ID and decision timestamp, recorded recommendation (not executed holdings), currency and price-only basis, covered weights of both legs, model tilt decomposition, unexplained residual and neutral-weight reconstruction quality. Preserve the §5.1a disclosure. Add report-only method/coverage metadata alongside the unchanged audit-summary object; no new audit fields.

### Step 6 — Render (bundle + audit)

Write the bundle to `~/.parallax/attribution-reports/<view_id>-<window_start>_<window_end>-<6-char-nonce>/` (dir `0700`, files `0600`):
- `report.md` and `report.json` from Step 5.
- `audit_entry.json` — copy of the appended row.

Compute `report_hash = sha256(report.md bytes)`. Append ONE audit row per loader.md §6 via `audit_chain.append_entry`: `action="attribution"`, `applied=false`, `attributed_view_id`, `attributed_version_id`, `attribution_window`, `attribution_summary` (with `reference_portfolio_hash` = sha256 of the sorted chain run_ids used, and `chains_used`), `report_hash`. Emit a reasoning chain via `chain_emit.emit_phase_0_chain` (`skill_version="parallax-house-view-attribution@1.0.0"`, `final_portfolio={"weights": {}}`).

## Failure modes

- Window start > 365 days ago: refuse with the `export_price_series` message; attribute a sub-window.
- Zero usable chains: halt with `InsufficientProvenance`; audit row with `attribution_summary.segments = 0` and a `notes` explanation.
- `analyze_portfolio` unavailable: local math stands, flagged "server cross-check unavailable".
- Price data missing for a holding: dropped and renormalized (Step 3), never imputed.
- Host lacks `run-shell`: the math layer cannot run; the skill declares itself unavailable on this host (conventions §14.3 gate-shaped helper rule).

## Done when

- Exactly one `attribution` audit row appended, `applied=false`, carrying `report_hash`; the bundle directory exists `0700` with the three files `0600`; the reasoning chain emitted.
- The reply leads with the verdict sentence, the per-tilt table, residual line, coverage notes, and the `file://` bundle path; §9.2 disclosure and the view-aware disclaimer with the added sentence are present.

## Output Format

Lead with: "Retrospective hypothetical diagnostic over [window]: recorded recommendation minus neutral [±N] bps on local price returns, without dividends or FX. This does not measure realized view value-add." Then give decision timestamp, actual price dates/currencies, original covered weights of both legs, the model tilt table, unexplained weight residual, reconstruction quality and report-bundle path.

**AI-interaction disclosure:** render `parallax-conventions.md §9.2` immediately above the disclaimer (this is an operator-facing analysis report — same reasoning as the judge's §9.2 treatment; no config-artifact exemption).

Use the view-aware disclaimer per loader.md §5 rule 5 (the analyzed view is named even when expired), with: *"This retrospective hypothetical weight comparison does not reconstruct executed holdings, establish causal or realized view value-add, or validate the view or tilt calibration."*
