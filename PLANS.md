# Align Parallax White-Label Ingest with DESIGN.md (Google Labs spec)

## Purpose

Make the Parallax white-label brand ingestion skill emit a Google Labs `DESIGN.md` file alongside the existing `config.yaml`, widen extractors to fill DESIGN.md slots (typography scale, corner radii, spacing), rename internal vocabulary to match the DESIGN.md spec, and run `npx @google/design.md lint` at save time. Downstream Parallax PDF skills (`/parallax-client-review`, `/parallax-due-diligence`, `/parallax-deep-dive`) must keep working unchanged against either old- or new-shape config files.

Observable outcome: after running `/parallax-white-label-onboard` on a PPTX, the user's `~/.parallax/client-branding/` directory contains both `config.yaml` (existing format) and `DESIGN.md` (Google Labs format with YAML frontmatter + markdown body), the two are consistent, and the existing test suite plus 57 new tests pass.

## Progress

Implementation is staged in three waves; each box must be checked when the work and its tests pass.

**Wave 1 — Parallel (independent files):**
- [ ] L1: New module `skills/_parallax/white-label/emit_design_md.py` — pure deterministic emitter
- [ ] L2: Extend `skills/_parallax/white-label/extract/ooxml.py` — typography scale + corner radii from PPTX/DOCX
- [ ] L3: Extend `skills/_parallax/white-label/extract/web_pdf.py` — CSS type scale + radii + spacing; PDF brand-guide prose with multi-signal gate

**Wave 2 — Serial after Wave 1:**
- [ ] L4: Extend `skills/_parallax/white-label/validator.py` — `DesignMdValidator` running `npx @google/design.md lint`
- [ ] L5: Migrate `skills/_parallax/white-label/loader.py` + `schema.yaml` — schema v2, v1↔v2 bridge, write path drops `fonts.*`

**Wave 3 — Serial after Wave 2:**
- [ ] L6: Extend `skills/_parallax/white-label/extract/merge.py` — token-level cross-validate and merge for typography/rounded/spacing
- [ ] L7: Update `skills/white-label-onboard/SKILL.md` — Step 3 gate shows DESIGN.md frontmatter preview + lint findings; Step 4 writes DESIGN.md atomically; add `--regenerate-design-md` mode

**Tests (in parallel with each lane):**
- [ ] New: `skills/_parallax/white-label/tests/test_emit_design_md.py`
- [ ] New: `skills/_parallax/white-label/tests/test_regression.py` (3 critical regression gates)
- [ ] Extend: `test_doc_extractors.py`, `test_extract.py`, `test_validator.py`, `test_loader.py`, `test_integration.py`, `test_roundtrip_and_url.py`
- [ ] New fixtures: committed `tests/fixtures/brand_guide_sample.pdf` + `tests/fixtures/legacy_v1_config.yaml` + `tests/fixtures/README.md`

## Context and Orientation

**Project root:** `/Users/bencharoenwong/parallax-workflows/.claude/worktrees/white-label-ingest` (a git worktree on branch `worktree-white-label-ingest`).

**What this repo is:** a collection of Claude Code skills for Parallax equity research. Each skill in `skills/` orchestrates Parallax MCP tools via structured workflows. Shared utilities live in `skills/_parallax/`.

**The skill being modified:** `skills/white-label-onboard/` (SKILL.md = orchestration / user-visible flow) + `skills/_parallax/white-label/` (the Python machinery: extractors, validators, loader, schema). The skill onboards a client's brand identity by extracting colors, fonts, logos, and writing voice from PowerPoint decks, Word docs, PDFs, websites, or a folder of mixed materials. It saves the result to `~/.parallax/client-branding/config.yaml` (mode 0600), downloads logo files to `~/.parallax/client-branding/assets/` (mode 0700), and appends a hash-chained entry to `~/.parallax/client-branding/audit.jsonl`. Downstream Parallax skills then read this config when generating client-branded reports.

**Current file layout** (relative to project root):

```
skills/
├── white-label-onboard/
│   ├── SKILL.md              # ~970 lines, orchestrates the user flow
│   ├── README.md
│   └── INSTALLATION.md
└── _parallax/
    └── white-label/
        ├── schema.yaml       # config.yaml schema; source of truth
        ├── loader.py         # downstream consumers import this; returns 9-key shape
        ├── validator.py      # ColorValidator, LogoValidator, FontValidator, VoiceValidator
        ├── extract/
        │   ├── __init__.py
        │   ├── colors.py
        │   ├── merge.py      # merge_drafts + cross_validate_visual
        │   ├── ooxml.py      # PPTX/DOCX theme XML parsers
        │   ├── voice.py
        │   ├── web_pdf.py    # URL + PDF extractors
        │   └── wizard.py
        └── tests/
            ├── conftest.py
            ├── fixtures/
            │   └── voice_extraction_polaris_2026-01.yaml
            ├── test_doc_extractors.py
            ├── test_extract.py
            ├── test_integration.py
            ├── test_loader.py
            ├── test_roundtrip_and_url.py
            └── test_validator.py
```

**Existing patterns to follow:**
- Tests generate PPTX/DOCX programmatically via `python-pptx` / `python-docx` in `tmp_path`; binaries are not committed (exception: one PDF brand-guide sample will be committed for this PR — see Wave 1 L3).
- File writes use atomic staging: write to `.staging/`, then `shutil.move` to live path.
- All files in `~/.parallax/client-branding/` are mode 0600; directories are 0700.
- The hash-chained `audit.jsonl` appends one entry per save (every extraction attempt, including aborts).
- `loader.py` returns a stable 9-key dict shape that PDF-generating skills depend on; this shape MUST NOT change.

**Tech stack:** Python 3.11+. Dependencies include `python-pptx`, `python-docx`, `pyyaml`, `beautifulsoup4`, `pypdf`, `pytest`. Optional new tooling dep: Node 18+ for `npx @google/design.md` (graceful skip if absent).

**Google DESIGN.md spec summary (this is what we're aligning to):**
- File format: YAML frontmatter delimited by `---` fences + markdown body with `## ` h2 sections in fixed order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts.
- Frontmatter tokens: `colors` (primary/secondary/tertiary/neutral, all flat hex strings), `typography` (named levels like `h1`, `body-md`, each with `fontFamily`/`fontSize`/`fontWeight`/`lineHeight`/`letterSpacing`), `rounded` (sm/md/lg/full dimensions), `spacing` (xs/sm/md/lg/xl), `components` (e.g. `button-primary: { backgroundColor, textColor, rounded, padding }`).
- Token references via `{path.to.token}` syntax inside `components`.
- Linter: `npx @google/design.md lint <file> --format json` outputs `{ "findings": [...], "summary": {...} }`. Exit 1 on errors, 0 otherwise.

**8 review-locked decisions for this implementation** (these resolve open questions surfaced in `/plan-eng-review`):

1. **1D — keep `npx` lint as planned.** 20s timeout, skipped on failure. Operators on Node-less machines see one line "skipped" at the gate; save proceeds.
2. **2A — add `--regenerate-design-md` flag.** Lets operators re-emit DESIGN.md from current `config.yaml` without re-extracting. Errors clearly when config is missing or broken.
3. **3A — drop `fonts.*` from v2 write path.** v2 `config.yaml` stores `typography.*` only. The loader derives the legacy `fonts.{header,body,monospace}` keys from `typography.{h1,body-md,code}.fontFamily` for downstream consumers. Single source of truth.
4. **4A — multi-signal gate for brand-guide PDF prose.** `_extract_brand_guide_prose` only extracts when ≥3 of 4 expected section headings present (Overview, Colors, Typography, Do's and Don'ts) AND the filename matches `/(brand|guide|identity|style)/i`. Otherwise returns `{}`.
5. **5A — spec-conformant flat `neutral`.** `colors.neutral` is a single hex string. Text-on-neutral pairing moves to `components.body-text` with `backgroundColor: "{colors.neutral}"` and `textColor: <hex>`. Loader's `background` legacy key derives from `colors.neutral`; `text` derives from `components.body-text.textColor`.
6. **6A — 57 tests + 3 critical regression gates.** Every codepath in the test diagram gets at least ★ coverage; every consumer flow at least ★★.
7. **7A — dedicated `tests/test_regression.py`** for the 3 critical gates: (i) v1 file → loader returns `colors.accent` populated; (ii) v2 file → loader returns `colors.accent = colors.tertiary` value; (iii) `--clear` archives both `config.yaml` AND `DESIGN.md`. Backed by a committed `tests/fixtures/legacy_v1_config.yaml`.
8. **8A — E2E lint canary marked `@pytest.mark.npx`.** Skipped via `pytest.mark.skipif(not DesignMdValidator.is_available())` when Node 18+ is not on PATH.

**Critical gaps (must close):**
- `emit_design_md` must validate every hex token via `ColorValidator.is_valid_hex` and raise `ValueError(f"invalid hex at colors.{role}: {value}")` on failure.
- `--regenerate-design-md` must error clearly on a missing or broken `config.yaml` (no partial emit).

## Plan of Work

The implementation follows the dependency graph in three waves. Within each wave, the listed lanes are independent and may be implemented in any order. Across waves, downstream lanes assume their upstream lanes have landed.

### Wave 1 (Lane L1) — Pure DESIGN.md emitter

Create `skills/_parallax/white-label/emit_design_md.py` exporting a single public function `emit_design_md(draft: dict, *, client_name: str, extracted_at: str, source_refs: list[str]) -> str`. The function is pure and deterministic — no I/O, no `datetime.now()`, no file reads. Given the same input dict, it returns byte-identical strings on every call.

Internally, the function builds two pieces and concatenates them with a `---` fence:

1. `_frontmatter_dict(draft)` — a Python dict assembled in spec-mandated order: `colors` → `typography` → `rounded` → `spacing` → `components`. Within `colors`, the order is `primary`, `secondary`, `tertiary`, `neutral`. Missing tokens are *omitted* (no `spacing: {}` placeholders) so the linter's `orphaned-tokens` rule stays meaningful.

   **Hex validation gate** (critical gap): before assembling the dict, iterate over every hex token in the draft (`draft['colors']['primary']['hex']`, etc.) and call `ColorValidator.is_valid_hex(hex)`. On the first invalid hex, raise `ValueError(f"invalid hex at colors.{role}: {value}")`. Do not partial-emit.

   Mapping table (the canonical source of truth for this PR):

   | Draft path | DESIGN.md frontmatter token | Notes |
   |---|---|---|
   | `draft['colors']['primary']['hex']` | `colors.primary` | direct |
   | `draft['colors']['secondary']['hex']` | `colors.secondary` | direct |
   | `draft['colors']['accent']['hex']` | `colors.tertiary` | RENAME |
   | `draft['colors']['background']['hex']` | `colors.neutral` | **flat hex** (decision 5A) |
   | `draft['colors']['text']['hex']` | `components.body-text.textColor` | **moved to components** (5A) |
   | `draft['typography'][<level>]` | `typography.<level>` | emit each present level as a full Typography object |
   | `draft['fonts']['monospace']['name']` (legacy) | `typography.code.fontFamily` | wrap singleton into Typography object |
   | `draft['rounded'][<size>]` | `rounded.<size>` | direct |
   | `draft['spacing'][<slot>]` | `spacing.<slot>` | direct |

   Additionally, emit a `components.body-text` block when both `colors.neutral` and a text color are known:
   ```yaml
   components:
     body-text:
       backgroundColor: "{colors.neutral}"
       textColor: <draft.colors.text.hex literal>
   ```

2. `_body_sections(draft, client_name, source_refs)` — produces the 8 required h2 sections in fixed order: Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts. Body prose for each section is *templated* (deterministic strings parameterized by `client_name` and the tokens present) by default. When `draft` contains a `brand_guide_prose` dict (populated by Lane L3 from a real brand-guide PDF), the templated text for matching sections is replaced by the extracted prose. Each section's prose contains at least one `{path.to.token}` reference to demonstrate token usage to coding-agent consumers.

Serialize the frontmatter via `yaml.safe_dump(..., sort_keys=False, default_flow_style=False, allow_unicode=True)`. Uppercase hex values (`#FF6600`, not `#ff6600`). Floats serialize without trailing zeros (write `1.5`, not `1.50`).

Tests live in `skills/_parallax/white-label/tests/test_emit_design_md.py`. Cover: minimal valid frontmatter, all 8 sections in order, accent→tertiary rename, components.body-text wiring, omitting missing tokens (no `spacing: {}`), determinism across two calls (byte-equality), invalid-hex raises `ValueError` with the correct path.

### Wave 1 (Lane L2) — OOXML typography scale + corner radii

Extend `skills/_parallax/white-label/extract/ooxml.py` with three new functions:

- `_parse_pptx_master_typography(zf: zipfile.ZipFile) -> dict[str, dict[str, Any]]` reads `ppt/slideMasters/slideMaster1.xml` for `<p:txStyles>` containing `<p:titleStyle>` and `<p:bodyStyle>`. Map: `titleStyle` → `h1`, `bodyStyle lvl1pPr` → `h2`, `lvl2pPr` → `h3`, `lvl3pPr` → `h4`, `lvl4pPr` → `h5`, `lvl5pPr` → `body-md`, `lvl6pPr` → `body-sm`. PPTX `sz` is hundredths of a point; divide by 100 and append `"pt"` (so `sz="4400"` → `"44pt"`). Capture `b="1"` as `fontWeight: 700`, otherwise 400. Read `lnSpc` for `lineHeight`. Default `letterSpacing` to `"0"` when not declared. Levels not present in the master are *omitted* — do not invent `body-xs` or `caption`. Record per-level confidence under `draft['confidence_scores']['typography.<level>']`: 0.85 for sizes, 0.7 for lineHeight, 0.5 for letterSpacing.

- `_parse_docx_style_typography(zf: zipfile.ZipFile) -> dict[str, dict[str, Any]]` reads `word/styles.xml`. Map by `w:styleId` and `w:name`: Heading 1 → h1, Heading 2 → h2, Heading 3 → h3, Heading 4 → h4, Heading 5 → h5, Normal → body-md, No Spacing → body-sm (when present). DOCX `w:sz` is in *half-points*; divide by 2 then append `"pt"`. Same confidence rules as PPTX.

- `_detect_corner_radii_pptx(zf: zipfile.ZipFile) -> dict[str, str]` walks all `ppt/slides/slide*.xml`, finds `<a:prstGeom prst="roundRect">` shapes, reads the `<a:gd name="adj" fmla="val NNNNN"/>` adjust value (0–50000 ≈ 0%–50% of half-dimension). Convert to a px guess assuming a default shape size. Cluster modal radii: `sm` if <8px, `md` if 8–16, `lg` if >16. Return `{}` when no roundRect shapes exist. Confidence 0.5 — geometry in PPTX is rarely a designer's deliberate radius token.

Wire these into the existing `extract_from_pptx` / `extract_from_docx` so the returned draft includes `typography` and `rounded` keys when extraction succeeds.

Tests live in `skills/_parallax/white-label/tests/test_doc_extractors.py`. Generate fixtures programmatically in `tmp_path` using `python-pptx` / `python-docx`. Cover: title size from PPTX master, body-md present, DOCX heading 1 size, missing levels omitted, roundRect radius extracted, no roundRect yields empty rounded, confidence recorded.

### Wave 1 (Lane L3) — URL/CSS extractors + PDF brand-guide prose

Extend `skills/_parallax/white-label/extract/web_pdf.py` with three new classes and one function:

- `TypographyExtractor.extract_type_scale_from_css(css_text: str) -> dict[str, dict[str, Any]]` parses CSS rules for selectors `h1`..`h6`, `body`, `.body-md`, `p`, `code`, `pre`. For each found rule, capture `font-size`, `font-weight`, `line-height`, `letter-spacing`. Map selectors to DESIGN.md levels: `h1`..`h5` → `h1`..`h5`, `body` or `p` → `body-md`, `code`/`pre` → `code`. Missing fields default to `font-weight: 400`, `line-height: 1.5`, `letter-spacing: "0"`. Confidence 0.80.

- `ShapeExtractor.extract_border_radii(css_text: str) -> dict[str, str]` collects all `border-radius` declarations, drops percentages (except `50%` → `"9999px"`), keeps `px`/`rem`. With 2+ distinct numeric radii, map by quantile: `sm` = 25th percentile (or 4px floor), `md` = median, `lg` = 75th percentile. Any value ≥ 9999px or `50%` → `rounded.full = "9999px"`. Return `{}` when <2 distinct radii. Confidence 0.70.

- `SpacingExtractor.extract_spacing_scale(css_text: str) -> dict[str, str]` samples `padding`, `margin`, `gap` declarations. With ≥4 distinct numeric values: `xs` = min, `sm` = 25%ile, `md` = median, `lg` = 75%ile, `xl` = max. Otherwise return `{}`. Confidence 0.50.

- `_extract_brand_guide_prose(pdf_text: str, *, filename: str) -> dict[str, str]` (multi-signal gate per decision 4A): extract section prose only when **both** conditions hold: (a) ≥3 of these 4 headings present in the PDF text (case-insensitive, allow leading numbering like "1. " or "01"): `Overview`, `Colors`, `Typography`, `Do's and Don'ts`; AND (b) the filename matches `re.search(r'(brand|guide|identity|style)', filename, re.IGNORECASE)`. When both hold, split the text by detected headings and return a dict like `{"overview": "...", "dos_and_donts": "...", "colors": "...", "typography": "..."}`. Otherwise return `{}`.

Wire these into the existing `extract_from_url` and `extract_from_pdf` so returned drafts include `typography`, `rounded`, `spacing` from URL sources, and `brand_guide_prose` from qualifying PDF sources.

Tests live in `skills/_parallax/white-label/tests/test_extract.py` and `test_roundtrip_and_url.py`. Cover: h1..h6 type scale from CSS, border-radius quantile clustering, `border-radius: 50%` → full, spacing scale emits when ≥4 distinct, omits when thin, multi-signal gate — qualifying PDF extracts prose, non-qualifying PDF returns `{}`.

### Wave 2 (Lane L4) — DESIGN.md linter integration

Add a new class `DesignMdValidator` to `skills/_parallax/white-label/validator.py`:

```python
class DesignMdValidator:
    NPX_TIMEOUT_SECONDS = 20
    _availability_cache: bool | None = None

    @classmethod
    def is_available(cls) -> bool:
        if cls._availability_cache is not None:
            return cls._availability_cache
        # shutil.which('npx') is not None AND `npx --version` exits 0 within 5s
        ...

    @staticmethod
    def lint(design_md_text: str) -> dict[str, Any]:
        # Write to tmp file, run `npx @google/design.md lint <path> --format json`,
        # parse stdout, normalize to:
        #   {"status": "pass"|"warn"|"fail"|"skipped",
        #    "available": bool,
        #    "findings": [{"rule", "severity", "message", "token"|None}, ...],
        #    "raw_exit_code": int,
        #    "note": str|None}
        # On is_available() False, return {"status": "skipped", "available": False, "note": "npx not installed"}
        # On TimeoutExpired or non-JSON stdout, return skipped with the reason in `note`.
        # NEVER raises.
```

This validator augments (does not replace) the existing `ColorValidator.validate_text_contrast` (WCAG AA) check. Extend the in-memory `validation_summary` dict produced at SKILL.md Step 2 with a new top-level `design_md` key carrying the linter result. The linter runs *after* the in-memory draft is finalized but *before* the Step 3 confirmation gate.

Tests live in `skills/_parallax/white-label/tests/test_validator.py`. Cover: skipped when npx missing (monkeypatch `shutil.which`), parses clean JSON output (mock `subprocess.run`), parses findings array, handles `TimeoutExpired`, handles non-JSON stdout. Add an integration test `test_lint_real_npx_smoke` decorated `@pytest.mark.skipif(not DesignMdValidator.is_available())` (decision 8A).

### Wave 2 (Lane L5) — Schema rename + loader migration

Bump `skills/_parallax/white-label/schema.yaml` to `schema_version: 2`. Add v2 frontmatter fields under `branding`:

```yaml
branding:
  colors:
    primary:   <hex>
    secondary: <hex>
    tertiary:  <hex>     # was 'accent' in v1
    neutral:   <hex>     # flat hex per 5A; was 'background' in v1
  typography:
    h1:       { fontFamily, fontSize, fontWeight, lineHeight, letterSpacing }
    h2..h5:   { ... }
    body-md:  { ... }
    body-sm:  { ... }
    code:     { ... }    # was 'fonts.monospace' in v1
  rounded:    { sm, md, lg, full }
  spacing:    { xs, sm, md, lg, xl }
  components:
    body-text:
      backgroundColor: "{colors.neutral}"
      textColor: <hex>
```

**Critically, do NOT emit `branding.fonts.*` in v2 write output** (decision 3A). The loader is the single bridge that exposes `fonts.{header,body,monospace}` to downstream consumers, deriving them from `typography.{h1,body-md,code}.fontFamily`.

Modify `loader.py`:

1. Add `_detect_schema_version(data: dict) -> int`. Read `data['metadata']['schema_version']` when present and an int. Otherwise heuristic: if `data['branding']['colors']` contains `tertiary` and not `accent`, return 2; else return 1.

2. Add `_normalize_branding_v2_to_return_shape(data: dict) -> dict`:
   ```python
   colors_legacy = {
       "primary":    colors_v2.get("primary", ""),
       "secondary":  colors_v2.get("secondary", ""),
       "accent":     colors_v2.get("tertiary", ""),
       "background": colors_v2.get("neutral", ""),
       "text":       components_v2.get("body-text", {}).get("textColor", ""),
   }
   fonts_legacy = {
       "header":    typo_v2.get("h1", {}).get("fontFamily", ""),
       "body":      typo_v2.get("body-md", {}).get("fontFamily", ""),
       "monospace": typo_v2.get("code", {}).get("fontFamily", ""),
   }
   return {
       "colors":     colors_legacy,
       "fonts":      fonts_legacy,
       "typography": typo_v2,                  # bonus key
       "rounded":    branding.get("rounded", {}),
       "spacing":    branding.get("spacing", {}),
       "components": components_v2,            # bonus key
   }
   ```

3. The top-level `load_client_branding()` keeps its 9-key return shape intact. Adds bonus keys (`typography`, `rounded`, `spacing`, `components`) that v1 consumers can ignore and v2-aware consumers can opt into.

4. Add `build_config_from_draft(draft, *, schema_version: int = 2)`. v2 branch writes the new shape (no `fonts.*`). v1 branch (called from legacy save paths) still writes the old shape including `accent`/`background`/`fonts.*` for back-compat. v1 stays valid forever; we never reject v1 files.

5. Add `archive_legacy_config(config_path: Path) -> Path` that copies the current `config.yaml` to `.archive/<utc_timestamp>-pre-v2-migration/config.yaml`, returns the archive path. Called only on the first save after schema bump. The orchestrator (SKILL.md Step 4) invokes this when the loader detects an old-shape file about to be overwritten.

Update `schema.yaml`'s embedded JSON schema dict (`_JSONSCHEMA` if it exists) with `oneOf` branches for v1 vs v2. v1 schema unchanged. v2 schema requires `branding.colors.{primary,secondary,tertiary,neutral}` and at least one `typography.*` entry.

Tests live in `skills/_parallax/white-label/tests/test_loader.py` and a new `tests/test_regression.py`. The 3 critical regression gates (decision 7A) go into `test_regression.py` with a committed v1 fixture `tests/fixtures/legacy_v1_config.yaml`:

```yaml
# tests/fixtures/legacy_v1_config.yaml
metadata: { schema_version: 1, client_name: "Test Client", ... }
branding:
  colors: { primary: "#001122", secondary: "#334455", accent: "#FF6600", background: "#FFFFFF", text: "#222222" }
  logos:  { primary: "/dummy/logo.png" }
  fonts:  { header: "Inter", body: "Source Sans Pro", monospace: "JetBrains Mono" }
```

The 3 gates:
- `test_v1_file_returns_legacy_colors_accent` — load the fixture, assert `result["colors"]["accent"] == "#FF6600"`.
- `test_v2_file_returns_legacy_keys_via_tertiary` — synthesize a v2 dict, write, load, assert `result["colors"]["accent"] == result["colors"]["accent value from tertiary"]`.
- `test_clear_archives_both_files` — run the `--clear` path (mock filesystem), assert both `config.yaml` and `DESIGN.md` end up under `.archive/<ts>-clear/`.

Other loader tests (in `test_loader.py`): heuristic schema-version autodetect, archive_legacy_config behavior, v2 round-trip, build_config_from_draft v2 omits `fonts.*`, v1 still includes `accent`, v2 components.body-text wiring.

### Wave 3 (Lane L6) — merge.py token-level reconcile

Extend `extract/merge.py`:

- `cross_validate_visual(drafts: list[dict]) -> dict[str, list[dict]]`: in addition to the existing color and font checks, compare per typography level (`h1`..`h5`, `body-md`, `body-sm`, `code`) at the `fontFamily` granularity; per rounded slot (`sm`, `md`, `lg`, `full`); per spacing slot (`xs`..`xl`). Mismatches go into the existing `mismatches` list with `field` paths like `typography.h1.fontFamily`, `rounded.md`, `spacing.lg`.

- `merge_drafts(drafts)`: extend to take the *highest-confidence* source per leaf token. For Typography objects, treat the whole h1 object as one atomic unit — pick the source whose `confidence_scores['typography.h1']` is highest, take that source's `h1` dict verbatim. Do not field-mix two h1 objects (a half-Inter half-Calibri h1 is a worse outcome than picking one). Same atomicity rule for rounded objects.

Tests live in `skills/_parallax/white-label/tests/test_extract.py`. Cover: typography mismatch flagged, rounded mismatch flagged, spacing mismatch flagged, higher-confidence typography wins, object atomicity (no field-mixing).

### Wave 3 (Lane L7) — SKILL.md orchestration

Edit `skills/white-label-onboard/SKILL.md`:

**Step 0 — add `--regenerate-design-md` row** to the input mode table. New row: `Argument is --regenerate-design-md` → mode "Regenerate-from-config".

**Step 3 — confirmation gate display layering.** Keep the existing primary view (concise table at lines 587–633). Append two new blocks:

```
--- DESIGN.md FRONTMATTER (preview) ---
<indented YAML, truncated to 30 lines max>
Save path: ~/.parallax/client-branding/DESIGN.md

--- DESIGN.md LINT (N findings) ---
[error] broken-ref: {colors.accent} unresolved
[warn]  contrast-ratio: components.body-text textColor on backgroundColor ratio 3.8:1
```

When the linter returned `skipped`, show one line: `DESIGN.md lint: skipped (npx not available; install Node 18+ to enable).` The four-option `AskUserQuestion` set stays unchanged: Confirm / Edit / Re-extract / Abort. Lint findings are informational; they never auto-block.

**Step 3 — extend "Edit specific fields" vocabulary.** Accept dotted paths like `typography.h1.fontSize`, `rounded.md`, `spacing.lg`, plus legacy keys (`colors.primary`, etc.). When an operator edits `typography.h1.fontSize`, reset the entire `typography.h1` object's confidence to 1.0. Reject unknown keys with the message "Unknown field: <path>".

**Step 4 — Save integration.** Insert a new sub-step **4d'** between 4c (config.yaml atomic write) and 4d (existing hash/audit):

```
4d'. Write DESIGN.md
- Call emit_design_md(draft, client_name=..., extracted_at=..., source_refs=[...])
- Atomically write to ~/.parallax/client-branding/DESIGN.md
- chmod 0600
- Compute sha256 → design_md_hash
```

Extend the hash-chained audit entry shape to include `design_md_hash` and `lint_status`:

```json
{
  "ts": "...",
  "action": "save",
  "disposition": "confirmed",
  "config_yaml_hash": "...",
  "design_md_hash": "...",
  "lint_status": "pass",
  "chain_prev": "...",
  "chain_self": "..."
}
```

**New section after Step 4 — Regenerate-from-config mode (decision 2A).** When invoked with `--regenerate-design-md`:

1. Read `~/.parallax/client-branding/config.yaml`. If absent: print "No active branding to regenerate from. Run /parallax-white-label-onboard first." and exit.
2. Validate the config has `branding.colors.primary` AND (`branding.typography.h1` OR `branding.fonts.header`). If missing: print "Cannot regenerate — config.yaml missing required keys: <list>. Re-run /parallax-white-label-onboard to repair." and exit.
3. Construct a synthetic `draft` dict from the config (the inverse of `build_config_from_draft`).
4. Call `emit_design_md(draft, ...)` and atomically write to `~/.parallax/client-branding/DESIGN.md`, chmod 0600.
5. Append audit entry with `action: "regenerate_design_md"`.
6. Print "DESIGN.md regenerated from config.yaml. Sources unchanged."

**`--clear` archives DESIGN.md.** Verify the existing recursive archive logic picks up the new file. If it doesn't (e.g., logic enumerates a fixed list of filenames), extend it.

Tests live in `skills/_parallax/white-label/tests/test_integration.py`. Cover: emits DESIGN.md alongside config.yaml, audit chain includes both hashes, lint findings appear in validation_summary, edit-typography persists, `--regenerate-design-md` round-trip (v2 in, byte-identical out), `--regenerate-design-md` errors on missing primary, `--clear` archives both files, edit-flow rejects unknown keys, DESIGN.md saved with 0600 mode.

## Concrete Steps

Work in the project root: `/Users/bencharoenwong/parallax-workflows/.claude/worktrees/white-label-ingest`.

```bash
# 1. Verify the test environment runs before any change.
cd /Users/bencharoenwong/parallax-workflows/.claude/worktrees/white-label-ingest
python -m pytest skills/_parallax/white-label/tests/ -x --tb=short 2>&1 | tail -30
# Expected: existing tests pass (baseline).

# 2. Run an emit-only spike (Lane L1) and its tests:
# (After implementing emit_design_md.py and test_emit_design_md.py)
python -m pytest skills/_parallax/white-label/tests/test_emit_design_md.py -v
# Expected: 8+ new tests pass.

# 3. Run Lane L2 tests after extending ooxml.py:
python -m pytest skills/_parallax/white-label/tests/test_doc_extractors.py -v
# Expected: existing tests still pass + new typography/radius tests pass.

# 4. Run Lane L3 tests after extending web_pdf.py:
python -m pytest skills/_parallax/white-label/tests/test_extract.py skills/_parallax/white-label/tests/test_roundtrip_and_url.py -v
# Expected: existing tests still pass + new CSS scale/spacing/radii/brand-guide tests pass.

# 5. Run Lane L4 tests after adding DesignMdValidator:
python -m pytest skills/_parallax/white-label/tests/test_validator.py -v
# Expected: existing tests still pass + new lint tests pass.
# If Node 18+ is on PATH, the @pytest.mark.npx smoke test runs; otherwise it is skipped (this is correct).

# 6. Run Lane L5 tests after schema migration + loader changes:
python -m pytest skills/_parallax/white-label/tests/test_loader.py skills/_parallax/white-label/tests/test_regression.py -v
# Expected: all 3 critical regression gates pass + new loader tests pass.

# 7. Run Lane L6 tests after merge.py extensions:
python -m pytest skills/_parallax/white-label/tests/test_extract.py -v -k merge
# Expected: new typography/rounded/spacing merge tests pass.

# 8. Run full test suite end-to-end:
python -m pytest skills/_parallax/white-label/tests/ --tb=short
# Expected: 57+ passing, 0 failing. Some skipped is OK if Node 18+ is unavailable.

# 9. Check that the existing skill files still parse:
python -c "import yaml; yaml.safe_load(open('skills/_parallax/white-label/schema.yaml'))"
python -c "import yaml; print(yaml.safe_load(open('skills/white-label-onboard/SKILL.md').split('---')[1] if '---' in open('skills/white-label-onboard/SKILL.md').read() else '{}'))"
# Expected: no parse errors.

# 10. Commit per wave to keep history clean.
git add -A && git commit -m "feat(white-label): Wave 1 — emit_design_md + extractor widening"
# (continue with Wave 2 and Wave 3 commits)
```

## Validation and Acceptance

The implementation is complete when all of the following hold:

1. Running `python -m pytest skills/_parallax/white-label/tests/ --tb=short` reports 57+ tests passing, 0 failing. Skipped tests are acceptable only for `@pytest.mark.npx` decorated tests when Node 18+ is unavailable.

2. The 3 critical regression gates in `tests/test_regression.py` are present and pass:
   - `test_v1_file_returns_legacy_colors_accent` — load committed `tests/fixtures/legacy_v1_config.yaml`, assert `result["colors"]["accent"] == "#FF6600"`.
   - `test_v2_file_returns_legacy_keys_via_tertiary` — write a v2 config, load it, assert legacy keys derived from new shape.
   - `test_clear_archives_both_files` — `--clear` archives both `config.yaml` AND `DESIGN.md`.

3. Importing `from skills._parallax.white_label.emit_design_md import emit_design_md` works without error, the function is pure (calling it twice with the same input returns byte-identical strings), and it raises `ValueError` on a draft with invalid hex.

4. Running `npx @google/design.md lint <emitted DESIGN.md>` on the output of the spike fixture exits 0 (pass) OR exits 1 with findings limited to known intentional warnings (e.g., `orphaned-tokens` on tokens we omit deliberately). The integration test `test_end_to_end_emit_then_lint` enforces this with `@pytest.mark.skipif(not DesignMdValidator.is_available())`.

5. The schema in `skills/_parallax/white-label/schema.yaml` declares both v1 and v2 shapes; the loader accepts either; the v2 write path emits `colors.tertiary` and never `colors.accent`, emits `colors.neutral` as a flat hex (never a dict), emits `typography.*` but never `fonts.*`.

6. `skills/white-label-onboard/SKILL.md` shows the `--regenerate-design-md` mode in the Step 0 input table, the Step 3 confirmation gate appended blocks for DESIGN.md frontmatter preview and lint findings, and Step 4d' for atomic DESIGN.md write with audit-chain integration.

7. After running `/parallax-white-label-onboard <PPTX-fixture>` (manually or via integration test), `~/.parallax/client-branding/DESIGN.md` exists with mode 0600, contains valid YAML frontmatter plus 8 h2 sections in fixed order, and `audit.jsonl` has a new entry with `design_md_hash` matching the file's sha256.

8. Downstream Parallax skills (`/parallax-client-review`, `/parallax-due-diligence`, `/parallax-deep-dive`) are NOT modified. Their existing code paths that call `load_client_branding()` continue to work because the loader's 9-key return shape is preserved.

## Surprises & Decision Log

_Gemini: append any non-trivial decision, deviation from the plan, or unexpected obstacle here as you implement. Format: one-line bullets with file path + brief rationale._

- (empty)
