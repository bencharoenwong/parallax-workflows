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

- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §0.1 tool loading, §0.2 typed integer params, §3 parallel execution, §3.1 annotation/rank separation, §9.1/§9.2 disclosures, §10 render gate, §11 verdict sensitivity, §12 information framing, and §13 audience mode.
- JIT-load `_parallax/coverage-matrix.md` before Batch A. `export_price_series` is equity-only; ETFs use `etf_daily_price`.
- JIT-load `_parallax/house-view/loader.md` §1-§2, §5, and §6. The house view annotates movers but never changes rank order or membership.
- JIT-load `_parallax/white-label/integration-pattern.md` before Pre-Render. Loader call is `load_visual_branding()`; do not access `branding["voice"]`.
- JIT-load `references/desk-book-format.md` before loading/validating any desk book.
- JIT-load `references/ranking-and-bounding.md` before thresholding, ranking, or rendering bounded sections.
- JIT-load `references/talk-tracks.md` before drafting per-client talk tracks.
- `desk_call_list_logic.py` is the pure arithmetic layer. Do not put MCP calls or local file writes in it.
- Client names and weights never go to Parallax MCP tools; only the deduplicated symbol union leaves the machine.
- `SCAN_CONCURRENCY = 24` applies only to the wide price scan. If the live probe shows rate limiting, use 8.
- `etf_profile` classification and `etf_daily_price` pricing costs are UNVERIFIED; do not invent numbers.
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

Execute using Parallax MCP tools plus local Python helpers.

### Batch 0 - Pre-flight, Book, House View

1. Resolve canonical `_parallax/...` paths per `_parallax/parallax-conventions.md §0.0`.
2. Call `ToolSearch` with query `"+Parallax"` to load deferred Parallax MCP schemas before the first data call.
3. Load `references/desk-book-format.md`; read inline input or `$PARALLAX_DESK_BOOK_PATH`, else `~/.parallax/desk-book/book.yaml`. Validate via `desk_call_list_logic.py`. Inline input wholly replaces the saved book. Preserve validation warnings for both input paths.
4. Apply subset filtering only to the saved book, passing the `redact_names` mode into resolution. Keep only global validation warnings and warnings owned by selected clients. Report unmatched names verbatim unless `redact_names=true`; in redacted mode retain and report only the unmatched count, then apply `redact_names()` so client refs and names are removed. If a non-empty subset matches no clients, refuse to scan under the same disclosure rule.
5. Compute staleness tier and the sorted deduplicated symbol union `U`.
6. Load active house view per `_parallax/house-view/loader.md` §1-§2. Shell out to `view_status`; do not recompute expiry date math. If absent or invalid, run without view.

If the first Parallax batch after tool loading is empty or cancelled, re-fire the whole batch once before concluding unavailability.

### Batch A - Asset-Class Classification and Wide Price Scan

Load `_parallax/coverage-matrix.md`. Asset-class pre-classification is mandatory before any price call:

1. Use holding `asset_class` when present.
2. Otherwise fan out `etf_profile(symbol)` probes. Error shape means equity; non-error profile means ETF.
3. If probes are unavailable, first resolve bare tickers to RICs per `_parallax/parallax-conventions.md` §1. Only then apply the static fallback to the resolved symbol: a symbol that remains suffix-less or ends in `.P` implies ETF; otherwise equity.

Then fan out the price scan at `SCAN_CONCURRENCY` waves, plus one telemetry call:

| Tool | Parameters | Notes |
|---|---|---|
| `get_telemetry` | `fields: regime_tag, signals, commentary.headline, divergences` | Desk-wide market context |
| `export_price_series` per equity branch | `symbol=<ric>`, `days=10` as typed integer | Equity-only; single-symbol calls |
| `etf_daily_price` per ETF branch | `symbol=<plain ticker>`, `start_date=<today-7d>`, `end_date=<today>` | ETF-only; single-symbol calls |

Derive `move_pct = (close[-1] / close[-2] - 1) * 100` from the last two closes, which must both be finite. Record both dates. If fewer than two closes return or either close/move is non-finite, mark the symbol unpriced, name it in coverage, and do not treat it as a trigger.

### Batch B - Threshold and Scan Integrity

Load `references/ranking-and-bounding.md`.

1. Compute desk scan integrity before the empty-mover path. If priced coverage is below 80%, render SCAN DEGRADED and skip the call list.
2. Define movers as `abs(move_pct) > threshold`; the boundary is strictly greater.
3. If more than 40 symbols cross the threshold, auto-raise to the 40th-largest absolute move rounded up to the nearest 0.5 pp, recompute movers, and state the auto-raise.
4. If no movers, or movers exist but no client clears `min_impact`, render the no-calls short form.

### Batch C - Mover Enrichment

For symbols in the mover set only, schedule enrichment in waves of at most 8 concurrent calls across symbols and tools:

| Tool | Parameters | Purpose |
|---|---|---|
| `get_company_info` | `symbol` for every mover | Display name and expected-name oracle |
| `get_peer_snapshot` | `symbol` for every mover | Current factor scores and `target_company` |
| `get_score_analysis` | `symbol`, `weeks=4` as typed integer for equity movers only | Four-week score trajectory |
| `get_news_synthesis` | `symbol` for top `news_cap` equity movers by desk-wide weighted exposure | One news synthesis per symbol, not per client |

Cross-check `get_peer_snapshot.target_company` against `get_company_info.name`. On mismatch, render Ground-truth Integrity, exclude that symbol's scores, but keep the price move in client ranking.

For ETF movers, skip `get_score_analysis` and `get_news_synthesis` because ETF coverage is unverified. Render those fields as `not available for ETFs`; never present their absence as an equity-grade enrichment failure. ETF price moves still drive client ranking.

### Batch D - Client Ranking

Zero tool calls. Use `desk_call_list_logic.py` to compute triggered exposure, signed net impact, direction-agnostic severity, top driver, coverage, rank order, and bounded detail/summary sections. News and house-view tags are annotations only and must not alter rank membership or order.

### Pre-Render - Load White-Label Branding

Load `_parallax/white-label/integration-pattern.md` §2. Call `load_visual_branding()`, `is_white_label_active(branding)`, and `safe_source_reference(branding)`. The branding is for the desk's firm: one report, one brand.

### Render - deterministic gate

Compose the complete report per Output Format, then run it through the shared render gate in one Bash step before replying:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/deskcall.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill desk-call-list < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is exactly that command's stdout. Put degraded notes inside the relevant report section so they survive the gate.

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
12. Verdict Sensitivity per `_parallax/parallax-conventions.md §11`; omit under `client_safe`.
13. Next steps: point to `/parallax-client-review`, `/parallax-should-i-buy`, or `/parallax-watchlist-monitor` as appropriate. Do not auto-invoke them.
14. About This Report: branding line per `_parallax/white-label/integration-pattern.md §7`, currency line, desk-book provenance, redaction state, audience mode if client-safe, skipped local-logo basename if relevant, and a cost note that both `etf_profile` classification and `etf_daily_price` pricing costs are UNVERIFIED.
15. AI-interaction disclosure per `_parallax/parallax-conventions.md §9.2`.
16. Disclaimer: view-aware per `_parallax/house-view/loader.md §5` if active; otherwise render the standard disclaimer from `_parallax/parallax-conventions.md §9.1`.

## No-Calls and Degraded Short Forms

SCAN DEGRADED starts with `**Scan degraded - results not reliable.**` and names priced count, total symbols, coverage, and up to 10 unpriced symbols.

An empty client or symbol selection starts with `**Scan refused — no clients or symbols selected.**` and never renders a call list or no-calls result. An all-unmatched subset starts with `**Scan refused — subset matched no clients: <names>.**`; under `redact_names=true`, replace the names with `<N> selector(s) matched no client`. Redacted refusal and partial-match output never contains raw selectors, and client refs are omitted everywhere.

Quiet mornings start with `**No calls indicated.**`, then unique symbols scanned, client books scanned, largest move, threshold, and the `min_impact` pp floor. Include House View Preamble, Branding Header, staleness warning, validation warnings, About This Report, AI disclosure, and disclaimer.
