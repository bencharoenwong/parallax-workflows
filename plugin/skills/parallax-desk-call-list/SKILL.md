---
name: parallax-desk-call-list
description: "Desk-level morning call list for relationship managers covering multiple client books: detects overnight price moves across the union of symbols held desk-wide, then ranks clients by weighted book impact and drafts per-client talk tracks. Reads a saved desk book from ~/.parallax/desk-book/, or accepts an inline array of {client_name, portfolio}. Triggers on 'who do I call this morning', 'desk call list', 'which clients are affected'. NOT for a single portfolio (use /parallax-morning-brief), not for one client's meeting prep (use /parallax-client-review), not for score surveillance on an unweighted ticker list (use /parallax-watchlist-monitor)."
---

<!-- white-label: integration-pattern.md -->

# Desk Call List

## When not to use

- Single portfolio morning analysis -> use /parallax-morning-brief
- One client meeting prep -> use /parallax-client-review
- Unweighted ticker surveillance -> use /parallax-watchlist-monitor
- Full stock drill-down, technicals, or analyst consensus -> use /parallax-should-i-buy or /parallax-watchlist-monitor
- Book creation/editing -> operator maintains `~/.parallax/desk-book/book.yaml`

## Gotchas

- Expected Parallax spend: `1 + 3|M_equity| + 5·min(|M_equity|,K) + 1·|M_etf|` (`_parallax/token-costs.md`); the wide equity price scan is FREE.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.1 discovery, §0.2 typed integer params, §3 parallel execution, §3.1 annotation/rank separation, §9.1/§9.2 disclosures, §10 render gate, §11 verdict sensitivity, §12 information framing, §13 audience mode, and §14 host primitives.
- JIT-load `_parallax/coverage-matrix.md` before Batch A. `export_price_series` is equity-only and FREE, and its `success:false` response classifies ETFs; ETFs then price via `etf_daily_price`. This skill does not call `etf_profile`.
- JIT-load `_parallax/house-view/loader.md` §1-§2, §5, and §6. The house view annotates movers but never changes rank order or membership.
- JIT-load `_parallax/white-label/integration-pattern.md` before Pre-Render. Call `load_rm_branding_context("desk call list", audience=<flag or None>)` from `_parallax/white-label/rm_consumer.py`, passing the parsed `audience=` invocation flag (or `None` if absent). This visual-only seam blocks voice access and redacts source references.
- JIT-load `references/desk-book-format.md` before loading/validating any desk book.
- JIT-load `references/ranking-and-bounding.md` before thresholding, ranking, or rendering bounded sections.
- JIT-load `references/talk-tracks.md` before drafting per-client talk tracks.
- `desk_call_list_logic.py` is the pure arithmetic layer. Do not put MCP calls or local file writes in it.
- Client names and weights never go to Parallax MCP tools; only the deduplicated symbol union leaves the machine.
- `SCAN_CONCURRENCY = 24` applies only to the wide price scan. If the live probe shows rate limiting, use 8.
- `client_safe` is supported, but this is primarily an internal RM artifact.

Build one ranked, bounded morning call list for a relationship manager covering many client books.

## Usage

```
/parallax-desk-call-list
/parallax-desk-call-list threshold=4.5 min_impact=0.4 detail_cap=6 subset="Northgate,NG-001"
/parallax-desk-call-list [{"client_name":"Northgate","portfolio":[{"symbol":"AAPL.O","weight":0.12,"asset_class":"equity"}]}] redact_names=true
```

Defaults:

- `threshold=5.0` unless overridden by book `default_threshold_pct`
- `min_impact=0.50` pp unless overridden by book `default_min_impact_pp`
- `detail_cap=8`, `news_cap=8`, `audience=internal_analyst`

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). Local Python helpers run via `run-shell`.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` and `references/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named anywhere in this workflow (Step 2) to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
3. Parse args: `threshold=`, `min_impact=`, `detail_cap=`, `news_cap=`, `subset=`, `redact_names=`, `audience=`, or an inline book array.
4. `load-reference` `_parallax/house-view/loader.md` §1–§2; `run-shell` `view_status` (never recompute expiry math). Absent or invalid → run without view; the view annotates movers and never changes rank order or membership.
5. `load-reference` `_parallax/white-label/integration-pattern.md` §2 and call `load_rm_branding_context("desk call list", audience=<flag or None>)` from `_parallax/white-label/rm_consumer.py` once; keep `header_lines`, `about_lines`, `resolved_audience` for Step 5.

### Step 1 — Resolve inputs

`load-reference` `references/desk-book-format.md`. `read-config`: inline input, else `$PARALLAX_DESK_BOOK_PATH`, else `~/.parallax/desk-book/book.yaml`; inline wholly replaces the saved book. `run-shell` `desk_call_list_logic.py` to validate (keep warnings for both paths). Apply `subset=` to the saved book only, passing `redact_names` into resolution: keep global warnings and those owned by selected clients; report unmatched names verbatim unless redacted (then only the count, and `redact_names()` strips client refs and names); a non-empty subset matching no client → Scan refused (short form below). Compute the staleness tier and the sorted deduplicated symbol union `U`. Client names and weights never leave the machine; only `U` does.

### Step 2 — Fetch (parallel batches)

**Batch A — classification fused with the wide price scan.** `load-reference` `_parallax/coverage-matrix.md`. Cached `asset_class` routes directly (`equity` → `export_price_series`; `etf` → `etf_daily_price`). Uncached: `call-tool` `export_price_series(<ric>, days=10 as typed int)` (FREE, equity-only) as both classifier and price source — `success: true` with a non-empty `prices` list → equity, take the move and both close dates; `success: false` / no `prices` → ETF → `etf_daily_price(<plain ticker>, start_date=<today-7d>, end_date=<today>)` for the move and per-row date. Keyed on `success == false`, NOT an empty list; a dead equity gets one `etf_daily_price` probe that also fails and lands in the unpriced/coverage handling, named in the coverage line. Only on a full `export_price_series` outage: resolve bare tickers per conventions §1 and use the static fallback (suffix-less or `.P` ⇒ ETF). Fan out at `SCAN_CONCURRENCY` waves (24; 8 if rate-limited) plus one `get_telemetry` (`fields: regime_tag, signals, commentary.headline, divergences`). `move_pct = (close[-1] / close[-2] - 1) * 100` from two finite closes; fewer than two, or a non-finite value → unpriced, named in coverage, never a trigger.

**Batch B — mover enrichment (after Step 3 sets the mover set).** Waves of ≤ 8 concurrent calls across symbols and tools: `get_company_info` and `get_peer_snapshot` for every mover; `get_score_analysis` (`weeks=4` as typed int) for equity movers; `get_news_synthesis` for the top `news_cap` equity movers by desk-wide weighted exposure (one per symbol, not per client). ETF movers skip score and news (coverage unverified) and render those fields `not available for ETFs`; their price moves still drive ranking.

### Step 3 — Verify

`load-reference` `references/ranking-and-bounding.md`. Scan integrity first: priced coverage < 80% → SCAN DEGRADED, no call list. Movers = `abs(move_pct) > threshold` (strictly greater). More than 40 movers → auto-raise the threshold to the 40th-largest absolute move rounded up to 0.5 pp, recompute, and state the raise. No movers, or no client clearing `min_impact` → the no-calls short form. Identity: `get_peer_snapshot.target_company` vs `get_company_info.name`; on mismatch render Ground-truth Integrity, exclude that symbol's scores, keep its price move in ranking.

### Step 4 — Compute

Zero tool calls. `run-shell` `desk_call_list_logic.py` for triggered exposure, signed net impact, direction-agnostic severity, top driver, coverage, rank order, and the bounded detail/summary sections. News and house-view tags are annotations only (conventions §3.1): they never alter rank membership or order.

### Step 5 — Compose

`load-reference` `references/talk-tracks.md` for the Client Detail entries. Fill **Output Format** below in order: the seam's `header_lines` below any House View Preamble and its `about_lines` verbatim in About This Report; §12 preface above Priority Calls; §11 Verdict Sensitivity omitted when `resolved_audience` is `client_safe`; `parallax-conventions.md §9.2` disclosure; disclaimer per loader.md §5 when a view is active, otherwise `parallax-conventions.md §9.1`; audit per loader.md §6.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/deskcall.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill desk-call-list < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout. The stderr `[render-gate] WARN:` line is diagnostics: never include it. Degraded notes go inside their section. If `run-shell` is absent, apply conventions §14.3: the render-gate row, and the gate-shaped-helper row for the ranking (the call list is UNVERIFIED; render the no-calls short form with that reason rather than a hand-ranked list). No Step 7.

## Output Format

1. House View Preamble, only if active, per `_parallax/house-view/loader.md §5`.
2. Branding Header, only if white-label active and `client_name != ""`: optional URL logo line, then `**<client_name>** desk call list`.
3. `# Desk Call List` title with as-of date, session dates, threshold, clients scanned, and clients triggered.
4. Book Staleness Warning, only for warn/stale/unknown tiers.
5. Validation Warnings, whenever validation produced warnings, including renormalisation warnings for inline and saved books.
6. Ground-truth Integrity, only if any mismatch.
7. Market Context: 2-3 sentences from telemetry.
8. Priority Calls: render the informational preface per `_parallax/parallax-conventions.md §12`, then the full ranked table.
9. Client Detail: top `detail_cap` clients. Load `references/talk-tracks.md`; include why-listed arithmetic, positions table, talk track, and likely questions.
10. Also Affected (summary only): ranks after `detail_cap`; group by driving symbol when triggered clients exceed 25.
11. Symbol Movers Reference: symbol, name, move %, four-week score change, news headline, number of clients holding, desk-wide weighted exposure, and house-view tag.
12. Verdict Sensitivity per `_parallax/parallax-conventions.md §11`; omit when the seam's `resolved_audience` is `client_safe`.
13. Next steps: point to `/parallax-client-review`, `/parallax-should-i-buy`, or `/parallax-watchlist-monitor` as appropriate. Do not auto-invoke them.
14. About This Report: first the seam's `about_lines` verbatim — they already carry the `_parallax/white-label/integration-pattern.md §7` branding line, the unconditional currency line, any skipped local-logo basename, and the audience mode/notice lines; do not re-add any of them — then desk-book provenance, redaction state, and a cost note that the equity price scan is FREE (`export_price_series`) while `etf_daily_price` costs 1 token per ETF priced.
15. AI-interaction disclosure per `_parallax/parallax-conventions.md §9.2`.
16. Disclaimer: view-aware per `_parallax/house-view/loader.md §5` if active; otherwise render the standard disclaimer from `_parallax/parallax-conventions.md §9.1`.

## No-Calls and Degraded Short Forms

SCAN DEGRADED starts with `**Scan degraded — results not reliable.**` and names priced count, total symbols, coverage, and up to 10 unpriced symbols.

An empty client or symbol selection starts with `**Scan refused — no clients or symbols selected.**` and never renders a call list or no-calls result. An all-unmatched subset starts with `**Scan refused — subset matched no clients: <names>.**`; under `redact_names=true`, replace the names with `<N> selector(s) matched no client`. Redacted refusal and partial-match output never contains raw selectors, and client refs are omitted everywhere.

Quiet mornings start with `**No calls indicated.**`, then unique symbols scanned, client books scanned, largest move, threshold, and the `min_impact` pp floor. Include House View Preamble, Branding Header, staleness warning, validation warnings, About This Report, AI disclosure, and disclaimer.


## Failure modes

- Priced coverage below 80%: SCAN DEGRADED short form; no call list.
- Empty selection, or a subset matching no client: Scan refused short form (redacted variant under `redact_names=true`).
- No movers or no client above `min_impact`: No calls indicated short form.
- Rate limiting on the wide scan: drop `SCAN_CONCURRENCY` to 8.
- Enrichment failures: the mover keeps its price move and ranking; missing fields render as unavailable (or `not available for ETFs`).
- Host lacks a primitive: conventions §14.3, per primitive.

## Done when

- The report starts with the House View Preamble, the Branding Header, or `# Desk Call List`, and every applicable Output Format item 1–16 is present in order (or the correct short form is rendered in full).
- Rank order comes from `desk_call_list_logic.py`; no annotation changed membership or order.
- Coverage line names every unpriced symbol; any auto-raise is stated.
- No client name or weight left the machine; redaction state is in About This Report.
- The render gate ran and the reply is its stdout (or the §14.3 note is present in About This Report).
- `parallax-conventions.md §9.2` disclosure and the §9.1 or view-aware disclaimer are present; expected spend stated (Gotchas).
