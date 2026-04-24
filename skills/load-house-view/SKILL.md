---
name: parallax-load-house-view
description: "Ingest a CIO house view (PDF / text / URL / wizard) into the Parallax workflow system. Extracts structured tilts and excludes, presents a confirmation gate, then saves the view to ~/.parallax/active-house-view/ where every portfolio skill auto-loads it. Use to set, update, re-pair, extend, or clear the active house view. NOT for portfolio construction (use /parallax-portfolio-builder), not for one-off scenario exploration (just describe inline to the relevant skill)."
negative-triggers:
  - Building a portfolio → use /parallax-portfolio-builder
  - One-off scenario / what-if → describe inline to the portfolio skill, don't load as a view
  - Single-stock evaluation → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/house-view/schema.yaml before extraction — it is the single source of truth for the YAML shape
  - JIT-load _parallax/house-view/loader.md to see what consumer skills will validate (helps you produce a valid view first time)
  - PDF input — use the Read tool with `pages` parameter for >10 pages; do NOT defuddle PDFs (we want figure context)
  - URL input — use the defuddle skill if Bash is available, else WebFetch
  - Confirmation gate is REQUIRED — the uploader must explicitly confirm extracted YAML before save (uploader_confirmed=true). Saving without confirmation breaks downstream loaders.
  - Always compute view_hash from the canonical tilts body per schema.yaml §"view_hash computation" — sorted keys, no comments, no empty fields
  - Ask uploader_role and basis_statement via AskUserQuestion — these are required-at-institutional fields and need explicit human input
  - Auto-applied macro_regime → factor tilts (loader.md §3) MUST be surfaced to the uploader at the gate, not silently applied
  - Confirmation gate persists a pre-edit snapshot (Step 3a) when uploader chooses 'Edit specific fields' — writes extractor's pristine draft to `.archive/<version>/pre_edit.yaml` alongside the superseded view. No-edit confirmations skip this.
  - Every extraction attempt (Step 3b) logs an `extraction_attempt` audit entry to `audit.jsonl` — whether or not it becomes a save. Capture disposition (confirmed/edited/re_extracted/rejected) + draft_yaml_hash per loader.md §6.2.
  - Save (Step 4 step 10) computes a `version_diff` block vs `parent_version_id` and stashes it on the save audit entry. Only when this save supersedes a prior version.
  - `--why <tilt-path>` is on-demand — does not write provenance to view.yaml. Reads prose.md + tilt value, produces a one-paragraph explanation with quoted spans. Use when auditing 'where did this tilt come from?'
---

# Load House View

Ingest a CIO house view into the Parallax workflow system. Once loaded, every portfolio-construction skill (`portfolio-builder`, `rebalance`, `thematic-screen`, `morning-brief`, `client-review`, `explain-portfolio`) silently applies the view's tilts, excludes, and macro regime mapping. Single-stock skills (`should-i-buy`, `deep-dive`) surface conflict flags but do not apply tilts.

## Usage

```
/parallax-load-house-view <path/to/view.pdf>
/parallax-load-house-view <path/to/view.txt>
/parallax-load-house-view <https://...>
/parallax-load-house-view                          # wizard mode — guided manual entry
/parallax-load-house-view --status                 # show active view summary
/parallax-load-house-view --clear                  # remove active view
/parallax-load-house-view --extend 2026-09-30      # push valid_through forward
/parallax-load-house-view --re-pair                # re-pair after manual prose edit (drift)
/parallax-load-house-view --edit                   # open YAML in editor; re-confirm on save
/parallax-load-house-view --why tilts.factors.momentum             # on-demand: why is this tilt set to what it is?
/parallax-load-house-view --why tilts.sectors.information_technology
/parallax-load-house-view --why factors.momentum                   # bare form — `tilts.` prefix auto-prepended
/parallax-load-house-view --version-history        # show parent chain + per-version diffs from audit.jsonl
```

## Where the view lives

**Phase 0:** `~/.parallax/active-house-view/`
- `view.yaml` — canonical YAML per `_parallax/house-view/schema.yaml`
- `prose.md` — verbatim CIO narrative with `paired_yaml_hash` frontmatter
- `audit.jsonl` — append-only consume log (consumers append; this skill initializes)
- `.archive/<view_id>-<version_id>/` — superseded versions (kept for `parent_version_id` traceability)

If `~/.parallax/active-house-view/` does not exist, create it on first save.

## Workflow

JIT-load `_parallax/house-view/schema.yaml` (canonical structure) and `_parallax/house-view/loader.md` (consumer expectations) before extraction.

### Step 1 — Detect mode and load source

| Input | Action |
|---|---|
| Argument is a `.pdf` path | Use `Read` tool with `pages` parameter; for >10 pages, read in 10-page batches |
| Argument is a `.txt`, `.md`, or other text path | Use `Read` tool |
| Argument starts with `http://` / `https://` | Try `defuddle parse <url> --md` via Bash; fall back to `WebFetch` |
| No argument | Wizard mode — see Step 1a |
| `--status` / `--clear` / `--extend` / `--re-pair` / `--edit` | Skip to Step 6 (operational modes) |

#### Step 1a — Wizard mode

Use `AskUserQuestion` to walk the uploader through the schema interactively. Present sector/region/factor/style sliders as multi-select questions with -2/-1/0/+1/+2 options. Skip fields the uploader leaves at neutral. Capture excludes as a free-text follow-up.

### Step 2 — Extract structured tilts

Produce a draft YAML conforming to `_parallax/house-view/schema.yaml`. For each field, also produce a `extraction_confidence` score (0.0-1.0) representing your confidence in the extraction.

**Pillar extraction (quantum-factor decomposition).** Before extracting sector/region/factor tilts, read the source for pillar-level conviction and populate `tilts.pillars`:

| Pillar | Look for | Map to |
|---|---|---|
| `econometrics_phase` (Ω) | Macro backdrop framing — "constructive on growth", "recessionary", "stagflation", "soft landing" | +2 very constructive → -2 recessionary/stress |
| `valuation_state` (Φ) | Valuation commentary — "stretched multiples", "cheap vs history", "PE reasonable", "dispersion" | +2 very undervalued → -2 highly overvalued |
| `market_entropy` (Ξ) | Technicals/vol/flows — "orderly rotation", "elevated VIX", "breadth deteriorating", "heavy issuance" | +2 low/ordered → -2 high/disordered |
| `psychological_wavelength` (Ψ) | Sentiment/RORO — "risk-on backdrop", "frothy retail", "capitulation", "fear index elevated" | +2 very positive → -2 very negative |

Pillars are usually coarse — a prose view rarely articulates sub-factor level. If the source is silent on a pillar, leave at 0 and flag `pillars` extraction_confidence ≤ 0.6. Pillar scores are encoding-only in Phase 0 (per loader.md §3): they are stored but do NOT auto-translate into factor multipliers.

**Hedged or split-sector language is a known failure mode.** When the source uses phrases like:
- "constructive on tech but selective in semis"
- "modestly underweight financials"
- "barbell of growth and value"
- "tactical opportunity"

…do not collapse to a single integer without recording uncertainty. Set the confidence to ≤ 0.7 and note the ambiguity in `extraction.extraction_notes`.

**Factor canonical names.** Use `profitability` (not `quality`) and `low_volatility` (not `defensive`) when extracting fresh. The synonyms remain valid for backward compatibility but new extractions should use the canonical set: `value, profitability, momentum, low_volatility, trading_signals`.

**Region granularity.** For prose that names specific countries (Mexico, Brazil, Indonesia, etc.), use the country-level region keys rather than collapsing into broad buckets (`em_ex_china`, `apac_ex_japan`). The full country list is in schema.yaml §`regions`. When the view speaks in broad terms ("EM ex-China overweight"), use the broad key. When specific ("overweight India and Mexico"), use per-country keys.

**Macro regime auto-mapping** (per `loader.md` §3): if the source implies a macro regime, populate `tilts.macro_regime` AND compute the factor-tilt deltas. Show the uploader the raw regime + the resulting factor deltas at the gate so they can override.

**Cross-asset views are out of scope.** If the source carries views on fixed income, FX, credit, commodities, or alternatives (common in full TAA workbooks), capture them in `extraction.extraction_notes` as "DROPPED (out of scope): <summary>" so the uploader knows what was lost. Do NOT silently discard.

**Required uploader-supplied fields** (cannot be extracted from source — ask via `AskUserQuestion` after extraction):
- `metadata.uploader_role` (single-select: CIO / PM / Investment Committee / Strategist / Other)
- `metadata.basis_statement` (free text — what's the basis for this view? IC meeting, strategy memo, regulatory mandate)
- `metadata.effective_date` (date, default today)
- `metadata.valid_through` OR `metadata.auto_expire_days` (date or int; default `auto_expire_days = 90`)

### Step 3 — Confirmation gate (REQUIRED before save)

Present the draft to the uploader in this format:

```
============================================================
HOUSE VIEW — DRAFT FOR CONFIRMATION
============================================================

Source: <filename or URL or "wizard">
Extraction confidence: avg <X.XX>, lowest <field>: <conf>

--- METADATA ---
view_name:        <proposed name>
uploader_role:    <captured>
effective_date:   <captured>
valid_through:    <captured or "computed: <date>">
basis_statement:  <captured, truncated to 200 chars>

--- PILLARS (quantum-factor decomposition) ---
Ω econometrics_phase:        <value>
Φ valuation_state:           <value>
Ξ market_entropy:            <value>
Ψ psychological_wavelength:  <value>

--- TILTS (only non-zero shown) ---
sectors:          <list of sector: tilt>
regions:          <list of region: tilt>
factors:          <list of factor: tilt>      [auto-applied from macro_regime: <fields>]
styles:           <list of style: tilt>
themes:           <list of theme: tilt>
excludes:         <list with reasons>

--- DROPPED (out of scope: cross-asset views) ---
<list of non-equity views found in source, e.g., "FI: long EM LC sovereign", or "none">

--- MACRO REGIME ---
growth: <value>   inflation: <value>   rates: <value>   risk_appetite: <value>
Auto-mapped to factor tilts (see loader.md §3): <delta list>

--- LOW-CONFIDENCE FIELDS (< 0.6) ---
<list with extraction_notes excerpts>

--- DEGENERATE-VIEW CHECK ---
tilt_variance: <X.XX>  [WARN if < 0.5]

============================================================
```

Then ask via `AskUserQuestion`:

> Confirm this house view extraction?
> - **Confirm and save** (Recommended if extraction looks right)
> - **Edit specific fields** — you'll be prompted for which fields
> - **Re-extract with hint** — provide a hint to improve extraction
> - **Reject** — abandon this ingest, no save

If `Edit specific fields`: **FIRST snapshot the extractor's pre-edit draft** (see §3a below — in-memory holding buffer), then loop on `AskUserQuestion` per flagged field, then re-render the gate. When the uploader ultimately chooses `Confirm` on the re-rendered edited gate, write the `extraction_attempt` audit entry (see §3b) BEFORE proceeding to Step 4 — use `disposition="edited"` and `draft_yaml_hash` = sha256 (canonical) of the **pre-edit** holding buffer (not the post-edit confirmed draft — that hash goes into `view.yaml` via Step 4's `view_hash`). This makes the pair `extraction_attempt.draft_yaml_hash` + `save.view_hash` the audit signature of "what the extractor produced → what the uploader shipped."
If `Re-extract with hint`: **discard the holding buffer if Edit was visited earlier** — do not write `pre_edit.yaml`. Log an `extraction_attempt` audit entry capturing the rejected draft and the hint (see §3b) with `disposition="re_extracted"`, ask for the hint, re-run Step 2 with the hint added to extraction context, re-render the gate.
If `Reject`: **discard the holding buffer if Edit was visited earlier**. Log an `extraction_attempt` audit entry with `disposition="rejected"`, abandon, do not write.

#### Step 3a — Pre-edit snapshot (Layer 2)

When the uploader chooses `Edit specific fields` (not `Confirm` on the pristine draft):

1. Serialize the current pre-edit draft YAML (the extractor's output, pre-modification) to a holding buffer.
2. After all edits land AND the uploader `Confirm`s the edited version, write the pre-edit snapshot to `~/.parallax/active-house-view/.archive/<new_view_id>-<new_version_id>/pre_edit.yaml`. (The directory is the SAME one Step 4 step 9 creates to archive the superseded view — both files share the slot.)
3. Optionally ask the uploader (single question, skippable): "One line on what you changed and why? (optional — press Enter to skip)". If non-empty, save as `~/.parallax/active-house-view/.archive/<new_view_id>-<new_version_id>/edit_notes.md`.

If the uploader confirms the pristine draft (no edits), skip Step 3a entirely — there's nothing to snapshot.

#### Step 3b — Extraction attempt logging (Layer 5, folded into audit.jsonl)

Every extraction attempt — including re-extracts and rejections that never become saves — appends one `action: "extraction_attempt"` entry to `audit.jsonl` per loader.md §6.1. Required fields: `schema_version`, `ts`, `skill`, `action`, `applied=false`. Conditional: `query_summary` (source file basename or URL), `disposition` (one of: `confirmed`, `edited`, `re_extracted`, `rejected`), `draft_yaml_hash` (sha256 of the draft the uploader saw; lets us correlate with a later save's `view_hash`), `extraction_duration_ms` (optional, wall-clock from extraction start to disposition), `hint` (when disposition=re_extracted, the hint text truncated to 200 chars).

A successful `save` after a confirmed draft still emits its own `action: "save"` entry per Step 4 — the two actions are independent. An `extraction_attempt` with `disposition=confirmed` tells you "the uploader confirmed this draft"; the subsequent `save` tells you "this draft was persisted." Rejected or re-extracted drafts have no matching save.

### Step 4 — Compute hashes and write files

On `Confirm`:

1. **Compute** `view_hash` per schema.yaml §"view_hash computation" (pinned algorithm; the reference Python snippet is reproduced in `skills/_parallax/house-view/tests/test_view_hash.py`). Keep the implementation byte-identical to the reference — any deviation will break hash round-trip.
2. **Generate** `metadata.view_id` (uuid4) — reuse from existing view if updating same view family; new uuid for new family.
3. **Generate** `metadata.version_id` (new uuid4 every save).
4. **Set** `metadata.parent_version_id` to the previous `version_id` if a view existed before this save; null otherwise.
5. **Set** `extraction.uploader_confirmed = true`.
6. **Set** `extraction.extracted_at` and `metadata.upload_timestamp` to now (ISO 8601 UTC).
6a. **Set** `metadata.schema_version = 1` (current schema version — see schema.yaml). Every new save writes this; legacy views without it read as v0 at load time.
6b. **Set** `metadata.calibration_status = "heuristic_phase0"`. Do NOT default to `"empirical_phase1"`; that value is reserved for saves made after the Phase 1 calibration backtest lands and is gated on an explicit uploader confirmation of calibration evidence. Until then, every save — including re-pairs and extensions that preserve tilts — writes `heuristic_phase0`.
7. **Construct the prose body** (the markdown that will live below the frontmatter — verbatim CIO narrative).
8. **Compute** `prose_body_hash = sha256(prose_body_utf8).hexdigest()` per schema.yaml §"prose_body_hash computation". The hash is over the bytes that will appear AFTER the closing `---` of the frontmatter — not over the whole file. Compute on the finalized body before writing.
9. **Write**:
   - Archive existing `~/.parallax/active-house-view/view.yaml` and `prose.md` (if present) to `~/.parallax/active-house-view/.archive/<old_view_id>-<old_version_id>/`.
   - Write new `view.yaml`.
   - Write new `prose.md` with frontmatter **four fields in this order**: `paired_yaml_hash`, `prose_body_hash`, `view_id`, `version_id`. Frontmatter is the only part of the file NOT covered by `prose_body_hash`.
   - If `audit.jsonl` does not exist, create it empty.
10. **Compute version-diff (Layer 3)** — only when `metadata.parent_version_id` is non-null (i.e., this save supersedes a prior version in the same view family):
    0. **Archive-missing guard.** If `.archive/<parent_view_id>-<parent_version_id>/view.yaml` does not exist (fresh install, manual deletion, or the parent was cleared before this update), skip sub-steps 1-2 and set `version_diff_truncated: true` with `notes: "parent_archive_missing: <parent_view_id>-<parent_version_id>"` on the save audit entry. Do not emit a `version_diff` field. Continue to save — the missing-archive case is survivable, not a save blocker.
    1. Read the parent's archived `view.yaml` from `.archive/<parent_view_id>-<parent_version_id>/view.yaml`.
    2. Compute a flat diff restricted to the `tilts` and `excludes` subtrees (same scope as `view_hash`). For each dotted path (`tilts.sectors.health_care`, `tilts.factors.momentum`, `excludes[0]`, etc.) that differs, record `{path: [old_value, new_value]}`. Use `null` for either side when the key is absent on that side. Cap output at 40 entries; if more, truncate and set `version_diff_truncated: true`.
    3. Stash as `version_diff` on the save audit entry in step 11 below.
11. **Append** an audit entry for the ingest itself:
    ```json
    {"schema_version":1,"ts":"...","view_id":"...","version_id":"...","skill":"parallax-load-house-view","action":"save","applied":true,"parent_version_id":"...","version_diff":{"tilts.factors.momentum":[null,-1]}}
    ```
    Schema per loader.md §6. `schema_version` is required. `parent_version_id` and `version_diff` are present only when this save supersedes a prior version.

### Step 5 — Confirmation summary

Output to user:

```
✓ House view saved.
  view_name:    <name>
  view_id:      <uuid>
  version_id:   <uuid>
  effective:    <date> through <date>
  tilts active: <count of non-zero tilt fields>
  excludes:     <count>

Active in: portfolio-builder, rebalance, thematic-screen, morning-brief, client-review, explain-portfolio.
Conflict-flag only in: should-i-buy, deep-dive.

To clear:  /parallax-load-house-view --clear
To check: /parallax-load-house-view --status
```

### Step 6 — Operational modes

| Flag | Behavior |
|---|---|
| `--status` | Read `view.yaml`, validate per loader.md §2, print summary block. If no view, print "No active house view." |
| `--clear` | Archive current view to `.archive/`, remove `view.yaml` and `prose.md`. Append audit entry `{"action":"clear"}`. |
| `--extend <date>` | Update `metadata.valid_through` only. Bump `version_id`. Re-pair (recompute view_hash — should be unchanged since tilts/excludes unmodified — and re-write `prose.md` frontmatter). |
| `--re-pair` | Recompute `view_hash` from current `view.yaml` and `prose_body_hash` from current `prose.md` body. Update `prose.md` frontmatter `paired_yaml_hash` AND `prose_body_hash` to match. Use this after a manual prose edit (body or YAML) when the edit was intentional; the command re-anchors both hashes in one step. Note that re-pair intentionally blesses whatever is currently on disk — run only after you have reviewed the edit. |
| `--edit` | Open `view.yaml` in `$EDITOR` (default: `vi`). On save, re-run Steps 3-4 (confirmation gate + write) using the edited content as the draft. |
| `--why <tilt-path>` | On-demand provenance query. Takes a dotted path into the view (e.g., `tilts.factors.momentum`, `tilts.sectors.information_technology`, `tilts.macro_regime.growth`). **Path parsing:** if the caller omits the `tilts.` prefix (e.g., bare `factors.momentum`), prepend it automatically before lookup. The path MUST resolve to a leaf (a scalar value under `tilts`), not a parent map — if the caller passes a parent (e.g., `tilts.macro_regime` without a sub-field), emit `"--why requires a leaf path; <path> is a parent. Try one of: tilts.macro_regime.growth, tilts.macro_regime.inflation, ..."` and exit. Reads the tilt's value from `view.yaml` and the prose from `prose.md`, then runs a targeted LLM re-read: quote the spans of prose.md that support the tilt value (or note "no explicit support in prose — may be auto-applied per loader.md §3 macro_regime mapping"). Output format: one-paragraph answer citing page/line ref if available, the quoted spans verbatim, and an optional note when the tilt appears to be rule-derived rather than prose-extracted. Zero schema cost — runs against existing `prose.md`. If path is a valid leaf but the tilt value is zero (omitted or neutral), before exiting scan `extraction.extraction_notes` for any mention of the field name (e.g., "momentum" for `tilts.factors.momentum`, "information_technology" or "tech" for `tilts.sectors.information_technology`). If found, emit: `"Tilt is currently zero but extraction_notes mentions this field — may reflect an edit at the confirmation gate or a re-extraction that changed the value. Run `--version-history` to inspect prior values."` Then exit. If no mention, exit cleanly with `"Tilt is zero (neutral) — no active tilt to explain."` |
| `--version-history` | Read `audit.jsonl`, filter `action="save"` entries in the current view family, and render a compact chain: `version_id → version_id` with the `version_diff` payload rendered as a short bullet list. If any save has `version_diff_truncated: true`, note that. Use this to audit how the view evolved. |

## Output Format

See Step 5. For operational modes, output the requested status block or success/failure message.

> *Phase 0 internal tool. Phase 1 promotes this to Parallax MCP server tools (`set_house_view`, `get_active_house_view`, etc.) with org-keyed Supabase storage. Schema and loader semantics carry forward unchanged.*
