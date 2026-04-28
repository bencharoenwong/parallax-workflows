---
name: parallax-load-house-view
description: "Ingest a CIO house view (PDF / text / URL / wizard) into the Parallax workflow system. Extracts structured tilts and excludes, presents a confirmation gate, then saves the view to ~/.parallax/active-house-view/ where every portfolio skill auto-loads it. Use to set, update, re-pair, extend, or clear the active house view. NOT for portfolio construction (use /parallax-portfolio-builder), not for one-off scenario exploration (just describe inline to the relevant skill)."
negative-triggers:
  - Building a portfolio → use /parallax-portfolio-builder
  - One-off scenario / what-if → describe inline to the portfolio skill, don't load as a view
  - Single-stock evaluation → use /parallax-should-i-buy
gotchas:
  - JIT-load _parallax/house-view/schema.yaml before extraction — it is the single source of truth for the YAML shape
  - JIT-load _parallax/house-view/loader.md to see what consumer skills will validate (helps you produce a valid view first time). Note: loader.md §3 (Multiplier mapping) is a normative replay dependency per reasoning chain spec — changes to multiplier values, factor ordering, or composite formula MUST coincide with a `skill_version` bump and break replay byte-identity for chains pinned to prior versions.
  - PDF input — use the Read tool with `pages` parameter for >10 pages; do NOT defuddle PDFs (we want figure context)
  - URL input — use the defuddle skill if Bash is available, else WebFetch
  - Confirmation gate is REQUIRED — the uploader must explicitly confirm extracted YAML before save (uploader_confirmed=true). Saving without confirmation breaks downstream loaders.
  - Always compute view_hash from the canonical tilts body per schema.yaml §"view_hash computation" — sorted keys, no comments, no empty fields
  - Ask uploader_role and basis_statement via AskUserQuestion — these are required-at-institutional fields and need explicit human input
  - Auto-applied macro_regime → factor tilts (loader.md §3) MUST be surfaced to the uploader at the gate, not silently applied
  - Confirmation gate persists a pre-edit snapshot (Step 3a) when uploader chooses 'Edit specific fields' — writes extractor's pristine draft to `.archive/<version>/pre_edit.yaml` alongside the superseded view. No-edit confirmations skip this.
  - Every extraction attempt (Step 3b) logs an `extraction_attempt` audit entry to `audit.jsonl` — whether or not it becomes a save. Capture disposition (confirmed/edited/re_extracted/rejected) + draft_yaml_hash per loader.md §6.2.
  - Save (Step 4 step 10) computes a `version_diff` block vs `parent_version_id` and stashes it on the save audit entry. Only when this save supersedes a prior version.
  - Calibration manifest: Invoke `manifest_cache.load_manifest()` during Step 4 (Write Phase) to resolve active calibration. Handle `DeadStateNoFallback` or signature errors by logging a warning and falling back to the bundled-values default.
  - Reasoning Chains: Every save MUST invoke `chain_emit.emit_chain()` (or `emit_phase_0_chain()`) to produce a compliance artifact at `~/.parallax/reasoning-chains/`.
  - Compliance Export: Use `--export <view_id>` to generate a regulator-grade bundle. Validates hash-chain integrity before packaging.
  - `--why <tilt-path>` is on-demand. Reads `provenance.yaml` first when present; the latest derivation entry for the leaf controls the answer. If type is `macro_regime_rule`, cite `rule_ref` + `trigger`. If type is `prose_extraction` or no `provenance.yaml` exists (legacy view), fall back to the prose.md targeted re-read. The saved house view never carries Parallax-derived overlays — augmentation happens just-in-time at consumer-skill use, with provenance recorded on the consuming portfolio/screen artifact, not on the view itself.
  - **Operator verification:** see [examples/testing-posture.md](../../examples/testing-posture.md)
---

# Load House View

Ingest a CIO house view (PDF / text / URL / wizard) into the Parallax workflow system.

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
/parallax-load-house-view --export <view_id>        # export regulator-grade compliance bundle
/parallax-load-house-view --why tilts.factors.momentum             # on-demand: why is this tilt set to what it is?
/parallax-load-house-view --why tilts.sectors.information_technology
/parallax-load-house-view --why factors.momentum                   # bare form — `tilts.` prefix auto-prepended
/parallax-load-house-view --version-history        # show parent chain + per-version diffs from audit.jsonl
```

## Where the view lives

`~/.parallax/active-house-view/`
- `view.yaml` — canonical YAML per `_parallax/house-view/schema.yaml`
- `prose.md` — verbatim CIO narrative with `paired_yaml_hash` frontmatter
- `provenance.yaml` — per-tilt derivation records (prose extraction / macro-regime rule / manual edit)
- `audit.jsonl` — append-only hash-chained log (consumers append; this skill initializes)
- `.archive/<view_id>-<version_id>/` — superseded versions (kept for `parent_version_id` traceability)

If `~/.parallax/active-house-view/` does not exist, create it on first save. Files are written `0600`, the directory is `0700`.

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. JIT-load `_parallax/house-view/schema.yaml` (canonical structure) and `_parallax/house-view/loader.md` (consumer expectations) before extraction.

### Step 1 — Detect mode and load source
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

Pillars are usually coarse — a prose view rarely articulates sub-factor level. If the source is silent on a pillar, leave at 0 and flag `pillars` extraction_confidence ≤ 0.6. Pillar scores are encoding-only (per loader.md §3): they are stored but do NOT auto-translate into factor multipliers.

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

> **Architectural note:** the saved house view is PURE — it carries only what the source document said + what the uploader confirmed at this gate. Parallax-derived augmentation is deferred to **just-in-time** lookup at consumer-skill use (e.g., when `/parallax-portfolio-builder` detects the active view is silent on a dimension it needs for a specific portfolio decision). The augmentation provenance lives on the consuming portfolio/screen artifact, never on the saved house view. The `gap_detect` and `gap_suggest` modules in `_parallax/house-view/` remain — they get JIT-loaded by consumer skills.

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
1a. **Load Calibration Manifest:** Call `manifest_cache.load_manifest(fresh_manifest=None)` to resolve the active manifest. Capture `manifest` and `status` (handle exceptions by falling back to `status="PHASE_0_FALLBACK"`).
1b. **Generate Provenance:** Create a `provenance.yaml` artifact capturing the evidence for every non-neutral tilt.
    - Classification (per schema.yaml §"Classification taxonomy"): `prose_extraction` (LLM-derived from CIO source), `macro_regime_rule` (auto-mapped per loader.md §3), or `manual_edit` (uploader edit at confirmation gate). Parallax-derived values are NEVER folded into the saved view — consumer skills carry that provenance per portfolio/screen artifact at JIT use time. (Legacy views may carry an additional `parallax_data_fill` class from a deprecated ingest-time-augment design; supported for back-compat read but never produced at save time.)
    - Per-class field tables in schema.yaml. Baseline fields shared by all classes: `confidence` (0.0-1.0), `rationale` (≤500 chars). Type-specific: `source_span` (prose_extraction), `rule_ref`+`trigger` (macro_regime_rule), `prior_value`+`edit_notes` (manual_edit).
1c. **Compute Provenance Hash:** `provenance_hash = sha256(JCS(provenance_data))`.
2. **Generate** `metadata.view_id` (uuid4) — reuse from existing view if updating same view family; new uuid for new family.
3. **Generate** `metadata.version_id` (new uuid4 every save).
3a. **Inject Hash:** Set `metadata.provenance_hash` in the draft `view.yaml` to the value computed in 1c.
4. **Set** `metadata.parent_version_id` to the previous `version_id` if a view existed before this save; null otherwise.
5. **Set** `extraction.uploader_confirmed = true`.
6. **Set** `extraction.extracted_at` and `metadata.upload_timestamp` to now (ISO 8601 UTC).
6a. **Set** `metadata.schema_version = 1` (current schema version — see schema.yaml). Every new save writes this; legacy views without it read as v0 at load time.
6b. **Set** `metadata.calibration_status`:
    - If `status == "ACTIVE"` AND `manifest.provenance.methodology_section != "GUESS"` AND `manifest.provenance.backtest_ref` is non-null: set to `"empirical_phase1"`.
    - Otherwise: set to `"heuristic_phase0"`.
7. **Construct the prose body** (the markdown that will live below the frontmatter — verbatim CIO narrative).
8. **Compute** `prose_body_hash = sha256(prose_body_utf8).hexdigest()` per schema.yaml §"prose_body_hash computation". The hash is over the bytes that will appear AFTER the closing `---` of the frontmatter — not over the whole file. Compute on the finalized body before writing.
9. **Write**:
   - Archive existing `~/.parallax/active-house-view/view.yaml` and `prose.md` (if present) to `~/.parallax/active-house-view/.archive/<old_view_id>-<old_version_id>/`.
   - Write new `view.yaml`.
   - Write new `prose.md` with frontmatter **four fields in this order**: `paired_yaml_hash`, `prose_body_hash`, `view_id`, `version_id`. Frontmatter is the only part of the file NOT covered by `prose_body_hash`.
   - Write new `provenance.yaml`, then **immediately `chmod 0o600`** (security audit Finding 6 — file carries source-extracted prose snippets; default umask perms would leave it world-readable on shared workstations). Also `chmod 0o700` the parent dir `~/.parallax/active-house-view/` if it was created in this run.
   - If `audit.jsonl` does not exist, create it empty AND **`chmod 0o600` on creation** (security audit Finding 5 — closes the window between empty-file creation and the first `audit_chain.append_entry` that would otherwise apply the perm). The `audit_chain` module also re-enforces 0600 on every append as defense in depth.
10. **Compute version-diff (Layer 3)** — only when `metadata.parent_version_id` is non-null (i.e., this save supersedes a prior version in the same view family):
    0. **Archive-missing guard.** If `.archive/<parent_view_id>-<parent_version_id>/view.yaml` does not exist (fresh install, manual deletion, or the parent was cleared before this update), skip sub-steps 1-2 and set `version_diff_truncated: true` with `notes: "parent_archive_missing: <parent_view_id>-<parent_version_id>"` on the save audit entry. Do not emit a `version_diff` field. Continue to save — the missing-archive case is survivable, not a save blocker.
    1. Read the parent's archived `view.yaml` from `.archive/<parent_view_id>-<parent_version_id>/view.yaml`.
    2. Compute a flat diff restricted to the `tilts` and `excludes` subtrees (same scope as `view_hash`). For each dotted path (`tilts.sectors.health_care`, `tilts.factors.momentum`, `excludes[0]`, etc.) that differs, record `{path: [old_value, new_value]}`. Use `null` for either side when the key is absent on that side. Cap output at 40 entries; if more, truncate and set `version_diff_truncated: true`.
    3. Stash as `version_diff` on the save audit entry in step 11 below.
11. **Append Hash-Chained Audit Entry:**
    - Prepare entry payload:
      ```json
      {"schema_version":1,"ts":"...","view_id":"...","version_id":"...","view_hash":"...","skill":"parallax-load-house-view","action":"save","applied":true,"parent_version_id":"...","provenance_hash":"...","version_diff":{...}}
      ```
    - Invoke `audit_chain.append_entry(audit_path, entry_data)` to handle `prev_entry_hash` linking and RFC 8785 canonicalization.
11a. **Emit Reasoning Chain:**
    - Call `chain_emit.emit_chain()` (or `emit_phase_0_chain()`) to produce the reasoning chain.
    - Since `load-house-view` produces a view rather than a portfolio, pass dummy values: `base_scores={"response_inline": {}, "response_hash": "0"*64}` and `final_portfolio={"weights": {}}`.
    - Use `run_id = "01HZ..."` (generate a unique ULID/UUID) and `skill_version = "parallax-load-house-view@1.0.0"`.
    - For `emit_chain` (ACTIVE status), also pass `manifest_dict=manifest`, `manifest_ref_hash`, and `signing_payload_hash` (from the manifest verification result).
    - Artifact is written to `~/.parallax/reasoning-chains/<YYYY-MM>/<run_id>.yaml`.

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
| `--export <view_id>` | Call `audit_export.create_bundle()` to package view + narrative + provenance + full hash-chained audit trail into a tarball. Fails if audit chain is broken. |
| `--why <tilt-path>` | On-demand provenance query. Takes a dotted path into the view (e.g., `tilts.factors.momentum`, `tilts.sectors.information_technology`, `tilts.macro_regime.growth`). **Path parsing:** if the caller omits the `tilts.` prefix (e.g., bare `factors.momentum`), prepend it automatically before lookup. The path MUST resolve to a leaf (a scalar value under `tilts`), not a parent map — if the caller passes a parent (e.g., `tilts.macro_regime` without a sub-field), emit `"--why requires a leaf path; <path> is a parent. Try one of: tilts.macro_regime.growth, tilts.macro_regime.inflation, ..."` and exit. **Provenance resolution order:** (1) Read `provenance.yaml` if present and look up the leaf's `derivation` list. The LAST entry in `derivation` is the effective source (later entries supersede earlier ones — e.g., a `manual_edit` after a `prose_extraction`). Branch on `type`: (a) `prose_extraction` → quote `source_span` verbatim and emit "Source: CIO prose, span '<source_span>' (confidence <c>)"; (b) `macro_regime_rule` → emit "Source: loader.md auto-mapping. Rule: <rule_ref>. Trigger: <trigger>. Confidence <c>."; (c) `manual_edit` → emit "Source: manual edit at confirmation gate. Prior value: <prior_value>. Notes: <edit_notes>." plus a recursive call to surface the entry BEFORE the edit (so the auditor sees both the original derivation and the override). The `parallax_data_fill` branch is not produced at ingest scope — Parallax-derived values no longer appear in saved-view provenance. (Legacy views from a deprecated ingest-time-augment design may still carry `parallax_data_fill` entries; emit "Source: legacy Parallax gap-fill. Tool: <source_tool> with args <source_call_args>. Snippet: '<source_snippet>'. Data as of <data_as_of>. NOT from the uploaded document — captured at ingest, may have drifted." for back-compat reading.) (2) If `provenance.yaml` is absent or the leaf has no entry (legacy view, or zero-tilt path), fall back to the prose.md targeted re-read: quote the spans of prose.md that support the tilt value, or note "no explicit support in prose — may be auto-applied per loader.md §3 macro_regime mapping". Zero schema cost in the fallback path — runs against existing `prose.md`. If path is a valid leaf but the tilt value is zero (omitted or neutral), before exiting scan `extraction.extraction_notes` for any mention of the field name (e.g., "momentum" for `tilts.factors.momentum`, "information_technology" or "tech" for `tilts.sectors.information_technology`). If found, emit: `"Tilt is currently zero but extraction_notes mentions this field — may reflect an edit at the confirmation gate or a re-extraction that changed the value. Run `--version-history` to inspect prior values."` Then exit. If no mention, exit cleanly with `"Tilt is zero (neutral) — no active tilt to explain."` |
| `--version-history` | Read `audit.jsonl`, filter `action="save"` entries in the current view family, and render a compact chain: `version_id → version_id` with the `version_diff` payload rendered as a short bullet list. If any save has `version_diff_truncated: true`, note that. Use this to audit how the view evolved. |

## Output Format

See Step 5. For operational modes, output the requested status block or success/failure message.

> *Local-filesystem implementation. A managed, org-keyed version (`set_house_view`, `get_active_house_view`, etc., backed by Supabase) is on the roadmap; schema and loader semantics carry forward unchanged.*
