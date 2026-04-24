# Render Helpers — House View Conflict Tokens

Canonical phrasing for the inline and closing flags defined in `loader.md` §7. Single source of truth so §7.1/§7.2/§7.3 tokens are byte-identical across every consumer skill and across time. Single file = single seam when Phase 0.5b lands provenance and tokens gain a `(source: "…")` suffix.

JIT-loaded alongside `loader.md` by any single-stock consumer that renders §7 flags.

---

## Function contract

```
render_view_conflict(kind, fields) -> str
```

`kind` is one of: `"blanket"` (§7.1), `"peer_suggest"` (§7.2), `"score_tension"` (§7.3).

`fields` is a dict. Required keys differ per `kind` — see templates below.

**Return type: `str`.** Always a plain string, ready to drop into rendered markdown. Empty string is never a valid return — the caller decides whether to invoke. If `kind` is unrecognized or required fields are missing, return the string `"[render_view_conflict: internal error — kind=<kind>, missing=<keys>]"` so the bug surfaces in output rather than silently dropping the flag.

---

## `kind = "blanket"` (§7.1 House View Note)

**Required fields:** `direction` (`"UW"` | `"OW"`), `subject` (sector / theme / region string), `effective_date` (ISO date), `alignment_count` (int), `conflict_count` (int), `conflict_list` (short comma-sep string, e.g., `"info_tech UW, momentum UW"`), `alignment_list` (short comma-sep string).

**Template:**

> **House view note:** Active view is {direction} {subject} (set {effective_date}). {alignment_count} alignment{s} / {conflict_count} conflict{s} — {conflict_list}. {alignment_list_clause} Recommendation above is for research purposes; evaluate against your active view before acting. (For tilt origin, run `/parallax-load-house-view --why tilts.<path>`.)

Where `{alignment_list_clause}` = `"Alignments: " + alignment_list + "."` if `alignment_count > 0`, else empty string. `{s}` = `""` if count == 1 else `"s"`.

The trailing `--why` pointer is MANDATORY while `metadata.calibration_status == "heuristic_phase0"` — it gives the reader a one-query path to tilt provenance (source prose vs. macro-regime rule). This is the Phase 0.5 bridge until Gap 4 ships `provenance.yaml` at ingest, at which point `render_view_conflict()` will gain an optional `source_type` field and the parenthetical can become richer (e.g., `(tilt source: prose-extracted | rule-derived | manual)`).

---

## `kind = "peer_suggest"` (§7.2 Peer-suggest token)

**Required fields:** `peer_ticker` (RIC), `peer_sector` (string), `view_tilt_direction` (`"UW"` — §7.2 only fires on UW or excludes), `on_excludes_list` (bool).

**Template (UW sector case):**

> ⚠ Peer suggestion **{peer_ticker}** is in view-UW {peer_sector} — flagged, not filtered.

**Template (excludes list case):**

> ⚠ Peer suggestion **{peer_ticker}** is on the active view's excludes list — flagged, not filtered. (Excludes are honored only at portfolio construction; for research purposes the peer is shown with this flag.)

Pick the template matching `on_excludes_list`. Do not emit both. Never emit a §7.2 token for peers outside the view's UW/excludes surface.

---

## `kind = "score_tension"` (§7.3 Tension banner)

**Required fields:** `total_score` (float, 1 decimal place), `stock_sector` (string).

**Template:**

> Parallax scores **{total_score:.1f}** but view is UW {stock_sector} — score-view tension. Resolve at decision time.

Only invoke when `total_score >= 7.0` AND the view's tilt for `stock_sector` is `<= -1`. The caller is responsible for the threshold check — this renderer only formats.

---

## Phase 0.5b hook (deferred)

When per-tilt provenance lands (Phase 1), the `peer_suggest` and `score_tension` templates will gain an optional suffix `(source: "<span from prose.md>")`. The renderer signature stays identical; the template adds one line. Single-file refactor.

Consumers MUST NOT construct these strings by hand. Route through this helper so the Phase 1 upgrade is a one-file change.
