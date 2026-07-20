# Ranking and Bounding

## §1 Impact Arithmetic

For client `c` with holdings `{(s, w)}` and triggered mover set `M`:

- Triggered exposure: `E_c = sum(w)` for holdings in `M`.
- Net book impact: `I_c = sum(w * move_pct_s)`, signed in percentage points.
- Severity: `S_c = sum(w * abs(move_pct_s))`, direction-agnostic percentage points.
- Top driver: the symbol with largest `w * abs(move_pct_s)`.
- Coverage: priced holding weight divided by total holding weight.

Severity ranks the call list. A book can have offsetting positive and negative movers with near-zero signed impact while still giving the RM multiple conversations to have.

## §2 Ranking

A client appears if `S_c >= min_impact`, default `0.50` pp.

Sort clients by:

1. `S_c` descending
2. `abs(I_c)` descending
3. largest single-symbol contribution descending
4. `client_name` ascending

House-view tags, news, and score trend annotations must not alter rank order or membership; this follows `_parallax/parallax-conventions.md §3.1`.

## §3 Thresholds

The move threshold is strict: `abs(move_pct) > threshold`. A symbol exactly at `5.00%` does not trigger when `threshold=5.0`.

If more than 40 symbols cross the requested threshold, auto-raise the threshold to the 40th-largest absolute move, rounded up to the nearest 0.5 percentage points. Recompute movers and state the auto-raise in the report.

## §4 Coverage

Compute desk scan integrity before the no-calls path. If fewer than 80% of unique symbols price successfully, render SCAN DEGRADED, name up to 10 unpriced symbols, and do not render a call list or no-calls short form.

For client-level coverage below 80%, keep the client in the ranking but flag `partial coverage` and name unpriced symbols. Missing prices are never treated as zero.

## §5 Bounding

The ranked table lists every triggered client. Detail sections are capped at `detail_cap=8` unless overridden.

Ranks after the detail cap appear under `Also Affected (summary only)`. If more than 25 clients trigger, group the summary by driving symbol rather than one line per client. Always render the arithmetic header: `<N> clients triggered - <detail_cap> shown in detail, <N - detail_cap> in summary.`

## §6 Verdict Sensitivity

Render Verdict Sensitivity per `_parallax/parallax-conventions.md §11`: the symbol closest to the move threshold from below and the client closest to the `min_impact` floor from below. Use third person and no advice language.
