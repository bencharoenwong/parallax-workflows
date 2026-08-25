---
name: parallax-load-house-view
description: "Ingest a CIO house view (PDF / text / URL / wizard) into the Parallax workflow system. Extracts structured tilts and excludes, presents a confirmation gate, then saves the view to ~/.parallax/active-house-view/ where every portfolio skill auto-loads it. Use to set, update, re-pair, extend, or clear the active house view. NOT for portfolio construction (use /parallax-portfolio-builder), not for one-off scenario exploration (just describe inline to the relevant skill)."
---

# Load House View

## When not to use

- Building a portfolio → use /parallax-portfolio-builder
- One-off scenario / what-if → describe inline to the portfolio skill, don't load as a view
- Single-stock evaluation → use /parallax-should-i-buy

## Gotchas

- JIT-load _parallax/house-view/schema.yaml before extraction — it is the single source of truth for the YAML shape
- JIT-load _parallax/house-view/loader.md to see what consumer skills will validate (helps you produce a valid view first time). Note: loader.md §3 (Multiplier mapping) is a normative replay dependency per reasoning chain spec — changes to multiplier values, factor ordering, or composite formula MUST coincide with a `skill_version` bump and break replay byte-identity for chains pinned to prior versions.
- PDF input — use the Read tool with `pages` parameter for >10 pages; do NOT defuddle PDFs (we want figure context)
- **PDF extraction is not deterministic, especially on large PDFs.** LLM-based text extraction can read the same PDF differently across runs. This risk is highest on long documents processed in chunks (Step 1). The confirmation gate (Step 3) is the safeguard: never treat draft YAML from a PDF as final without uploader review, and never re-run extraction silently to "fix" a value the uploader did not flag.
- URL input — use the defuddle skill if Bash is available, else WebFetch
- Confirmation gate is REQUIRED — the uploader must explicitly confirm extracted YAML before save (uploader_confirmed=true). Saving without confirmation breaks downstream loaders.
- Always compute view_hash from the canonical tilts body per schema.yaml §"view_hash computation" — sorted keys, no comments, no empty fields
- Ask uploader_role and basis_statement via AskUserQuestion — these are required-at-institutional fields and need explicit human input
- Auto-applied macro_regime → factor tilts (loader.md §3) MUST be surfaced to the uploader at the gate, not silently applied
- Confirmation gate persists a pre-edit snapshot (Step 3a) when uploader chooses 'Edit specific fields' — writes extractor's pristine draft to `.archive/<version>/pre_edit.yaml` alongside the superseded view. No-edit confirmations skip this.
- Every extraction attempt (Step 3b) logs an `extraction_attempt` audit entry to `audit.jsonl` — whether or not it becomes a save. Capture disposition (confirmed/edited/re_extracted/rejected) + draft_yaml_hash per loader.md §6.2. Append it with `audit_chain.append_entry`, never with the Write tool (Step 3b names the call).
- Save (Step 4 step 10) computes a `version_diff` block vs `parent_version_id` and stashes it on the save audit entry. Only when this save supersedes a prior version.
- Calibration manifest: Invoke `manifest_cache.load_manifest()` during Step 4 (Write Phase) to resolve active calibration. Handle `DeadStateNoFallback` or signature errors by logging a warning and falling back to the bundled-values default.
- Reasoning Chains: Every save MUST invoke `chain_emit.emit_chain()` (or `emit_phase_0_chain()`) to produce a compliance artifact at `~/.parallax/reasoning-chains/`.
- Compliance Export: Use `--export <view_id>` to generate a regulator-grade bundle. Validates hash-chain integrity before packaging.
- `--why <tilt-path>` is on-demand. Reads `provenance.yaml` first when present; the latest derivation entry for the leaf controls the answer. If type is `macro_regime_rule`, cite `rule_ref` + `trigger`. If type is `prose_extraction` or no `provenance.yaml` exists (legacy view), fall back to the prose.md targeted re-read. The saved house view never carries Parallax-derived overlays — augmentation happens just-in-time at consumer-skill use, with provenance recorded on the consuming portfolio/screen artifact, not on the view itself.
- **Operator verification:** see [examples/testing-posture.md](../../examples/testing-posture.md)

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

If a path or URL was given: read the source via the appropriate tool. For PDFs:
- **≤10 pages:** use `Read` with `pages` parameter in one call; proceed to Step 2.
- **>10 pages:** use streaming extraction — read in 5-page chunks via `Read` with `pages: "N-(N+4)"`, parse YAML incrementally, merge results. Track `extraction_confidence` per chunk (if a chunk fails to parse, flag ≤ 0.5 for that chunk and continue). Merged result proceeds to Step 2 with average confidence score across chunks.

**Determinism note.** Chunked extraction on a large PDF is the least deterministic path in this skill — re-running the same document can produce different draft values. Do not present it to the uploader as a precise read of the source. Surface a lower confidence when the source is long or dense, and rely on the Step 3 confirmation gate, not on repeated extraction attempts, to reach a value the uploader trusts.

For URLs: use `defuddle` or `WebFetch`. Skip the wizard and proceed to Step 2.

If no source was given (wizard mode): walk the uploader through the schema interactively in the order below, using one `AskUserQuestion` invocation per numbered group (not eight separate prompts). Skip any dimension the uploader leaves neutral.

1. **Identity:** view name, uploader role (CIO / PM / Investment Committee / Strategist / Other), basis statement, effective date, valid_through (or `auto_expire_days`).
2. **Macro regime:** growth (slowing / steady / accelerating / null), inflation (disinflation / benign / sticky / accelerating / null), rates (cutting / holding / hiking / null), risk_appetite (risk_on / neutral / risk_off / null).
3. **Components:** `econometrics_phase` (macro backdrop), `valuation_state` (valuation), `market_entropy` (market state), `psychological_wavelength` (sentiment) — each on -2 / -1 / 0 / +1 / +2.
4. **Factors:** value, profitability, momentum, low_volatility, trading_signals — each on -2 / -1 / 0 / +1 / +2.
5. **Sectors:** present GICS sector keys; uploader picks the ones with a view, then sets each on the same -2 to +2 scale.
6. **Regions:** present broad keys (developed_markets, emerging_markets, etc.); offer per-country drill-down only if the uploader names specific countries.
7. **Styles & themes:** offer a free-text follow-up for any thematic conviction.
8. **Excludes:** free-text list; for each exclude, ask for a one-sentence reason.

Default to multi-select where the schema allows. Capture `extraction_confidence` as 1.0 for wizard-supplied values (the uploader is the source).

### Step 2 — Extract structured tilts

Produce a draft YAML conforming to `_parallax/house-view/schema.yaml`. For each field, also produce a `extraction_confidence` score (0.0-1.0) representing your confidence in the extraction.

**Component extraction.** Before extracting sector/region/factor tilts, read the source for component-level conviction and populate `tilts.pillars` (field identifier preserved for data-contract stability):

| Component | Look for | Map to |
|---|---|---|
| `econometrics_phase` | Macro backdrop framing — "constructive on growth", "recessionary", "stagflation", "soft landing" | +2 very constructive → -2 recessionary/stress |
| `valuation_state` | Valuation commentary — "stretched multiples", "cheap vs history", "PE reasonable", "dispersion" | +2 very undervalued → -2 highly overvalued |
| `market_entropy` | Technicals/vol/flows — "orderly rotation", "elevated VIX", "breadth deteriorating", "heavy issuance" | +2 low/ordered → -2 high/disordered |
| `psychological_wavelength` | Sentiment/RORO — "risk-on backdrop", "frothy retail", "capitulation", "fear index elevated" | +2 very positive → -2 very negative |

Components are usually coarse — a prose view rarely articulates sub-factor level. If the source is silent on a component, leave at 0 and flag `pillars` extraction_confidence ≤ 0.6. Component scores are encoding-only (per loader.md §3): they are stored but do NOT auto-translate into factor multipliers.

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

> **Shared module.** The gate display + disposition loop lives in `_parallax/house-view/gate_present.py` so the in-progress `/parallax-make-house-view` skill can reuse it. This Step describes how `parallax-load-house-view` *uses* the module; the module itself is the source of truth for display rendering and disposition vocabulary. Step 3a (pre-edit snapshot persistence) and Step 3b (extraction_attempt audit logging) remain caller-side responsibilities — the module returns the snapshot in `GateResult` but never writes audit rows or `.archive/<...>/pre_edit.yaml`. Step 3b's row is appended with `audit_chain.append_entry` (see §3b); it does not go through `view_commit`, which derives `action` from its `--mode` and has no extraction-attempt mode.

JIT-load `_parallax/house-view/gate_present.py` and construct a `GateContext`:

- `source_label`: the filename / URL / `"wizard"` identifier from Step 1.
- `uploader_present=True` (ingest framing — "Source:" prefix, extraction verb tense).
- `confidence_map`: per-category confidence from `extraction.extraction_confidence` (keys: `sectors`, `regions`, `factors`, `macro_regime`; the maker path additionally carries `pillars`, which this skill omits).
- `extraction_attempt_action=True` (this skill always logs the `extraction_attempt` row per §3b below).
- `disposition_options=["confirm", "edit", "re_extract", "reject"]`.

Call `gate_present.run_gate_loop(draft, context, dispose_fn=..., edit_fn=...)`. The two callbacks bridge to `AskUserQuestion`:

- `dispose_fn(prompt) -> str` — print `prompt.display` verbatim, then ask `prompt.question` with `prompt.options` via `AskUserQuestion`. Return the chosen disposition keyword.
- `edit_fn(current_draft, context) -> (edited_draft, edit_notes | None)` — loop on `AskUserQuestion` per flagged field (the LOW-CONFIDENCE block from the rendered prompt is the suggested order). After all edits land, optionally ask "One line on what you changed and why? (optional)" and pass the response as `edit_notes`. Return the post-edit draft. The module re-renders the gate and re-invokes `dispose_fn` until the uploader confirms or branches to a terminal disposition.

The module returns a `GateResult` with `disposition` set to one of `"confirm"`, `"edited"`, `"re_extracted"`, or `"rejected"`. Branch as follows:

- **`"confirm"`** — proceed to Step 4 with `result.final_draft`. No pre-edit snapshot to persist. Write the `extraction_attempt` audit row per §3b with `disposition="confirmed"` and `draft_yaml_hash` = sha256(canonical) of `result.final_draft`.
- **`"edited"`** — proceed to Step 3a using `result.pre_edit_snapshot` (the pristine pre-edit draft, which the module captured automatically on first entry into the edit branch) and optionally `result.edit_notes`. Then write the `extraction_attempt` audit row per §3b with `disposition="edited"` and `draft_yaml_hash` = sha256(canonical) of the **pre-edit** snapshot — not the post-edit confirmed draft (that hash goes into `view.yaml` via Step 4's `view_hash`). The pair `extraction_attempt.draft_yaml_hash` + `save.view_hash` is the audit signature of "what the extractor produced → what the uploader shipped." Proceed to Step 4 with `result.final_draft`.
- **`"re_extracted"`** — discard any holding buffer; do not write `pre_edit.yaml`. Write the `extraction_attempt` audit row per §3b with `disposition="re_extracted"`, the rejected draft's hash, and the hint (collected via a follow-up `AskUserQuestion`). Re-run Step 2 with the hint added to extraction context and return to Step 3.
- **`"rejected"`** — discard any holding buffer. Write the `extraction_attempt` audit row per §3b with `disposition="rejected"`. Abandon; do not write `view.yaml`.

#### Step 3a — Pre-edit snapshot (Layer 2)

When the uploader chooses `Edit specific fields` (not `Confirm` on the pristine draft):

1. Serialize the current pre-edit draft YAML (the extractor's output, pre-modification) to a holding buffer.
2. After all edits land AND the uploader `Confirm`s the edited version, write the pre-edit snapshot to `~/.parallax/active-house-view/.archive/<new_view_id>-<new_version_id>/pre_edit.yaml`. (The directory is the SAME one Step 4 step 9 creates to archive the superseded view — both files share the slot.)
3. Optionally ask the uploader (single question, skippable): "One line on what you changed and why? (optional — press Enter to skip)". If non-empty, save as `~/.parallax/active-house-view/.archive/<new_view_id>-<new_version_id>/edit_notes.md`.

If the uploader confirms the pristine draft (no edits), skip Step 3a entirely — there's nothing to snapshot.

#### Step 3b — Extraction attempt logging (Layer 5, folded into audit.jsonl)

Every extraction attempt — including re-extracts and rejections that never become saves — appends one `action: "extraction_attempt"` entry to `audit.jsonl` per loader.md §6.1.

**How to write it.** Append the row with `audit_chain.append_entry` — the append-only path that takes the view's `flock`, computes `prev_entry_hash`, and never replaces the file. It is the one sanctioned direct write to `audit.jsonl`; the Write tool is not (see Step 4 Stage 2). `view_commit` cannot produce this row: it derives `audit_entry["action"]` from `--mode`, and there is no `extraction_attempt` mode. Run exactly:

```bash
cd <repo>/skills/_parallax/house-view && python3 -c '
import json, os, sys, audit_chain
from pathlib import Path
view_dir = Path(os.environ.get("PARALLAX_HOUSE_VIEW_DIR")
                or Path.home() / ".parallax" / "active-house-view").expanduser()
view_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
print(json.dumps(audit_chain.append_entry(view_dir / "audit.jsonl", json.load(sys.stdin))))
' <<'ROW'
{"schema_version": 1, "ts": "...", "skill": "parallax-load-house-view",
 "action": "extraction_attempt", "applied": false, "query_summary": "...",
 "disposition": "confirmed", "draft_yaml_hash": "..."}
ROW
```

Note `import audit_chain` and `audit_chain.append_entry(...)` — module-attribute access, not a `from`-import. The view directory resolves the same way `view_commit` resolves it (`$PARALLAX_HOUSE_VIEW_DIR`, else `~/.parallax/active-house-view/`), which is why the snippet does not hardcode a path. On a fresh install the directory is created `0700`; `append_entry` writes the file `0600` and mints the `chain_root` on the empty chain.

Required fields: `schema_version`, `ts`, `skill`, `action`, `applied=false`. Conditional: `query_summary` (source file basename or URL), `disposition` (one of: `confirmed`, `edited`, `re_extracted`, `rejected`), `draft_yaml_hash` (sha256 of the draft the uploader saw; lets us correlate with a later save's `view_hash`), `extraction_duration_ms` (optional, wall-clock from extraction start to disposition), `hint` (when disposition=re_extracted, the hint text truncated to 200 chars).

A successful `save` after a confirmed draft still emits its own `action: "save"` entry per Step 4 — the two actions are independent. An `extraction_attempt` with `disposition=confirmed` tells you "the uploader confirmed this draft"; the subsequent `save` tells you "this draft was persisted." Rejected or re-extracted drafts have no matching save.

### Step 4 — Compute hashes and write files

On `Confirm`:

1. **Compute** `view_hash` per schema.yaml §"view_hash computation" (pinned algorithm; the reference Python snippet is reproduced in `skills/_parallax/house-view/tests/test_view_hash.py`). Keep the implementation byte-identical to the reference — any deviation will break hash round-trip.
1a. **Load Calibration Manifest (async-ready):** Call `manifest_cache.load_manifest(fresh_manifest=None)` to resolve the active manifest. Capture `manifest` and `status` (handle exceptions by falling back to `status="PHASE_0_FALLBACK"`). If manifest caching supports async lookup, use non-blocking I/O to avoid stalling other Step 4 operations.
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
9. **Write (atomic-safe per-file pattern)**:
   - **Pre-write validation:** Before firing any writes, validate that all required fields are set and the directory `~/.parallax/active-house-view/` is writable. If not writable, fail loudly and do not proceed.
   - **Stage 1: Compute version-diff BEFORE writes** — only when `metadata.parent_version_id` is non-null (i.e., this save supersedes a prior version in the same view family). **Must happen before archiving to avoid async race conditions:**
     0. **Current-view guard.** If the current active `~/.parallax/active-house-view/view.yaml` does not exist (fresh install), set `version_diff_truncated: true` with `notes: "no_prior_version"` on the save audit entry. Do not emit a `version_diff` field. Continue to save.
     1. Read the current active `view.yaml` (the prior version being superseded).
     2. Compute a flat diff restricted to the `tilts` and `excludes` subtrees (same scope as `view_hash`) by comparing the prior `view.yaml` with the new draft. For each dotted path (`tilts.sectors.health_care`, `tilts.factors.momentum`, `excludes[0]`, etc.) that differs, record `{path: [old_value, new_value]}`. Use `null` for either side when the key is absent on that side. Cap output at 40 entries; if more, truncate and set `version_diff_truncated: true`.
     3. Stash computed diff for use in the `audit_entry` passed to `view_commit` in Stage 2 below.

     Stage 1's read happens outside the lock. The only thing that makes that safe is `expected_identity`, which `view_commit` re-checks under the lock and refuses to write past if it moved. Do not remove it as redundant.
   - **Stage 1b: Archive (non-blocking, best-effort):** After version-diff is computed, archive the current active `~/.parallax/active-house-view/view.yaml` and `prose.md` to `~/.parallax/active-house-view/.archive/<old_view_id>-<old_version_id>/` **asynchronously**. Archive failures are non-blocking — log a warning but do not abort the save. (The archive is a courtesy; it is not load-bearing for correctness.)
   - **Stage 2 — Commit.** Use the staging directory `$HOME/.parallax/.staging` — create it with `mkdir -p "$staging" && chmod 700 "$staging"` (a bare `mkdir` inherits the shell's umask, typically `0755`; the `chmod 700` is what protects the source-extracted content in `provenance.yaml` while it sits outside the view directory, and a fixed path under `$HOME` avoids the world-writable-directory exposure `/tmp` carries). Write the three artifacts into `$staging` with the Write tool (`view.yaml` with frontmatter fields set per the earlier substeps, `prose.md` with frontmatter **four fields in this order** — `paired_yaml_hash`, `prose_body_hash`, `view_id`, `version_id` — frontmatter being the only part of the file NOT covered by `prose_body_hash`, and `provenance.yaml`), **and write the plan JSON itself into `$staging/plan.json` with the Write tool too** — never type the plan into a shell heredoc. The plan carries document-derived text (the `version_diff` values come from the CIO draft's `tilts`/`excludes`), and a heredoc would hand that text to the shell for command substitution; a file written by the Write tool never passes through a shell. Because the staging path is known, every `path` in the plan is a literal absolute path (no `~`, no variables — `view_commit` reads the file as-is). Never write into `~/.parallax/active-house-view/` yourself. Remove `$staging` unconditionally after the commit (shown in the block) — the contents are reconstructible, so leaving source-extracted output behind on a failed commit is the worse trade — and end the block with `exit "$status"` so the Bash tool reports `view_commit`'s own exit code rather than the cleanup's.

     **`audit.jsonl` is append vs replace, not touch vs don't-touch.** Never stage, rename, copy over, or overwrite it, and never write it with the Write tool — every one of those replaces the file, which swaps the inode out from under the append path and truncates the chain into something that still verifies green. Appending through `audit_chain.append_entry` is the one sanctioned direct write (that is how Step 3b's `extraction_attempt` row lands, and `view_commit` itself appends through the same call). Every commit of the canonical artifacts — `view.yaml`, `prose.md`, `provenance.yaml` — goes through `view_commit`, which appends its own witnessing row. Then run exactly:

     ```bash
     staging="$HOME/.parallax/.staging"
     mkdir -p "$staging" && chmod 700 "$staging"
     # write view.yaml, prose.md, provenance.yaml, and plan.json into "$staging" via the Write tool, then:
     cd <repo>/skills/_parallax/house-view && python3 -m view_commit --mode save --staging-dir "$staging" < "$staging/plan.json"
     status=$?
     rm -rf "$staging"
     exit "$status"
     ```

     `plan.json` (written with the Write tool; `<home>` is the literal expansion of `$HOME`):

     ```json
     {"write": {"view.yaml": {"path": "<home>/.parallax/.staging/view.yaml"},
                "prose.md": {"path": "<home>/.parallax/.staging/prose.md"},
                "provenance.yaml": {"path": "<home>/.parallax/.staging/provenance.yaml"}},
      "audit_entry": {"schema_version": 1, "ts": "...", "view_id": "...", "version_id": "...",
                      "view_hash": "...", "skill": "parallax-load-house-view", "applied": true,
                      "parent_version_id": "...", "provenance_hash": "...", "version_diff": {}},
      "expected_identity": {"parent_version_id": "<the value read at Stage 1, or null on a fresh install>"}}
     ```

     On a fresh install with no prior view, pass `"parent_version_id": null` — JSON `null`, not `""` and not an omitted key. The key is required for `--mode save`; an empty string fails the identity check and omitting it fails the required-keys check.

     Do not pass `--dir`. `view_commit` resolves the view directory from `$PARALLAX_HOUSE_VIEW_DIR`, falling back to `~/.parallax/active-house-view/` — the same order `view_status.py` and loader.md use. Hardcoding `--dir` overrides a per-org directory the operator set deliberately.

     `--staging-dir` is the same `$staging` directory the artifacts and `plan.json` were just written into, and it is a containment boundary, not a convenience. A `{"path": ...}` value is read **only** when it resolves to a file sitting directly in that directory; a path elsewhere, a `..` that climbs out, and a symlink inside the directory whose target resolves outside it are each refused before the file is opened. Omit the flag and every `path` ref is refused — so pass it whenever the plan uses one, and give it one directory rather than a parent that happens to contain several. The boundary exists because the plan is assembled after reading an untrusted CIO document: without it, text in that document could name any local file and have its contents committed into the 7-year record. A `path` must also resolve outside the view directory — `view_commit` rejects one that resolves inside it, since reading the file you are about to replace would silently no-op the change — and the staging directory itself may not be, contain, or sit inside the view directory. `view_commit` sets `audit_entry.action` from `--mode` itself; do not set `action` in the plan. `audit_entry.view_hash` is required whenever `view.yaml` is in the write set — a row that can't identify the view it witnesses defeats the row-vs-bytes check.

     Exit 0 prints the committed audit row as JSON on stdout — that row already carries `prev_entry_hash` linking and is authoritative; nothing further needs to append it. Exit 2 means the commit was refused and **nothing was written**; surface the message verbatim and do not retry blindly — read why first (a moved `expected_identity` means the active view changed since Stage 1's read). Exit 1 means something else went wrong, including the rare case where the artifacts were renamed into place but the audit row could not be appended — that failure is loud and names its own recovery in the message; follow it rather than hand-editing the chain.
10. (Moved to Step 9 Stage 1 to avoid async race conditions.)
11a. **Emit Reasoning Chain (deferred, non-blocking):**
    - This step can be deferred to async completion AFTER the save confirmation is returned to the user. It does not block user confirmation in Step 5.
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

Try it:
  /parallax-portfolio-builder "<your thesis>"     # build a portfolio with this view applied
  /parallax-rebalance [holdings]                  # rebalance against the active view

Audit & inspect:
  /parallax-load-house-view --status              # active view summary
  /parallax-load-house-view --why <tilt-path>     # why is this tilt set to what it is?
  /parallax-load-house-view --version-history     # how did this view evolve?
  /parallax-load-house-view --export <view_id>    # regulator-grade compliance bundle

To clear:  /parallax-load-house-view --clear
```

### Step 6 — Operational modes

| Flag | Behavior |
|---|---|
| `--status` | Read `view.yaml`, validate per loader.md §2, then invoke `view_status.compute_status()` (or shell `python -m view_status`) to obtain the canonical status. Print the helper's `banner` field verbatim as the first line, then render the status block defined in §"Status block" below. The banner is the single source of truth for state wording across operator LLMs — do NOT paraphrase. If no view, the helper returns `state="none"` with the standard "No active house view" banner. |
| `--clear` | **Archives** the current view, then removes **all three** artifacts (`view.yaml`, `prose.md`, `provenance.yaml`) via `view_commit --mode clear`. `provenance.yaml` was previously left behind; a cleared view's provenance is stale, and `audit_export.py` raises when `provenance.yaml` is *missing*, so leaving it meant a later export could silently bundle a prior view's evidence rather than failing loudly. Writes an audit row (`destination` + `reason` required); `destination` is the archive directory, so the archive must happen first. See invocation below. |
| `--extend <date>` | Update `metadata.valid_through` only. Bump `version_id`. Recompute `view_hash` (should be unchanged since tilts/excludes unmodified) and re-write `prose.md` frontmatter. Commits both files plus an audit row via `view_commit --mode extend` — previously wrote no audit row for this mode. See invocation below. |
| `--re-pair` | Recompute `view_hash` from current `view.yaml` and `prose_body_hash` from current `prose.md` body. Commits the updated `prose.md` frontmatter (`paired_yaml_hash` AND `prose_body_hash`) plus an audit row via `view_commit --mode re-pair` — previously wrote no audit row for this mode. Use this after a manual prose edit (body or YAML) when the edit was intentional; the command re-anchors both hashes in one step. Note that re-pair intentionally blesses whatever is currently on disk — run only after you have reviewed the edit. See invocation below. |
| `--edit` | Open `view.yaml` in `$EDITOR` (default: `vi`). On save, re-run Steps 3-4 (confirmation gate + write) using the edited content as the draft. |
| `--export <view_id>` | Call `audit_export.create_bundle()` to package view + narrative + provenance + full hash-chained audit trail into a tarball. Fails if audit chain is broken. |
| `--why <tilt-path>` | On-demand provenance query. Takes a dotted path (e.g., `tilts.factors.momentum`, `tilts.sectors.information_technology`, `tilts.macro_regime.growth`). JIT-load `references/why-provenance.md` for path parsing rules, derivation resolution order, and per-source output formats. |
| `--version-history` | Read `audit.jsonl`, filter `action="save"` entries in the current view family, and render a compact chain: `version_id → version_id` with the `version_diff` payload rendered as a short bullet list. If any save has `version_diff_truncated: true`, note that. Use this to audit how the view evolved. |

#### Commit invocations for `--extend`, `--re-pair`, `--clear`

Same contract as Step 4 Stage 2: use the staging directory `$HOME/.parallax/.staging`, created with `mkdir -p "$staging" && chmod 700 "$staging"` (the `0700` mode is what protects source-extracted content outside the view directory, and a fixed path under `$HOME` avoids `/tmp`'s world-writable exposure), write every file to be committed **and the plan JSON itself** into it with the Write tool — never a shell heredoc — feed the plan via `< "$staging/plan.json"`, name that directory in `--staging-dir` (path refs are read only from there — see Stage 2), then remove it unconditionally and `exit "$status"` so the commit's exit code is what the block reports. Plan `path` values are literal absolute paths (no `~`, no variables). Omit `--dir` so `$PARALLAX_HOUSE_VIEW_DIR` (default `~/.parallax/active-house-view/`) resolves the target, `view_commit` sets `audit_entry.action` from `--mode` itself, exit 0 prints the committed row, exit 2 means refused and nothing was written, exit 1 is anything else (including the rare artifacts-committed-row-not-appended case, which names its own recovery). `audit.jsonl` stays append-only throughout — see the Stage 2 rule above.

`--extend` (writes `view.yaml` + `prose.md`; `view_hash` is required in `audit_entry` because `view.yaml` is in the write set). Create the staging directory, write both files and `plan.json` into it with the Write tool, then commit:

```bash
staging="$HOME/.parallax/.staging"
mkdir -p "$staging" && chmod 700 "$staging"
# write view.yaml, prose.md, and plan.json into "$staging" via the Write tool, then:
cd <repo>/skills/_parallax/house-view && python3 -m view_commit --mode extend --staging-dir "$staging" < "$staging/plan.json"
status=$?
rm -rf "$staging"
exit "$status"
```

`plan.json` (`<home>` is the literal expansion of `$HOME`):

```json
{"write": {"view.yaml": {"path": "<home>/.parallax/.staging/view.yaml"},
           "prose.md": {"path": "<home>/.parallax/.staging/prose.md"}},
 "audit_entry": {"schema_version": 1, "ts": "...", "view_id": "...", "version_id": "<new-version-id>",
                 "view_hash": "...", "skill": "parallax-load-house-view", "applied": true},
 "expected_identity": {"version_id": "<the version_id read before this call>"}}
```

`--re-pair` (writes `prose.md` only — `view.yaml` is untouched). Create the staging directory, write the file and `plan.json` into it with the Write tool, then commit:

```bash
staging="$HOME/.parallax/.staging"
mkdir -p "$staging" && chmod 700 "$staging"
# write prose.md and plan.json into "$staging" via the Write tool, then:
cd <repo>/skills/_parallax/house-view && python3 -m view_commit --mode re-pair --staging-dir "$staging" < "$staging/plan.json"
status=$?
rm -rf "$staging"
exit "$status"
```

`plan.json` (`<home>` is the literal expansion of `$HOME`):

```json
{"write": {"prose.md": {"path": "<home>/.parallax/.staging/prose.md"}},
 "audit_entry": {"schema_version": 1, "ts": "...", "view_id": "...", "version_id": "...",
                 "view_hash": "...", "skill": "parallax-load-house-view", "applied": true},
 "expected_identity": {"view_hash": "<the view_hash read before this call>",
                       "prose_body_hash": "<the prose_body_hash read before this call>"}}
```

`--clear` — **archive first, then commit.** `view_commit --mode clear` deletes; it does not archive. The row's `destination` field asserts where the view was moved, so writing a row without having moved it puts a false statement into a 7-year compliance record and leaves the operator with nothing to recover.

1. Read `metadata.view_id` and `metadata.version_id` from the current `view.yaml`.
2. Resolve the view directory exactly as the command below does — `$PARALLAX_HOUSE_VIEW_DIR` if set, else `~/.parallax/active-house-view/` — and copy `view.yaml`, `prose.md`, and `provenance.yaml` (each one that exists) into `<view_dir>/.archive/<view_id>-<version_id>/`, creating the directory `0700`. Do not hardcode the default path: the command omits `--dir` and clears whichever directory that variable resolves to, so archiving out of a different one would again make `destination` name a location that does not hold what was deleted. Use the Read + Write tools, or `cp`; this is a copy, not a move — `view_commit` does the removal.
3. Verify that every artifact **that existed** in step 2 landed in the archive — a legacy view carrying no `provenance.yaml` archives two files, not three, and that is not a failure. **If any artifact that did exist failed to copy, stop — do not run the clear.** Report the failure and leave the active view in place; an unrecoverable clear is worse than a clear that did not happen.
4. Only then run the command below, passing that same directory as `destination`. Its write set is empty, so it takes no `--staging-dir` — nothing is read from disk.

```bash
cd <repo>/skills/_parallax/house-view && python3 -m view_commit --mode clear <<'PLAN'
{"write": {},
 "audit_entry": {"schema_version": 1, "ts": "...", "view_id": "...", "version_id": "<current version_id>",
                 "skill": "parallax-load-house-view", "applied": true,
                 "destination": "<the .archive/<view_id>-<version_id>/ path written in step 2>",
                 "reason": "operator cleared"},
 "expected_identity": {"version_id": "<the version_id read before this call>"}}
PLAN
```

### Status block (output of `--status`)

The first line is the `view_status` helper's `banner` field, surfaced verbatim. The block below follows on the next lines. The helper emits one of seven states (`none`, `malformed`, `not_yet_effective`, `expired`, `critical`, `warning`, `active`) — see `_parallax/house-view/view_status.py` and loader.md §2 for the full taxonomy and wording. Do not paraphrase the banner.

```
<view_status.banner>

Active house view
─────────────────
Name:           <view_name>
Uploader:       <uploaded_by> (<uploader_role>)
Effective:      <effective_date> through <valid_through>   [<days_remaining> days remaining]
Calibration:    <heuristic_phase0 | empirical_phase1>
Schema:         v<schema_version>

Tilts active:   <count of non-zero tilts>
  factors:      <pretty list>
  sectors:      <pretty list>
  regions:      <pretty list>
  themes:       <pretty list>

Excludes:       <count>
  <ticker / sector / theme>  — <reason>
  ...

Audit chain:    <ok | broken (offset N)>
Last consume:   <timestamp> by <skill>
Version chain:  <N versions; latest version_id <truncated>>
```

The leading `<view_status.banner>` line covers all non-active states (expired, critical/warning countdowns, not-yet-effective, malformed, none). Do not hand-craft a prefix line — the helper owns the wording, including the days-remaining count and the refresh / `--extend` / `--clear` guidance.

## Output Format

See Step 5 for the post-save summary. See §"Status block" above for `--status`. For other operational modes, output the requested success/failure message.

**§9.2 exemption:** This skill is listed in `_NINE_TWO_EXEMPT_SKILLS` (`_parallax/white-label/tests/test_integration_pattern_referenced.py`) and does not render the §9.2 banner itself — it emits a `view.yaml` configuration artifact, and any LLM-extracted content is gated by Step 3's operator confirmation before it can flow downstream. Each downstream consumer skill renders §9.2 in its own output when it loads the saved view (see `parallax-conventions.md` §9.2 exemption rationale).

> *Local-filesystem implementation. A managed, org-keyed version (`set_house_view`, `get_active_house_view`, etc., backed by Supabase) is on the roadmap; schema and loader semantics carry forward unchanged.*
