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

**Hedged or split-sector language is a known failure mode.** When the source uses phrases like:
- "constructive on tech but selective in semis"
- "modestly underweight financials"
- "barbell of growth and value"
- "tactical opportunity"

…do not collapse to a single integer without recording uncertainty. Set the confidence to ≤ 0.7 and note the ambiguity in `extraction.extraction_notes`.

**Macro regime auto-mapping** (per `loader.md` §3): if the source implies a macro regime, populate `tilts.macro_regime` AND compute the factor-tilt deltas. Show the uploader the raw regime + the resulting factor deltas at the gate so they can override.

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

--- TILTS (only non-zero shown) ---
sectors:          <list of sector: tilt>
regions:          <list of region: tilt>
factors:          <list of factor: tilt>      [auto-applied from macro_regime: <fields>]
styles:           <list of style: tilt>
themes:           <list of theme: tilt>
excludes:         <list with reasons>

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

If `Edit specific fields`: loop on `AskUserQuestion` per flagged field, then re-render the gate.
If `Re-extract with hint`: ask for the hint, re-run Step 2 with the hint added to extraction context, re-render the gate.
If `Reject`: abandon, do not write.

### Step 4 — Compute view_hash and write files

On `Confirm`:

1. **Compute** `view_hash`:
   - Take `tilts` and `excludes` sections only.
   - Strip empty/zero fields.
   - Serialize with sorted keys.
   - `view_hash = sha256(canonical_body).hexdigest()`
   - Use Python via Bash: `python3 -c "import hashlib, yaml, sys; data=yaml.safe_load(sys.stdin); ..."`
2. **Generate** `metadata.view_id` (uuid4) — reuse from existing view if updating same view family; new uuid for new family.
3. **Generate** `metadata.version_id` (new uuid4 every save).
4. **Set** `metadata.parent_version_id` to the previous `version_id` if a view existed before this save; null otherwise.
5. **Set** `extraction.uploader_confirmed = true`.
6. **Set** `extraction.extracted_at` and `metadata.upload_timestamp` to now (ISO 8601 UTC).
7. **Write**:
   - Archive existing `~/.parallax/active-house-view/view.yaml` and `prose.md` (if present) to `~/.parallax/active-house-view/.archive/<old_view_id>-<old_version_id>/`.
   - Write new `view.yaml`.
   - Write new `prose.md` with frontmatter `paired_yaml_hash`, `view_id`, `version_id`.
   - If `audit.jsonl` does not exist, create it empty.
8. **Append** an audit entry for the ingest itself:
   ```json
   {"ts":"...","view_id":"...","version_id":"...","skill":"parallax-load-house-view","action":"save","applied":true}
   ```

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
| `--re-pair` | Recompute view_hash from current `view.yaml`. Update `prose.md` frontmatter `paired_yaml_hash` to match. Use this after a manual prose edit when no YAML change was intended. |
| `--edit` | Open `view.yaml` in `$EDITOR` (default: `vi`). On save, re-run Steps 3-4 (confirmation gate + write) using the edited content as the draft. |

## Output Format

See Step 5. For operational modes, output the requested status block or success/failure message.

> *Phase 0 internal tool. Phase 1 promotes this to Parallax MCP server tools (`set_house_view`, `get_active_house_view`, etc.) with org-keyed Supabase storage. Schema and loader semantics carry forward unchanged.*
