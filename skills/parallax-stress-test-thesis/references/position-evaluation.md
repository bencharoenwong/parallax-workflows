# Phase 3 — Evaluate position-level ideas (layer 3)

Loaded when Phase 3 fires. **Skip this phase entirely if the thesis names no tickers** — state
that in the output rather than inventing a position to evaluate.

## RIC resolution

Resolve every named ticker to RIC format per `_parallax/parallax-conventions.md` §1 before calling
any scoring tool. Cross-validate names per §2 after every scoring call — a mismatched name is
excluded from the position read, not silently presented under the wrong company.

## Batch — fire in parallel, per symbol

| Tool | Parameters | Notes |
|---|---|---|
| `get_company_info` | comma-separated list of all symbols in one call | One call validates all names at once — the ground-truth oracle for cross-validation. **Also returns the headline factor scores** (`quality`, `value`, `momentum`, `tactical`, `defensive`, `total`) instantly — use them for a first-cut direction-alignment read (a bull thesis on a name scoring `value: 1`, `momentum: 2` is already fighting its own data) without waiting on the async `get_news_synthesis` call |
| `get_peer_snapshot` | per symbol | Factor scores + peer set. `target_company` (top-level) is the name field to cross-validate — not `name`, which belongs to individual peer rows. **The `rank` field / row order is NOT a quality ranking — it tracks market cap, so the target can show `rank: 1` while a peer beats it on `total_score`. Always rank the peer set by `total_score`, and read the tool's own `suggestion` field as the higher-scoring alternative** |
| `get_score_analysis` | per symbol, `weeks` as an **integer** (26 for a near-term catalyst thesis, 52 for a multi-quarter one — match the thesis's own stated timeframe, default 52) | Factor trajectory |
| `get_stock_outlook` | per symbol, **two separate calls**: `aspect: "analyst_targets"` and `aspect: "risk_return"` | One `aspect` per call — this tool does not accept multiple aspects in a single call |
| `get_news_synthesis` | per symbol (symbol-only — no query/theme parameter) | **Async, ~30-90s** — do not block the rest of the batch. Card-date staleness caveat applies (see below) |

## Assessment per symbol

With the batch results in hand, assess:

**(a) Direction alignment** — does the thesis's directional call on this name (long/short,
re-rate up/down) match what the factor scores and analyst outlook actually show, or is the thesis
fighting its own data?

**(b) Peer-relative factor check** — this is the check most theses skip, and the one most likely
to surface a real hole: if the thesis calls this name "the leader," does it actually lead its
*own peer set* on the factor the thesis is relying on (e.g., "best-in-class margins" — check
`get_peer_snapshot`'s peer rows, not just the standalone score)? A thesis that calls out relative
strength deserves a relative check, not just an absolute one. **Compare on `total_score` and the
specific factor columns — never on the `rank` field or row order, which follow market cap, so the
biggest name looks "#1" even when a peer out-scores it.** If Parallax's `suggestion` names a
higher-scoring peer, that is itself a mark against a "this name is *the* way to play it" thesis —
surface it rather than burying it.

**(c) Macro alignment** — does this position's factor profile line up with, or fight, the Phase 2
regime/sector read for its home market? A position can be fundamentally sound and still be
macro-misaligned (e.g., a rate-sensitive grower in a Phase-2-confirmed "higher for longer" regime).

**(d) News check** — does `get_news_synthesis` surface anything the thesis's stated catalyst
already priced in, or contradicts? Note the card's as-of date in the output — a news card that
predates a market-moving event is stale, and that staleness should be visible to the reader, not
silently treated as current.

## Failure handling

Per `_parallax/parallax-conventions.md` §4 fast-response / async fallback tables and the
coverage-matrix.md "per-symbol research" failure contract: if one tool fails for one symbol,
render that section "Data unavailable" / "Analysis pending" and continue with the rest — do not
gate the whole position read on one failed call. If `get_stock_outlook` returns data for 0–1 of
its aspects across the two calls, flag the position's outlook read as "may be materially
incomplete."
