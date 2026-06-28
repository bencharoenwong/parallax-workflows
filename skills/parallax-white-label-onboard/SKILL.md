---
name: parallax-white-label-onboard
description: "Configure white-label client branding for Parallax report output. Extracts colors, logos, fonts AND writing voice from a folder of client collateral (PowerPoint, Word docs), a website URL, a PDF brand guide, or guided wizard intake. Multi-source ingestion supported: when more than one source is provided, mismatches between sources are flagged at the confirmation gate rather than silently resolved. Validates visual assets against WCAG accessibility standards and voice section against corpus-size and completeness thresholds, presents a confirmation gate, then saves branding to ~/.parallax/client-branding/ where downstream skills inject it: visual goes into client-review, due-diligence, and deep-dive PDFs; voice goes into letter-writing, newsletter, and meeting-prep skills. Use to onboard a new client brand, update an existing one, or audit what branding is currently active."
---

# White-Label Client Onboarding

## When not to use

- Generating a client report → use /parallax-client-review (it loads the saved branding automatically)
- One-off color/font question → answer inline, don't save as config
- Portfolio construction → use /parallax-portfolio-builder
- Single-prompt voice rewrite of one piece of content → use /humanizer or /chicago-global-voice; this skill is for persistent client brand state

## Gotchas

- JIT-load _parallax/white-label/schema.yaml before extraction — it is the single source of truth for config.yaml shape
- JIT-load _parallax/white-label/extract.py and _parallax/white-label/validator.py before running Steps 1 and 2
- URL input — use defuddle (Bash: `defuddle parse <url> --md`) if available, else WebFetch; do NOT defuddle PDFs
- PDF input — use the Read tool with `pages` parameter; read up to first 10 pages unless the brand guide is clearly deeper
- PPTX input — extract.extract_from_pptx() reads OOXML theme XML directly (precise colors/fonts) and aggregates slide text for voice corpus. Requires python-pptx
- DOCX input — extract.extract_from_docx() same pattern via word/theme/theme1.xml. Requires python-docx
- Folder input — when given a directory, run all .pptx/.docx/.pdf files inside it through their respective extractors and merge_drafts() the result before validation
- Voice extraction is LLM-driven (NOT regex) — extract.py only assembles the corpus. SKILL.md Step 1.5 prompts the model to fill the voice schema using the Lago 7-section template
- Voice corpus must be ≥500 words for credible extraction; ≥2000 words is recommended. VoiceValidator.validate_corpus_size enforces this with warn/fail. Below the floor, refuse to populate voice or surface a hard warning
- Wizard mode is triggered by invoking with no argument — guide intake via AskUserQuestion, one prompt per group
- Confirmation gate is REQUIRED — config must not be written until the user explicitly confirms
- Validation warnings (warn/fail) never block the save — surface them and let the user decide
- Logo download: always download to assets/ during save so downstream PDF generation has local files; external URLs in config are a fallback reference only
- Audit entries must be written even for aborted sessions (extraction_attempt with disposition=rejected)
- If config.yaml exists and is corrupted or fails yaml.safe_load, warn and offer to overwrite; do not crash
- Pre-edit snapshot: when user chooses "Edit specific fields," serialize the pre-edit draft to .archive/ before applying edits — mirrors load-house-view Layer 2 pattern
- config.yaml permissions: 0600. assets/ directory: 0700. Parent directory ~/.parallax/client-branding/: 0700 on creation.
- Cross-validate extracted company name vs. source — extractor may misidentify which brand it found
- File paths in schema.yaml use tilde notation (~/.parallax/...); expand to absolute path at runtime

Configure client branding for Parallax equity research report output.

## Usage

```
/parallax-white-label-onboard                              # wizard mode — guided intake via prompts
/parallax-white-label-onboard <https://client.com>         # auto-extract from website
/parallax-white-label-onboard <path/to/brand-guide.pdf>    # extract from PDF brand guide
/parallax-white-label-onboard <path/to/newsletter.pptx>    # extract from PowerPoint (visual + voice)
/parallax-white-label-onboard <path/to/letter.docx>        # extract from Word (visual + voice)
/parallax-white-label-onboard <path/to/client-collateral/> # extract from folder of mixed PPTX/DOCX/PDF
/parallax-white-label-onboard <url> <path/to/folder>       # multi-source: cross-validate URL vs documents
/parallax-white-label-onboard --status                     # show active branding summary
/parallax-white-label-onboard --clear                      # remove active branding (requires confirmation)
```

**Multi-source priority.** When more than one source is supplied, visual fields with mismatches are surfaced at the confirmation gate (never auto-merged). Voice corpus is concatenated across all sources before voice extraction. The merged draft's `source.type` becomes `"multi"` with all components listed in `source.components`.

## Where branding lives

`~/.parallax/client-branding/`
- `config.yaml` — canonical config per `_parallax/white-label/schema.yaml`
- `DESIGN.md` — Google Labs DESIGN.md companion file emitted from the same draft (frontmatter tokens + 8-section markdown rationale); consumed by frontend coding-agent skills that want a recognized spec
- `assets/` — downloaded logo files (logo-primary.png, favicon.ico, etc.)
- `audit.jsonl` — append-only hash-chained log
- `.archive/<timestamp>-<source>/` — superseded configs kept for traceability

Files are written `0600`; `assets/` is `0700`; the directory is `0700` on creation.

## Optional prerequisites

The DESIGN.md emit path is in-process and pure Python. The optional **DESIGN.md linter** wraps `npx @google/design.md` (Google Labs CLI, published to npm). When Node 18+ is on PATH, the validator runs the linter at save time and surfaces findings in the confirmation gate. When Node is absent, the validator returns `status: "skipped"` and the save proceeds — nothing breaks; the operator just doesn't get inline lint feedback.

If you want the inline lint feedback, install Node 18+ (e.g., `brew install node@20`) and run `/parallax-white-label-onboard <source>` once to warm the npm cache. To pin the version for reproducibility, run `npm install -g @google/design.md@<version>` before invoking the skill. The validator passes `-y` so first-call invocation does not block on the npm install prompt; this also means npx will silently fetch whatever the registry resolves for `@google/design.md` on a clean machine — pin the version in regulated environments.

## Integration with Downstream Skills

Two consumer classes: **visual** (PDF/report skills, read colors/logos/fonts) and **voice** (letter/newsletter/writing skills, read `voice.*`). Both fall back silently to defaults if config is absent.

Visual consumers call `loader.load_visual_branding()` (6-key visual subset). Voice consumers call `loader.load_client_branding()` (full 13-key shape including voice + v2 token tree).

Currently integrated: **Tier 1** (`/parallax-cio-letter-prep`, `/parallax-client-review`, `/parallax-due-diligence`, `/parallax-deep-dive`) and **Tier 2** (`/parallax-should-i-buy`, `/parallax-thematic-screen`, `/parallax-portfolio-checkup`, `/parallax-portfolio-builder`, `/parallax-rebalance`, `/parallax-morning-brief`, `/parallax-explain-portfolio`, `/parallax-scenario-analysis`, `/parallax-country-deep-dive`, `/parallax-pair-finder`, `/parallax-peer-comparison`, `/parallax-macro-outlook`). New visual consumers must JIT-load `_parallax/white-label/integration-pattern.md` via the `<!-- white-label: integration-pattern.md -->` sentinel; the drift gate at `tests/test_integration_pattern_referenced.py` enforces sentinel ↔ load-directive pairing.

> Full loader API + visual/voice loading patterns + voice prompt-prepend template: see `references/integration-contract.md`.

## Workflow

JIT-load `_parallax/white-label/schema.yaml`, `_parallax/white-label/extract.py`, and `_parallax/white-label/validator.py` before executing any step below.

```python
from skills._parallax.white_label.extract import (
    ColorExtractor, LogoExtractor, FontExtractor,
    extract_from_url, extract_from_pdf, extract_from_wizard
)
from skills._parallax.white_label.validator import (
    ColorValidator, LogoValidator, FontValidator
)
```

### Step 0 — Detect input mode

Examine each invocation argument (the skill accepts one or more):

| Condition | Mode |
|---|---|
| No argument | **Entry menu** (see below) |
| Argument starts with `http://` or `https://` | URL extraction |
| Argument is a file path ending in `.pdf` | PDF extraction |
| Argument is a file path ending in `.pptx` | PPTX extraction |
| Argument is a file path ending in `.docx` | DOCX extraction |
| Argument is an existing directory | Folder extraction (run all `.pptx`/`.docx`/`.pdf` inside) |
| Argument is `--status` | Show status block |
| Argument is `--clear` | Clear branding |
| Argument is `--regenerate-design-md` | Regenerate `DESIGN.md` from current `config.yaml` (no extraction; see Operational Modes) |

**Multi-source.** If two or more arguments resolve to extraction modes (any combination of URL, PDF, PPTX, DOCX, folder), run each through its respective extractor and call `extract.merge_drafts(drafts)` + `extract.cross_validate_visual(drafts)` before the validation step. Mismatches are stored in the draft for surfacing at Step 3.

For `--status` and `--clear`, jump directly to the Operational Modes section. For all extraction modes (single or multi-source), proceed to Step 1.

If an argument does not match any row above (e.g., a plain ticker, a relative path with no extension, a file that does not exist), stop and ask: "I couldn't identify the input type for `<arg>`. Please provide a URL, a `.pdf`/`.pptx`/`.docx` path, a folder path, or run without arguments for the entry menu."

**Entry menu (no-argument invocation).** Do NOT jump straight into the manual color-hex wizard. The operator may not know that PPTX/DOCX or folder ingestion exists. First show the routing menu via `AskUserQuestion`:

> How do you want to onboard this client's brand?
>
> - **Point me at their website** — I'll extract colors, fonts, logo, and writing voice from the homepage. Best when their site is the primary brand reference. *Recommended starting point.*
> - **Point me at a folder of their materials** — drop their newsletters / letters / decks (`.pptx`, `.docx`, `.pdf`) in a folder; I'll extract everything from the OOXML theme XML and aggregate the body text for voice analysis. Best for voice fidelity.
> - **Both — website AND folder** — I'll cross-validate visual fields between sources, flag mismatches for you to resolve, and combine the corpora for stronger voice extraction. *Best when both are available.*
> - **Manual wizard** — I'll prompt you for each value (colors, fonts, logo URL). Use only if you have no website and no document samples.

After the operator picks, ask the follow-up:

| Choice | Follow-up question |
|---|---|
| Website | "What's the URL?" — accept and re-route through Step 0 with the URL as argument. |
| Folder | "What's the folder path? (Absolute path; should contain `.pptx`, `.docx`, or `.pdf` files.)" — re-route through Step 0. |
| Both | Two questions: URL, then folder path. Re-route through Step 0 with both arguments. |
| Manual wizard | Proceed directly to Step 1 wizard mode. |

### Step 1 — Extract brand assets

**Wizard mode:**

Use one `AskUserQuestion` per numbered group below. Do not ask all fields in a single wall of text — group them logically. Confidence for all wizard-supplied values is 1.0 (the user is the source).

1. **Identity:** Client display name, contact name/email (optional, for audit log).
2. **Colors:** Primary brand color (hex), secondary color (hex), accent color (hex). For each, if the user provides a name like "navy blue" rather than a hex code, ask for the hex code explicitly or offer to pick a nearest standard hex.
3. **Background and text defaults:** Background color (hex, default `#FFFFFF`), default text color (hex, default `#333333`).
4. **Logos:** Primary logo (URL or local file path), favicon (URL or local file path, optional).
5. **Fonts:** Header font name, body font name, monospace font name (optional, default `Courier New`).

Assemble the `draft` dict from wizard answers. Skip any field the user leaves blank and flag it as missing with confidence 0.0.

**URL mode:** `draft = extract_from_url(url)`. If `draft` contains `"error"`, surface it: `"Extraction returned partial results due to: <error>. Review and edit before confirming."`

**PDF mode:** `draft = extract_from_pdf(pdf_path)`. Reads up to 5 pages by default. If the brand guide appears to be a dedicated multi-page document and extraction confidence is low (<0.6 average), offer to read more pages or switch to wizard mode.

**PPTX mode:** `draft = extract_from_pptx(pptx_path)`. Reads `ppt/theme/theme1.xml` directly, so colors and fonts come from the canonical OOXML theme declarations (confidence 0.9). Body text from every text frame is aggregated into `draft["voice_corpus"]` for the voice extraction step. The OOXML slot mapping is fixed: `accent1`→primary, `accent2`→secondary, `accent3`→accent, `dk1`→text, `lt1`→background. If the deck uses a heavily customized theme that overrides these slots inline, theme XML may understate the actual on-slide colors — flag this and offer wizard override.

**DOCX mode:** `draft = extract_from_docx(docx_path)`. Identical pattern via `word/theme/theme1.xml`. Body text from all paragraphs (skipping headers/footers) aggregated into `draft["voice_corpus"]`. Word's defaults are commonly Calibri (header) + Cambria (body); if the document inherits defaults rather than declaring custom fonts, the extracted values reflect the default theme — note this in `notes`.

**Folder mode.** Folder mode is NOT a blind iteration — it inventories, classifies by role (branded marketing / internal memo / compliance / transcript / ambiguous), confirms the classification with the operator, then extracts per classification. Decision points: ambiguous files are surfaced one-per-`AskUserQuestion`; voice-only OOXML keeps voice and discards visual; 2+ branded drafts merge via `merge_drafts + cross_validate_visual`; voice-only folders seed `source.type = "folder-voice-only"`; the corpus is re-truncated at the 3000-word cap.

> Full folder procedure (Steps F-1 inventory → F-2 classification tables → F-3 operator gate → F-4 extract) and the three named voice frameworks (Lago / Rezvani / Genesys) it grounds on: see `references/folder-mode.md`. F-4 Python: `references/workflow-code.md` § Step 1 — Folder extraction.

**Multi-source mode (URL + folder, or any 2+ sources):** iterate `args`, dispatch each to its extractor, call `merge_drafts(drafts) + cross_validate_visual(drafts)` and store mismatches/agreements in `draft["multi_source"]`. Mismatches are NOT auto-resolved here — they surface in the Step 3 confirmation gate.

> Full Python (multi-source dispatch loop) and the full `draft` dict shape: see `references/workflow-code.md` § Step 1 — Multi-source extraction and § Draft structure after extraction.

Missing fields (empty dict values or absent keys) are acceptable — they will surface as warnings at Step 2 and can be filled at Step 3.

### Step 1.5 — Voice extraction (only when corpus is available)

**Skip this step entirely if `draft["voice_corpus"]["word_count"] < 500`.** Below that floor, voice extraction is unreliable; set `draft["voice"] = {"enabled": False}` and continue to Step 2. Surface the gap to the user: `"Voice section not populated — corpus is only <N> words, below the 500-word minimum. Add more sample documents to enable voice extraction."`

**When corpus is sufficient,** drive voice extraction via in-skill prompting (no Python — this is LLM-native work). Read the corpus from `draft["voice_corpus"]["text"]`, prompt yourself with the Lago 7-section + Rezvani tone-matrix template, then write the resulting fields into `draft["voice"]`.

After extraction, set `draft["voice"]["enabled"] = True`, `draft["voice"]["source_corpus"]["word_count"] = N`, `draft["voice"]["source_corpus"]["documents"] = [list of source references]`, and `draft["voice"]["source_corpus"]["confidence"] = your_self_assessed_confidence_0_to_1`. Leave `drafted_vs_sent: []` — it is not auto-extractable (requires draft↔human-edited comparison) and is populated incrementally by downstream skills; note that in `voice.source_corpus.notes`.

> Full voice prompt template, the 3-item anti-boilerplate self-check, and the drafted-vs-sent rationale: see `references/voice-extraction.md`.

### Step 1.75 — Completeness audit & supplement offer

Before validation, audit the draft for thinness and proactively offer to supplement. The operator may have given just a URL not realizing that adding a sample folder dramatically improves voice extraction; saving a thin config without surfacing the gap is a UX failure.

Audit checks: count brand colors, count fonts, check voice corpus word count, voice enabled flag, logo presence. Each thinness condition (colors_thin / fonts_missing / logo_missing / voice_corpus_thin / voice_corpus_low / voice_disabled_unexpectedly) appends a tuple to the `audit` list with a human-readable description.

> Full Python (audit checks): see `references/workflow-code.md` § Step 1.75 — Completeness audit.

**If any audit item fires AND the operator is in single-source mode**, surface them clearly via `AskUserQuestion` BEFORE the confirmation gate:

> The extraction is thin in these areas:
>   - <list of audit items, one per line, with the human-readable description>
>
> Do you want to supplement before saving?
>
> - **Add a folder of sample materials** — point me at a folder with their newsletters / letters / decks. I'll re-extract and merge. *Recommended if voice corpus is thin or fonts are missing.*
> - **Add their website URL** — only useful if you started with a folder. *Recommended if you want a sanity-check cross-source.*
> - **Fill the gaps manually in wizard mode** — I'll prompt you for the missing fields only.
> - **Save what I have** — I'll save the partial config; downstream consumers fall back to defaults for missing fields. The audit notes go into `metadata.notes`.

**If the operator chooses to supplement,** loop back to Step 0 with the additional source(s) and run multi-source extraction. If they choose "save what I have," append the audit list to `draft["metadata"]["notes"]` so the gap is durable in the saved config and the operator can re-run with more sources later.

**If the operator is already in multi-source mode** (e.g., URL + folder), skip the supplement offer — they've already given the skill its best shot. Surface the audit items in the confirmation-gate "MISSING FIELDS" block instead, so they're visible but don't block.

### Step 2 — Validate assets

Run all validators in parallel (no inter-dependency). Collect results into a `validation_results` dict. Validators:

- **Color contrast (WCAG AA)** — `ColorValidator.validate_text_contrast(text_hex, bg_hex)` → `{"status": "pass"|"warn"|"fail", "ratio": float, "recommendation": str|None}`
- **Individual hex format** — `ColorValidator.is_valid_hex(hex_val)` per color slot
- **Logo dimensions/format** — `LogoValidator.validate_logo(path)` for local logos only; URLs marked `"pending"` until Step 4 download
- **Font availability** — `FontValidator.validate_font(font_name)` per font slot
- **Voice section** — `VoiceValidator.validate_voice(draft.get("voice", {"enabled": False}))` → `{"status": "pass"|"warn"|"fail"|"skipped", "checks": {...}}`. `status: "skipped"` is the default when voice extraction was bypassed (visual-only sources) — informational, never an error. Do NOT block the save on a skipped voice section.

> Full code per validator: see `references/workflow-code.md` § Step 2 — Per-validator code blocks.

**Validation rules:**
- `fail` on: invalid hex format, logo file >5MB, logo format unsupported
- `warn` on: WCAG contrast 3.0–4.49, logo dimensions <200×200, font not on system
- `pass` on: all checks clear

Validation warnings and failures are informational only. They never block the save. Surface them clearly at Step 3 so the user can make an informed choice.

**Assemble validation summary table:**

```
Asset              Check                   Status    Note
─────────────────────────────────────────────────────────────────────
colors.primary     hex format              pass
colors.secondary   hex format              pass
colors.text+bg     WCAG AA contrast        warn      4.1:1 — large text only
logos.primary      (URL — validate post-download)
fonts.header       system availability     warn      "Montserrat" not found; fallback: Helvetica
fonts.body         system availability     pass
fonts.monospace    system availability     pass
```

Compute `avg_conf` and `lowest_field` from `draft["confidence_scores"]` for the Step 3 summary header.

### Step 3 — Confirmation gate (REQUIRED before save)

**The gate is mandatory: config must NOT be written until the user explicitly confirms.** Render the draft display block (colors / logos / fonts / voice / multi-source mismatches / validation summary / DESIGN.md frontmatter preview + lint / missing fields), then ask via `AskUserQuestion`:

> Confirm this branding configuration?
> - **Confirm and save** (Recommended if extraction looks right)
> - **Edit specific fields** — you'll be prompted for which fields to change
> - **Re-extract from different source** — provide a different URL or PDF path
> - **Abort** — abandon this session, no save

Decision points to preserve:
- **DESIGN.md preview + lint are informational** — generated via `emit_design_md(...)` (split on `---`, indent YAML) and `DesignMdValidator.lint(...)`; they never auto-block the save.
- **Mismatch resolution (multi-source):** if mismatches are present, the user MUST pick a winner per field via `AskUserQuestion` (candidate values shown with source attribution). Apply the choice to `draft` before save. Do NOT auto-pick by confidence or recency — the PM/CIO is canonical on which brand version is current.
- **Edit / Re-extract / Abort** each have their own disposition and audit handling: `edited` archives the pre-edit draft and hashes the pre-edit draft; `re_extracted` returns to Step 0; `rejected` writes no files; `confirmed` proceeds to Step 4.

> Full draft display template, color-swatch fallback, and the per-option procedures (Edit-fields 7-step / Re-extract / Abort / Confirm): see `references/confirmation-gate.md`.

### Step 4 — Save

#### 4a. Pre-write validation

Before any I/O:
- Verify `~/.parallax/client-branding/` is writable (create it with `os.makedirs(..., mode=0o700, exist_ok=True)` if absent).
- Verify the draft contains at minimum: one color (`branding.colors.primary`), or one logo, or one font. An entirely empty config is a user error — ask to confirm or abort.
- Validate all hex colors one final time via `ColorValidator.is_valid_hex()`. Reject any that fail (they should have been caught at Step 2, but this is a hard gate).

#### 4b. Download logos to local assets/

For each logo with a URL (not already a local path), download to `~/.parallax/client-branding/assets/` as `logo-primary.<ext>` / `favicon.<ext>`, then set `draft["logos"]["<role>"]["local_path"]`. On download failure: warn and preserve URL only. After successful downloads, re-run `LogoValidator.validate_logo(dest)` and append to the validation summary.

> Full code: see `references/workflow-code.md` § Step 4b — Download logos to local assets/.

#### 4c. Construct config.yaml

**Use `build_config_from_draft(draft, schema_version=2)` from `loader.py` — do not hand-assemble the config dict.** The builder is the single source of truth for the v2 shape (decisions 3A, 5A: drops `fonts.*`, emits `colors.tertiary` and flat `colors.neutral`, wires `components.body-text`). It also handles the `voice` section and the `multi_source` provenance block — no post-build mutation needed.

v2 emits: `metadata`, `branding.{colors[primary|secondary|tertiary|neutral], logos, typography[h1..h5|body-md|code], rounded, spacing, components.body-text}`, `validation_summary`, `confidence_scores`. `fonts.*` is NOT in v2 — the loader bridges v1↔v2 at read time so consumers always see `fonts.{header,body,monospace}` derived from `typography.{h1,body-md,code}.fontFamily`.

Compute `config_hash = sha256(yaml.safe_dump(config["branding"], sort_keys=True).encode()).hexdigest()`.

> Full code (builder call + v2 yaml shape + v1 legacy fallback): see `references/workflow-code.md` § Step 4c — Construct config.yaml.

#### 4d. Archive existing config (if present)

Copy any existing `config.yaml` to `~/.parallax/client-branding/.archive/<YYYYMMDDTHHMMSSZ>/config.yaml` before overwriting. Archive failures are non-blocking — log and continue.

> Full code: see `references/workflow-code.md` § Step 4d — Archive existing config.

#### 4e. Write files (atomic-swap pattern)

Write `config.yaml` to a staging directory, then `shutil.move` to the live path. Enforce `0600` on config.yaml and `0700` on assets/. On write failure: report cleanly and DO NOT proceed to Step 4e' or Step 4f — the previous active config remains unchanged.

> Full code: see `references/workflow-code.md` § Step 4e — Staging write + atomic-swap.

#### 4e'. Write DESIGN.md (Google Labs spec)

Emit `DESIGN.md` from the draft via `emit_design_md(draft, client_name=..., extracted_at=..., source_refs=[...])`, write to staging, atomic-move to `~/.parallax/client-branding/DESIGN.md`, chmod `0600`. Compute `design_md_hash` (sha256) for the audit entry. `emit_design_md` raises `ValueError` on invalid hex tokens — treat as write failure, do not proceed to Step 4f.

> Full code: see `references/workflow-code.md` § Step 4e' — Write DESIGN.md.

#### 4f. Append hash-chained audit entry

**Audit-entry schema bump (intentional chain discontinuity).** With the DESIGN.md emit at Step 4e', save entries now include `design_md_hash` and `lint_status`. The chain hash is `sha256(prior-line-bytes)`, so the first new-shape entry after a v1 audit log will appear as a chain break to any downstream verifier comparing entry shape across the bump. This is intentional: keep the prior chain readable for forensics but treat entries before this point as belonging to the v1 audit schema. If a verifier exists, gate it on `entry.get("design_md_hash") is not None` to detect schema-2 entries; absent that field, treat the entry as v1.

Read the last line of `audit.jsonl`, sha256 it to get `prev_entry_hash`, then append a new entry with `action: "save"`, `applied: true`, the config_hash, client_name, validation_status, disposition, draft_yaml_hash, design_md_hash, and lint_status. Chmod `audit.jsonl` to `0600`.

**Every extraction attempt that does not result in a save also appends an audit entry** (`action: "extraction_attempt"`, `applied: false`) with `disposition`: `confirmed` / `edited` / `re_extracted` / `rejected`. This includes aborted sessions.

> Full code: see `references/workflow-code.md` § Step 4f — Append hash-chained audit entry.

### Step 5 — Confirmation summary

Output:

```
Branding saved.
  client:      <client_name>
  source:      <type>: <reference>  (or "multi: N sources" when multi-source)
  colors:      <count of non-empty color slots> configured
  logos:       <count> downloaded to assets/
  fonts:       <count of non-empty font slots> configured
  voice:       <enabled: yes|no — corpus N words from M docs, register: ...>
  warnings:    <count of warn/fail checks> (see validation above)

Active in:
  visual:  client-review, due-diligence, deep-dive
  voice:   any skill that calls cfg["voice"] when enabled
Fallback: if branding load fails, downstream skills use default Parallax styling/voice.

Audit & inspect:
  /parallax-white-label-onboard --status    # active branding summary
  /parallax-white-label-onboard --clear     # remove branding

Try it:
  /parallax-client-review <ticker>          # generates a branded client report
```

---

## Operational Modes

| Flag | Behavior |
|---|---|
| `--status` | Read `config.yaml`, render status block. If no config: print "No active client branding configured." |
| `--clear` | Ask for explicit confirmation ("Type YES to remove client branding"). On confirm: archive `config.yaml`, `DESIGN.md`, and `assets/` to `.archive/<timestamp>-clear/`, remove live files. Append `{"action":"clear"}` audit entry. |
| `--regenerate-design-md` | Re-emit `DESIGN.md` from the current `config.yaml` without re-extracting from source. See section below. |

> Status block output template: see `references/status-format.md`.

If `config.yaml` fails to load (YAML parse error, missing required keys), the `--status` mode shows: `"! Config corrupted or outdated. Re-run /parallax-white-label-onboard to reconfigure."`

### Regenerate-from-config mode (`--regenerate-design-md`)

Purpose: keep `DESIGN.md` in sync with `config.yaml` after manual edits, without re-running source extraction. Single source of truth: `config.yaml` is canonical; `DESIGN.md` is derived.

**What `--regenerate-design-md` preserves and recomputes:**
- **Preserved from config.yaml:** all color tokens, typography/font declarations, rounded/spacing values, logos, voice section (if present), `extracted_at` timestamp, source provenance, `multi_source` block.
- **Recomputed:** DESIGN.md frontmatter YAML and 8-section markdown body. The `design_md_hash` in the audit chain is updated to reflect the new output.
- **Not archived:** the prior `DESIGN.md` is overwritten without an `.archive/` snapshot. If you need to retain the old file, copy it manually before running this flag.
- **v1 config behavior:** `fonts.header`/`fonts.body`/`fonts.monospace` are used as fallbacks for `typography.h1`/`body-md`/`code` slots (confidence 0.5). No `typography.*` block is required in the config.

Implementation: load `config.yaml`, validate required keys (`branding.colors.primary` AND either `branding.typography.h1` OR `branding.fonts.header`), call `_config_to_draft(cfg)` from `loader.py` to reconstruct a synthetic draft, call `emit_design_md`, atomic-write to `DESIGN.md`, append `action: "regenerate_design_md"` audit entry.

> Full Python (validation + draft reconstruction + atomic write + audit entry): see `references/workflow-code.md` § Regenerate-from-config — Python block.

Hard errors (printed + return, no partial emit):
- `config.yaml` not present → "No active branding to regenerate from. Run /parallax-white-label-onboard first."
- `config.yaml` present but missing `branding.colors.primary` or both typography & fonts → "Cannot regenerate — config.yaml missing required keys: ...". Do not write a partial `DESIGN.md`.

Behavior on a v1 config (no `typography.*` block): emitter takes `fonts.header` / `fonts.body` / `fonts.monospace` as the `typography.h1.fontFamily` / `body-md.fontFamily` / `code.fontFamily` defaults (with confidence-neutral 0.5).

---

## Error Handling, Edge Cases & Success Criteria

Edge-case handling (corrupted config, logo-download failure, empty color extraction, font-not-on-system, WCAG fail, unwritable directory, mid-way staging failure, >10-page PDF) and the full Success Criteria checklist (config/assets/audit assertions, voice-extracted vs not, multi-source) are catalogued in `references/edge-cases.md`. Consult it when a failure mode fires or before declaring a run successful.

---

## See also

- `references/workflow-code.md` — full Python for Steps 1–4 + regenerate-from-config
- `references/folder-mode.md` — folder inventory/classification (F-1..F-4) + Lago/Rezvani/Genesys voice frameworks
- `references/voice-extraction.md` — Step 1.5 voice prompt template, self-check, drafted-vs-sent rationale
- `references/confirmation-gate.md` — Step 3 draft display template + Edit/Re-extract/Abort/Confirm procedures
- `references/edge-cases.md` — error handling, edge cases, and Success Criteria checklist
- `references/status-format.md` — `--status` output template
- `references/integration-contract.md` — visual + voice consumer loading patterns, voice prompt-prepend template
- `references/overview.md` — architecture, data flow, test inventory (was top-level `README.md`)
- `references/installation.md` — setup, dependencies, troubleshooting (was top-level `INSTALLATION.md`)
- `references/validation-rules.md` — color/logo/font validation reference
- `references/supported-fonts.md` — web-safe fonts + fallback chains
- `_parallax/white-label/integration-pattern.md` — canonical consumer-side contract for visual rendering (§1–§9)
