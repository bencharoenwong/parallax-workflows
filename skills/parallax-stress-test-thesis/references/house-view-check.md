# House-View Cross-Check (optional, read-only, flag-only)

Loaded only if an active house view exists at `~/.parallax/active-house-view/`. This is a
**read-only conflict flag**, not a tilt application: the house view is an *opinion*, and this skill
tests an *argument against live data*. The view therefore never changes a Pass-1
Supported/Contradicted/Unconfirmed status — it can only add a visible note where the thesis's own
directional claims disagree with the firm's stated positioning.

If `~/.parallax/active-house-view/view.yaml` does not exist, do nothing and render nothing — there
is no view to cross-check, and its absence is not a caveat.

## The no-write variance from loader.md §7 (deliberate, documented)

`loader.md` §7 says single-stock read-only consumers (`should-i-buy`, `deep-dive`) MUST (1) load and
validate per §2, (2) check conflicts, (3) surface a flag, and (4) **append a `consume` audit entry
per §6**. This skill performs (1)–(3) but **deliberately omits (4)**.

Reason: this skill's foundational invariant is *no persistence* — it handles un-vetted client
profiles and raw thesis text in-session and is architected with **no write path at all** (SKILL.md
"Where artifacts live: None"). Joining the house-view consume-audit log would require adding that
write path, which is exactly the compliance-surface expansion v1 was designed to avoid. So it
consumes the view in the strictest possible mode: **flag-only, unlogged.**

Accepted limitation: by default the house-view `audit.jsonl` will **not** record that a stress-test
run read the view. That is the price of the no-write default.

**Opt-in full §7 compliance (`--house-view-audit`).** An embedder that standardizes on the house-view
audit trail across all consumers (so every view read is logged) can turn on consume-logging
explicitly. When — and only when — the caller passes `--house-view-audit` (or sets it in an
integration config), append the single `loader.md` §6 `consume` entry: `action:"consume"`,
`applied:false`, `applied_reason:"single-stock consumer (loader.md §7) — stress-test flag-only"`,
plus `conflicts_count` / `conflicts_summary` from Step 2. This is the **one** write the skill will
ever make, it is off by default, and it is surfaced to the operator (the disclaimer/preamble notes
"house-view consumption logged to the active view's audit trail" when it is on) — never silent. The
default remains flag-only, unlogged.

## Step 1 — Load and validate (read-only, per loader.md §2)

Run the `loader.md` §2 validation chain **read-only** — do not apply tilts, do not write:

- Read `view.yaml` + `prose.md`; note `metadata.schema_version` (absent → v0 legacy).
- Verify `view_hash`, `paired_yaml_hash`, `prose_body_hash`, `version_id`, and
  `uploader_confirmed == true`. On any drift / unconfirmed failure → **do not flag against a broken
  view**; render the one-line `loader.md` "Failure handling" message and continue the report with no
  house-view section.
- Resolve expiry via the `view_status` helper (`python -m view_status --json`, cwd
  `_parallax/house-view/`). Hard-block states (`none`/`malformed`/`expired`/`not_yet_effective`) →
  surface the helper's `banner` verbatim and render no conflict flags. Soft states
  (`active`/`warning`/`critical`) → surface the `banner` in the load preamble and proceed.
- Surface any `extraction_confidence[field] < 0.6` and any legacy-view prose-integrity warning in the
  preamble, exactly as §2 requires.

The active-view banner is **required** in the load preamble whenever a view is present (loader.md
§5.1 / §2 step 6) — even when no conflict fires, the reader must see which lens was checked.

## Step 2 — Detect thesis-vs-view conflicts

Unlike the per-stock consumers, this skill's conflict surface is the **thesis's own directional
claims**, layer by layer — never a rescore. Compare each non-Unconfirmed assumption's *claim
direction* against the view's non-neutral tilts (`|tilt| >= 1`):

| Thesis layer | View field | Conflict when |
|---|---|---|
| Layer 1 (macro) — Fed path, inflation, growth, risk regime | `tilts.macro_regime.*` | The thesis's macro premise is the opposite regime the view holds (e.g. thesis leans on "Fed cutting / risk-on"; view has `rates: holding`, `risk_appetite: risk_off`). |
| Layer 2 (sector/theme) — the sector the thesis is long/short | `tilts.sectors.*` | Thesis is bullish a sector the view is UW (`<= -1`), or bearish one the view is OW (`>= +1`), or the sector is on `excludes`. |
| Layer 4 (implicit factor lean) — growth vs. value, momentum, low-vol | `tilts.factors.*` | The thesis's implied factor tilt is the opposite sign of the view's. Apply the loader.md §"Factor-to-Parallax mapping" alias rule (`quality↔profitability`, `defensive↔low_volatility`). |

Alignments (thesis and view point the same way) are worth counting too — they go in the
`alignment_count` / `alignment_list` of the blanket note.

## Step 3 — Render the flag (never filter, never restate a status)

Render one **House-View Alignment** note via the shared helper
`render_view_conflict(kind="blanket", fields=...)` (`_parallax/house-view/render_helpers.md` — do
not inline the template; the helper is the single source of truth). Populate `direction`/`subject`
from the dominant conflicting tilt, and `alignment_count` / `conflict_count` / `conflict_list` /
`alignment_list` from Step 2.

Hard rules:

- **Flag, do not filter or re-rank.** The house view never removes an assumption from the map,
  never changes its `criticality`, and above all **never changes its Pass-1
  Supported/Contradicted/Unconfirmed status** — a Contradicted-by-data claim the CIO happens to
  agree with is still Contradicted. The flag is orthogonal to the factual read.
- **The view is opinion, the status is evidence.** State this in the note when a conflict fires: the
  thesis disagrees with the firm's stated positioning on *X*; that is a positioning conflict to
  resolve at decision time, not a mark against the assumption's evidential status.
- **No conflict → still show the banner**, plus a one-line "thesis is directionally consistent with
  the active view" if every checked layer aligned. Silence is not allowed (loader.md §7 "conflicts
  always banner-flag, never silent" — extended here to the aligned case for symmetry).

## Where it renders

A **House-View Alignment** section, placed immediately after the **World Verdict** (the Pass-1
positioning read belongs with the world read, before any client conditioning). It is client-invariant
— Phase 5 does not touch it. Omit the section entirely when no active view is present.
