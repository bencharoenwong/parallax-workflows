name: parallax-white-label-onboard
description: "Configure white-label client branding for Parallax report output. Extracts colors, logos, fonts AND writing voice from a folder of client collateral (PowerPoint, Word docs), a website URL, a PDF brand guide, or guided wizard intake. Multi-source ingestion supported: when more than one source is provided, mismatches between sources are flagged at the confirmation gate rather than silently resolved. Validates visual assets against WCAG accessibility standards and voice section against corpus-size and completeness thresholds, presents a confirmation gate, then saves branding to ~/.parallax/client-branding/ where downstream skills inject it: visual goes into client-review, due-diligence, and deep-dive PDFs; voice goes into letter-writing, newsletter, and meeting-prep skills. Use to onboard a new client brand, update an existing one, or audit what branding is currently active."
negative-triggers:
  - Generating a client report → use /parallax-client-review (it loads the saved branding automatically)
  - One-off color/font question → answer inline, don't save as config
  - Portfolio construction → use /parallax-portfolio-builder
  - Single-prompt voice rewrite of one piece of content → use /humanizer or /chicago-global-voice; this skill is for persistent client brand state
gotchas:
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

---

# White-Label Client Onboarding

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

Two consumer classes:

**Visual consumers** — Skills that produce a PDF or formatted report. They read `branding.colors`, `branding.logos`, `branding.fonts`. They ignore `voice`. Currently integrated: Tier 1 (`/parallax-cio-letter-prep`, `/parallax-client-review`, `/parallax-due-diligence`, `/parallax-deep-dive`) and Tier 2 (`/parallax-should-i-buy`, `/parallax-thematic-screen`, `/parallax-portfolio-checkup`, `/parallax-portfolio-builder`, `/parallax-rebalance`, `/parallax-morning-brief`, `/parallax-explain-portfolio`, `/parallax-scenario-analysis`, `/parallax-country-deep-dive`, `/parallax-pair-finder`, `/parallax-peer-comparison`, `/parallax-macro-outlook`). The canonical consumer-side contract — header rendering, provenance line, color substitution, logo placement, fallback behavior — lives in `_parallax/white-label/integration-pattern.md` (§1–§9). New visual consumers should JIT-load it via the `<!-- white-label: integration-pattern.md -->` sentinel; the drift gate at `tests/test_integration_pattern_referenced.py` enforces the sentinel ↔ load-directive pairing.

**Voice consumers** — letter-writing, newsletter, meeting-prep, email-drafting, and any skill that produces written content under the client's name. They read `voice.*` and apply it as a style guide before generating prose. They optionally also read `branding.*` if the output is rendered (e.g., a branded PDF letter).

Both classes silently fall back to default Parallax styling/voice if the config is absent or corrupted. This skill never breaks downstream consumers.

**Visual consumer loading pattern.** Visual-rendering skills call `loader.load_visual_branding()` — it returns only the six keys a visual consumer is permitted to read (`client_name`, `colors`, `logos`, `fonts`, `source`, `error`) and structurally excludes `voice`/typography/`multi_source` so a misuse (`branding["voice"]`) raises `KeyError` instead of silently inheriting voice data. The full 13-key shape from `load_client_branding()` is reserved for voice consumers (CIO letter, newsletter, future writing skills) that need both visual and voice. Both wrappers bridge v1↔v2 file shapes so downstream code keeps working through the schema migration:

```python
from skills._parallax.white_label.loader import load_visual_branding

result = load_visual_branding()
if result.get("error") is None:
    # 6-key visual subset — works against both v1 AND v2 config.yaml on disk
    primary_color = result["colors"]["primary"]
    accent_color  = result["colors"]["accent"]   # v2: derived from colors.tertiary
    bg_color      = result["colors"]["background"]  # v2: derived from colors.neutral
    header_font   = result["fonts"]["header"]    # v2: derived from typography.h1.fontFamily
```

For voice consumers that need the full token tree alongside voice, call `load_client_branding()` and read `result["typography"]`, `result["rounded"]`, `result["spacing"]`, `result["components"]` (empty dicts on v1 configs and on every error path — safe to access unconditionally), plus `result["voice"]`.

**Do NOT** read `cfg["branding"]["colors"]["accent"]` directly — that key exists in v1 files but is named `tertiary` in v2. The loader is the single source of truth for the legacy return shape.

**Voice consumer loading pattern:**
```python
import yaml, os
config_path = os.path.expanduser("~/.parallax/client-branding/config.yaml")
voice = None
if os.path.exists(config_path):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    if cfg.get("voice", {}).get("enabled"):
        voice = cfg["voice"]

# In the prose-generation prompt, prepend something like:
if voice:
    style_block = f"""
    Write in the voice of {cfg['metadata']['client_name']}. Their register is
    {voice['tone']['register']}. Primary attributes: {', '.join(voice['tone']['primary_attributes'])}.
    Avoid: {', '.join(voice['tone']['avoid_attributes'])}.

    Non-negotiable rules:
    {chr(10).join('- ' + r for r in voice['core_rules'])}

    Phrases to delete on sight (anti-filler):
    {chr(10).join('- ' + p for p in voice['anti_filler'])}

    How they describe themselves: {voice['company_context']}
    """
    prompt = style_block + "\n\n" + content_prompt
```

**Drafted-vs-Sent feedback loop.** Voice consumer skills SHOULD save the AI draft + the human-edited final version after each session as an entry in `voice.drafted_vs_sent`. This is the highest-quality voice calibration data and improves future outputs. Implementation deferred until at least one voice consumer is wired up.

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

**URL mode:**

```python
draft = extract_from_url(url)
```

If `draft` contains `"error"`, surface it: "Extraction returned partial results due to: <error>. Review and edit before confirming."

**PDF mode:**

```python
draft = extract_from_pdf(pdf_path)
```

PDF extraction reads up to 5 pages by default (per the extract module). If the brand guide appears to be a dedicated multi-page document and extraction confidence is low (<0.6 average), offer: "Low confidence on PDF extraction. Shall I read more pages or switch to wizard mode to confirm values manually?"

**PPTX mode:**

```python
draft = extract_from_pptx(pptx_path)
```

`extract_from_pptx` reads `ppt/theme/theme1.xml` directly, so colors and fonts come from the canonical OOXML theme declarations (confidence 0.9). Body text from every text frame is aggregated into `draft["voice_corpus"]` for the voice extraction step. The OOXML slot mapping is fixed: `accent1`→primary, `accent2`→secondary, `accent3`→accent, `dk1`→text, `lt1`→background. If the deck uses a heavily customized theme that overrides these slots inline, theme XML may understate the actual on-slide colors — flag this and offer wizard override.

**DOCX mode:**

```python
draft = extract_from_docx(docx_path)
```

Identical pattern via `word/theme/theme1.xml`. Body text from all paragraphs (skipping headers/footers) aggregated into `draft["voice_corpus"]`. Word's defaults are commonly Calibri (header) + Cambria (body); if the document inherits defaults rather than declaring custom fonts, the extracted values reflect the default theme — note this in `notes`.

**Folder mode:**

Folder mode is NOT a blind iteration. The operator's folder may contain a mix of branded marketing material (newsletters, decks, brochures), voice-only material (memos, white papers, blog exports, transcripts), and irrelevant files (logos as standalone images, spreadsheets, raw data). The LLM must inventory and classify before extracting, and confirm with the operator when the folder is mixed or ambiguous.

**Step F-1 — Inventory the folder.** List every file (recursive one level by default; ask the operator if deeper recursion is wanted for large structures). Capture filename, extension, and size. Group by type:

| Group | Extensions | Extraction path |
|---|---|---|
| **OOXML branded** | `.pptx`, `.docx` | `extract_from_pptx` / `extract_from_docx` — visual (theme XML) + voice corpus |
| **PDF branded** | `.pdf` | `extract_from_pdf` — visual (heuristic, low confidence) + voice corpus |
| **Text-only voice** | `.md`, `.markdown`, `.txt`, `.html`, `.htm`, `.rtf`, `.eml` | Read tool → strip markup if HTML/EML → append to supplementary voice corpus (no visual extraction) |
| **Visual asset** | `.png`, `.jpg`, `.jpeg`, `.svg`, `.ico`, `.webp` | Treat as candidate logo / brand asset; offer to use as logo path if naming or count suggests it |
| **Out of scope** | everything else (`.xlsx`, `.csv`, `.zip`, etc.) | Skip; report skip count to operator |

**Step F-2 — Classify each in-scope file by likely role.** Read the filename + (for OOXML/PDF) sample the first few hundred chars of body text. Categorize:

| Role | Heuristic signals | Treatment |
|---|---|---|
| **Branded marketing** | filenames like `newsletter`, `quarterly`, `letter`, `brochure`, `pitch`, `deck`; cover slide / first page mentions client name + tagline | Extract visual + voice. High weight in voice corpus. |
| **Internal memo / whitepaper** | filenames like `memo`, `internal`, `notes`, `research`, `whitepaper`, `analysis`; body text is dense prose without marketing framing | Extract voice only. Skip visual (theme is generic Office default; would mislead). |
| **Client-policy / compliance** | filenames like `policy`, `compliance`, `disclosure`, `terms`; body text is legal boilerplate | Skip voice (legal language is a different register). Optionally pull explicit disclaimer text into the `disclaimers[]` section if found. |
| **Transcript / interview** | filenames like `transcript`, `interview`, `Q&A`, `call`; body text is conversational with multiple speakers | Voice only, but flag in notes — interview voice is unrepresentative of written voice. Lower-weight or ask operator. |
| **Ambiguous** | filename gives no signal AND first-page sample is inconclusive | Surface to operator: show filename, file size, first 200 chars of text, ask "Include this for visual + voice / voice only / skip?" |

**Step F-3 — Operator confirmation gate.** Before extraction, present the inventory + classification:

```
Folder: <path>  (depth: 1)

In-scope files (8):
  ✓ newsletters/2026-Q1.pptx           — branded marketing  (visual + voice)
  ✓ newsletters/2026-Q2.pptx           — branded marketing  (visual + voice)
  ✓ letters/2026-jan-client-letter.docx — branded marketing  (visual + voice)
  ✓ research/macro-outlook-2026.docx   — internal memo      (voice only)
  ✓ research/credit-views.md            — text voice         (voice only)
  ? misc/agm-transcript.txt             — transcript         (ASK: include?)
  - misc/holdings-2026q1.xlsx           — out of scope       (skipped)
  - misc/portfolio-data.csv             — out of scope       (skipped)

Visual assets (2):
  ✓ assets/logo.png                     — candidate logo
  - assets/team-photo.jpg                — skipped (not logo-shaped naming)

Confirm? Or change classification for any file?
```

For ambiguous items (the `?` rows), ask one `AskUserQuestion` per file with the choices: include for visual + voice / include for voice only / skip.

**Step F-4 — Extract per classification.**

```python
import os
from pathlib import Path
folder = Path(folder_path)
drafts: list = []
voice_only_corpus_chunks: list[str] = []  # text from non-OOXML voice-only files

for f, classification in classified_files.items():
    if classification == "skip":
        continue
    if classification in ("branded_visual_voice", "branded"):
        if f.suffix.lower() == ".pptx":
            drafts.append(extract_from_pptx(str(f)))
        elif f.suffix.lower() == ".docx":
            drafts.append(extract_from_docx(str(f)))
        elif f.suffix.lower() == ".pdf":
            drafts.append(extract_from_pdf(str(f)))
    elif classification == "voice_only":
        if f.suffix.lower() in (".pptx", ".docx", ".pdf"):
            # extract for voice corpus only — discard the (likely-default) visual fields
            d = (extract_from_pptx if f.suffix.lower() == ".pptx"
                 else extract_from_docx if f.suffix.lower() == ".docx"
                 else extract_from_pdf)(str(f))
            voice_only_corpus_chunks.append(d.get("voice_corpus", {}).get("text", ""))
        else:
            # Text-only file — use Read tool, strip markup if HTML/EML, append
            text = read_text_file(str(f))  # operator-side helper; see below
            voice_only_corpus_chunks.append(text)

if not drafts and not voice_only_corpus_chunks:
    # Empty supported-file inventory; surface error and offer wizard fallback
    ...

# Merge OOXML drafts (visual + voice)
if len(drafts) == 1:
    draft = drafts[0]
elif len(drafts) > 1:
    draft = merge_drafts(drafts)
    xv = cross_validate_visual(drafts)
    draft["multi_source"] = {
        "sources": [d["source"] for d in drafts],
        "mismatches": xv["mismatches"],
        "agreements": xv["agreements"],
    }
else:
    # Voice-only folder — start with an empty visual draft
    from datetime import datetime, timezone
    draft = {
        "colors": {}, "logos": {}, "fonts": {},
        "source": {"type": "folder-voice-only", "reference": str(folder)},
        "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "confidence_scores": {},
        "voice_corpus": {"text": "", "word_count": 0, "truncated": False},
    }

# Append voice-only corpus chunks to draft's voice_corpus
if voice_only_corpus_chunks:
    extra_text = "\n\n".join(voice_only_corpus_chunks)
    existing = draft.get("voice_corpus", {}).get("text", "")
    combined = (existing + "\n\n" + extra_text).strip()
    # Truncate again if needed (3000-word cap matches _voice_corpus_from_text)
    words = combined.split()
    if len(words) > 3000:
        combined = " ".join(words[:3000])
        truncated = True
    else:
        truncated = False
    draft["voice_corpus"] = {
        "text": combined,
        "word_count": len(words),
        "truncated": truncated,
    }
```

`read_text_file` is an inline helper — operator just uses the Read tool for `.md`/`.txt`/`.html`/`.eml`, strips HTML tags if present (BeautifulSoup or simple regex), strips email headers if `.eml`, returns the body. No new Python dependency required for v1.

**Background frameworks (cited inline so an LLM reading this skill has the grounding):**

The voice extraction in Step 1.5 follows three named patterns documented in `DECISIONS.md` 2026-05-06:

- **Lago voice template** (`getlago/inside-lago-voice-skill`): 7 sections — Voice / Core Rules / Anti-Filler / Audience Adaptation / Channel Notes / Drafted-vs-Sent / Company Context. Calibration is via *Drafted vs Sent* example pairs.
- **Rezvani brand audit** (`alirezarezvani/claude-skills/marketing-skill/brand-guidelines`): 7-dimension audit (colors, fonts, logo, body text, imagery, tone, prohibited uses) and Tone Matrix (voice × context).
- **Genesys 4-phase extraction** (`matteotitta/genesys-claude-code-pmm-quickstart/.claude/skills/brand-guidelines`): Fetch & Detect → Extract Tokens → Visual Description → Generate Output → Review, with confidence scoring 0–5 and explicit gap documentation.

The skill blends them: Genesys 4-phase backbone → Rezvani schema as the output target → Lago voice section embedded inside.

**Multi-source mode (URL + folder, or any 2+ sources):**

```python
drafts = []
for arg in args:
    if arg.startswith("http"):
        drafts.append(extract_from_url(arg))
    elif arg.endswith(".pptx"):
        drafts.append(extract_from_pptx(arg))
    elif arg.endswith(".docx"):
        drafts.append(extract_from_docx(arg))
    elif arg.endswith(".pdf"):
        drafts.append(extract_from_pdf(arg))
    elif Path(arg).is_dir():
        # Recurse via folder mode helper
        ...

draft = merge_drafts(drafts)
cross_validation = cross_validate_visual(drafts)
draft["multi_source"] = {
    "sources": [d["source"] for d in drafts],
    "mismatches": cross_validation["mismatches"],
    "agreements": cross_validation["agreements"],
}
```

Mismatches are NOT auto-resolved here. They surface in the Step 3 confirmation gate.

**Draft structure after extraction:**

All extraction modes produce a `draft` dict with this shape:
```python
{
    "colors": {
        "primary": {"hex": "#...", "confidence": 0.95},
        "secondary": {"hex": "#...", "confidence": 0.90},
        "accent": {"hex": "#...", "confidence": 0.85},
        "background": {"hex": "#FFFFFF", "confidence": 0.75},
        "text": {"hex": "#333333", "confidence": 0.70},
    },
    "logos": {
        "primary": {"url": "https://...", "confidence": 0.90},  # or "path": "..."
        "favicon": {"url": "https://...", "confidence": 0.80},
    },
    "fonts": {
        "header": {"name": "Montserrat", "confidence": 0.85},
        "body": {"name": "Open Sans", "confidence": 0.80},
        "monospace": {"name": "Courier New", "confidence": 0.70},
    },
    "source": {"type": "url"|"pdf"|"pptx"|"docx"|"wizard"|"multi", "reference": "..."},
    "extracted_at": "2026-04-30T00:00:00Z",
    "confidence_scores": {...},
    "voice_corpus": {                         # only present for sources with body text
        "text": "...",                        # cleaned, optionally truncated to ~3000 words
        "word_count": 0,
        "truncated": False,
    },
    # Only present for multi-source extraction:
    "multi_source": {
        "sources": [...],
        "mismatches": [{"field": "...", "values": [...]}, ...],
        "agreements": [{"field": "...", "value": ...}, ...],
    },
}
```

Missing fields (empty dict values or absent keys) are acceptable — they will surface as warnings at Step 2 and can be filled at Step 3.

### Step 1.5 — Voice extraction (only when corpus is available)

**Skip this step entirely if `draft["voice_corpus"]["word_count"] < 500`.** Below that floor, voice extraction is unreliable; set `draft["voice"] = {"enabled": False}` and continue to Step 2. Surface the gap to the user: "Voice section not populated — corpus is only `<N>` words, below the 500-word minimum. Add more sample documents to enable voice extraction."

**When corpus is sufficient,** drive voice extraction via in-skill prompting (no Python — this is LLM-native work). Read the corpus from `draft["voice_corpus"]["text"]` and prompt yourself with the structure below, then write the resulting fields into `draft["voice"]`.

**Voice extraction prompt structure (Lago 7-section + Rezvani tone matrix):**

```
You are reading {N} words of body text from {client_name}'s recent client-facing
material ({source_descriptor}). Your task: extract their writing voice into a
structured profile that downstream skills will use to draft new material that
sounds like them.

Produce a YAML block with these fields. Be specific. "Write clearly" is useless;
"Cut any sentence that announces the smart thing before saying it" is actionable.

positioning: |  # 1-2 sentences: who they are, what they do, who they serve
tone:
  register: # one phrase, e.g., "formal-institutional", "warm-advisory", "technical-direct"
  primary_attributes: [3-5 attributes observed in the corpus]
  avoid_attributes:   [words/tones that would clearly NOT fit the corpus]
core_rules: [3-7 non-negotiables derived from observed patterns — e.g., "Never make
            forward-looking statements without a 'subject to' clause"]
anti_filler: [5+ phrase patterns to delete from AI drafts — e.g., "leverage our
              expertise", "best-in-class", "we believe that we believe"]
audience_adaptation:  # optional; only if the corpus shows clear differentiation
  - audience: ...
    notes: ...
channel_notes:        # optional; only if the corpus spans multiple channels
  - channel: ...
    notes: ...
company_context: |    # how they describe themselves, competitors, positioning
disclaimers:          # only include if explicit disclaimers appear in the corpus
  - jurisdiction: ...
    text: ...
    placement: ...
```

Set `draft["voice"]["enabled"] = True`, `draft["voice"]["source_corpus"]["word_count"] = N`, `draft["voice"]["source_corpus"]["documents"] = [list of source references]`, `draft["voice"]["source_corpus"]["confidence"] = your_self_assessed_confidence_0_to_1`.

**Self-check before writing into draft:**

- [ ] Did I derive `core_rules` and `anti_filler` from the corpus, or am I producing generic asset-management boilerplate? Generic = bad. Re-do.
- [ ] If I claim `tone.register` is "formal-institutional", can I quote 2 specific phrases from the corpus that prove it? If not, soften the claim.
- [ ] Did I leave any field as `""` or `[]` because the corpus genuinely doesn't show it, or because I didn't look? Be honest — empty is better than fabricated.

**Drafted-vs-Sent pairs are not auto-extractable.** They require comparison between an AI draft and a human-edited version. Leave `drafted_vs_sent: []` in the initial extraction. Document in `voice.source_corpus.notes` that this should be populated incrementally as the client uses downstream skills (we save the draft + sent pair after each session).

### Step 1.75 — Completeness audit & supplement offer

Before validation, audit the draft for thinness and proactively offer to supplement. The operator may have given just a URL not realizing that adding a sample folder dramatically improves voice extraction; saving a thin config without surfacing the gap is a UX failure.

**Audit checks:**

```python
audit = []
n_brand_colors = sum(1 for r in ["primary", "secondary", "accent"] if r in draft.get("colors", {}))
n_fonts = len(draft.get("fonts", {}))
voice_words = draft.get("voice_corpus", {}).get("word_count", 0)
voice_enabled = draft.get("voice", {}).get("enabled", False)
has_logo = "primary" in draft.get("logos", {})

if n_brand_colors < 2:
    audit.append(("colors_thin", f"only {n_brand_colors} brand color(s) extracted"))
if n_fonts == 0:
    audit.append(("fonts_missing", "no fonts extracted (URL extraction often misses externally-hosted CSS)"))
if not has_logo:
    audit.append(("logo_missing", "no logo extracted"))
if voice_words < 500:
    audit.append(("voice_corpus_thin", f"voice corpus is only {voice_words} words; voice extraction skipped (need ≥500)"))
elif voice_words < 2000:
    audit.append(("voice_corpus_low", f"voice corpus is {voice_words} words; below recommended 2000 for high-confidence voice extraction"))
if not voice_enabled and voice_words >= 500:
    audit.append(("voice_disabled_unexpectedly", "voice corpus was sufficient but voice section is not enabled"))
```

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

Run all validators in parallel (no inter-dependency). Collect results into a `validation_results` dict.

**Color contrast (WCAG AA):**
```python
text_color = draft["colors"].get("text", {}).get("hex", "#333333")
bg_color   = draft["colors"].get("background", {}).get("hex", "#FFFFFF")
contrast   = ColorValidator.validate_text_contrast(text_color, bg_color)
# contrast = {"status": "pass"|"warn"|"fail", "ratio": float, "recommendation": str|None}
```

**Individual hex validation:**
```python
for role in ["primary", "secondary", "accent", "background", "text"]:
    hex_val = draft["colors"].get(role, {}).get("hex", "")
    if hex_val:
        valid = ColorValidator.is_valid_hex(hex_val)
        # If not valid: fail that color slot
```

**Logo validation** (only if the logo has been downloaded to a local path; skip for URLs until Step 4):
```python
if "path" in draft["logos"].get("primary", {}):
    logo_result = LogoValidator.validate_logo(draft["logos"]["primary"]["path"])
# For URLs: mark as "pending" — validate after download in Step 4
```

**Font validation:**
```python
for role in ["header", "body", "monospace"]:
    font_name = draft["fonts"].get(role, {}).get("name", "")
    if font_name:
        font_result = FontValidator.validate_font(font_name)
```

**Voice validation** (skip when `draft["voice"]["enabled"]` is False):
```python
from skills._parallax.white_label.validator import VoiceValidator
voice_result = VoiceValidator.validate_voice(draft.get("voice", {"enabled": False}))
# voice_result = {"status": "pass"|"warn"|"fail"|"skipped", "checks": {"corpus": {...}, "completeness": {...}}}
```

`status: "skipped"` is the default when voice extraction was bypassed (corpus too small or visual-only sources). It is informational, not an error. Do NOT block the save on a skipped voice section — visual-only configs remain valid for visual-only downstream consumers.

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

**Validation rules:**
- `fail` on: invalid hex format, logo file >5MB, logo format unsupported
- `warn` on: WCAG contrast 3.0–4.49, logo dimensions <200×200, font not on system
- `pass` on: all checks clear

Validation warnings and failures are informational only. They never block the save. Surface them clearly at Step 3 so the user can make an informed choice.

**Confidence summary:**
Compute average confidence across all extracted fields:
```python
avg_conf = sum(draft["confidence_scores"].values()) / max(len(draft["confidence_scores"]), 1)
lowest_field = min(draft["confidence_scores"], key=draft["confidence_scores"].get, default="n/a")
```

### Step 3 — Confirmation gate (REQUIRED before save)

Present the draft in this format:

```
============================================================
WHITE-LABEL BRANDING — DRAFT FOR CONFIRMATION
============================================================

Source: <URL | PDF path | wizard>
Extraction confidence: avg <X.XX>, lowest <field>: <conf>

--- COLORS ---
Primary:     <hex> ████  (confidence: <X.XX>)
Secondary:   <hex> ████  (confidence: <X.XX>)
Accent:      <hex> ████  (confidence: <X.XX>)
Background:  <hex> ████  (confidence: <X.XX>)
Text:        <hex> ████  (confidence: <X.XX>)

--- LOGOS ---
Primary:     <URL or local path>  (confidence: <X.XX>)
Favicon:     <URL or local path | not found>  (confidence: <X.XX>)

--- FONTS ---
Header:      <font name>  (confidence: <X.XX>)
Body:        <font name>  (confidence: <X.XX>)
Monospace:   <font name>  (confidence: <X.XX>)

--- VOICE ---
Enabled:     <yes|no — corpus N words from M document(s)>
Register:    <e.g., "formal-institutional">
Tone:        <comma-list of primary_attributes>
Avoid:       <comma-list of avoid_attributes>
Core rules:  <count>
Anti-filler: <count>
Disclaimers: <count, with jurisdictions if any>
Confidence:  <X.XX>
(only present when voice.enabled)

--- MULTI-SOURCE MISMATCHES ---
<for each mismatch>
  field: <e.g., colors.primary>
    <source_a>: <value_a>
    <source_b>: <value_b>
(only present when len(sources) >= 2 and mismatches found; otherwise omit section)

--- VALIDATION SUMMARY ---
<validation table from Step 2>

--- DESIGN.md FRONTMATTER (preview) ---
<indented YAML excerpt of frontmatter, truncated to 30 lines max>
Save path: ~/.parallax/client-branding/DESIGN.md

--- DESIGN.md LINT (N findings) ---
<one line per finding: [severity] rule: message>
(when status="skipped": single line "DESIGN.md lint: skipped (npx not available; install Node 18+ to enable).")
(when status="pass" with 0 findings: single line "DESIGN.md lint: pass (0 findings).")

--- MISSING FIELDS ---
<list of fields with confidence 0.0 or absent, or "none">

============================================================
```

The DESIGN.md frontmatter preview is generated by calling `emit_design_md(draft, client_name=..., extracted_at=..., source_refs=[...])` from `skills/_parallax/white-label/emit_design_md.py`, splitting on `---` fences, and indenting the YAML block. Lint findings come from `DesignMdValidator.lint(design_md_text)` in `validator.py`. Both are informational — they never auto-block the save. The four-option `AskUserQuestion` set below stays unchanged.

**Mismatch resolution.** If multi-source mismatches are present, the user MUST pick a winner per mismatched field before saving. Use `AskUserQuestion` per mismatched field, listing each candidate value as a choice (with source attribution). Apply the chosen value to `draft` before proceeding to save. Do NOT attempt to auto-pick by confidence or recency — the PM/CIO is the canonical source of truth on which version of their brand is current.

For color swatches (the `████` blocks), use Unicode block characters filled with a text approximation if terminal color is unavailable: `[#FF5733]`.

Then ask via `AskUserQuestion`:

> Confirm this branding configuration?
> - **Confirm and save** (Recommended if extraction looks right)
> - **Edit specific fields** — you'll be prompted for which fields to change
> - **Re-extract from different source** — provide a different URL or PDF path
> - **Abort** — abandon this session, no save

**If "Edit specific fields":**

1. Serialize the pre-edit draft to an in-memory holding buffer (`pre_edit_draft = copy.deepcopy(draft)`).
2. Ask: "Which fields do you want to edit? (e.g., colors.primary, typography.h1.fontSize, rounded.md, spacing.lg, logos.primary)" — accept comma-separated list. Accept both legacy keys (`colors.primary`, `fonts.header`, etc.) AND new DESIGN.md vocabulary (`typography.<level>.fontSize`, `rounded.<size>`, `spacing.<slot>`, `components.body-text.textColor`). Reject any other path with the message "Unknown field: <path>".
3. For each named field, ask for the new value via `AskUserQuestion`.
4. Update `draft` with the new values. Set confidence to 1.0 for any manually edited field. When the edited path is inside a typography object (e.g., `typography.h1.fontSize`), reset the entire `typography.h1` object's confidence (`confidence_scores["typography.h1"] = 1.0`).
5. Re-run Step 2 validation on the edited draft.
6. Re-render the confirmation gate with updated values and validation.
7. When the user ultimately confirms the edited version:
   - Write `pre_edit_draft` to `~/.parallax/client-branding/.archive/<timestamp>/pre_edit.yaml`
   - Optionally ask: "One line on what you changed and why? (Enter to skip)" — if non-empty, write to `.archive/<timestamp>/edit_notes.md`
   - Log audit entry with `disposition="edited"`, `draft_yaml_hash` = sha256 of the **pre-edit** draft

**If "Re-extract from different source":**
- Discard any holding buffer.
- Log an audit entry with `disposition="re_extracted"`, capture the source hint.
- Ask: "Please provide the new URL or PDF path."
- Return to Step 0 with the new source.

**If "Abort":**
- Discard any holding buffer.
- Log an audit entry with `disposition="rejected"`.
- Output: "Branding session aborted. No files written."
- Stop.

**If "Confirm and save" on the pristine draft (no edits):**
- Log audit entry with `disposition="confirmed"`, `draft_yaml_hash` = sha256 of draft YAML.
- Proceed to Step 4.

### Step 4 — Save

#### 4a. Pre-write validation

Before any I/O:
- Verify `~/.parallax/client-branding/` is writable (create it with `os.makedirs(..., mode=0o700, exist_ok=True)` if absent).
- Verify the draft contains at minimum: one color (`branding.colors.primary`), or one logo, or one font. An entirely empty config is a user error — ask to confirm or abort.
- Validate all hex colors one final time via `ColorValidator.is_valid_hex()`. Reject any that fail (they should have been caught at Step 2, but this is a hard gate).

#### 4b. Download logos to local assets/

```python
import os, urllib.request
assets_dir = os.path.expanduser("~/.parallax/client-branding/assets")
os.makedirs(assets_dir, mode=0o700, exist_ok=True)
```

For each logo with a URL (not already a local path):
```python
# Primary logo
if "url" in draft["logos"].get("primary", {}):
    ext = Path(urlparse(url).path).suffix or ".png"
    dest = f"{assets_dir}/logo-primary{ext}"
    urllib.request.urlretrieve(url, dest)
    draft["logos"]["primary"]["local_path"] = dest

# Favicon
if "url" in draft["logos"].get("favicon", {}):
    ext = Path(urlparse(url).path).suffix or ".ico"
    dest = f"{assets_dir}/favicon{ext}"
    urllib.request.urlretrieve(url, dest)
    draft["logos"]["favicon"]["local_path"] = dest
```

On download failure: warn ("Logo download failed: <error>. URL preserved in config; local copy unavailable.") and set `local_path` to None. Do not abort the save.

After download, re-run `LogoValidator.validate_logo(dest)` on each successfully downloaded file. Append results to the validation summary in config.

#### 4c. Construct config.yaml

**Use `build_config_from_draft(draft, schema_version=2)` from `loader.py` — do not hand-assemble the config dict.** The builder is the single source of truth for the v2 shape (decisions 3A, 5A: drops `fonts.*`, emits `colors.tertiary` and flat `colors.neutral`, wires `components.body-text`). It also handles the `voice` section and the `multi_source` provenance block — no post-build mutation needed.

```python
from skills._parallax.white_label.loader import build_config_from_draft

config = build_config_from_draft(
    draft,
    client_name=draft.get("client_name", ""),
    extracted_by=draft.get("extracted_by", ""),
    notes=draft.get("notes", ""),
    validation_summary=validation_results,   # from Step 2; updated with post-download logo checks
    schema_version=2,
)
```

For reference, the v2 config shape looks like (do NOT hand-write this — call the builder):

```yaml
metadata:
  schema_version: 2
  client_name: <draft.client_name>
  extracted_at: <draft.extracted_at>
  source: <draft.source>
branding:
  colors:
    primary: <hex>
    secondary: <hex>
    tertiary: <hex>           # was 'accent' in v1
    neutral: <hex>            # flat hex; was 'background' in v1
  logos:
    primary: <local_path or url>
    favicon: <local_path or url>
  typography:
    h1:      { fontFamily, fontSize, fontWeight, lineHeight, letterSpacing }
    h2..h5:  { ... }
    body-md: { ... }
    code:    { ... }          # was 'fonts.monospace' in v1
  rounded:   { sm, md, lg, full }
  spacing:   { xs, sm, md, lg, xl }
  components:
    body-text:
      backgroundColor: "{colors.neutral}"
      textColor: <hex>        # text-on-neutral pair; was 'colors.text' in v1
validation_summary: <validation_results>
confidence_scores: <draft.confidence_scores>
```

`fonts.*` is **not** emitted in v2. The loader's `_normalize_branding_v2_to_return_shape` derives the legacy `fonts.{header,body,monospace}` keys from `typography.{h1,body-md,code}.fontFamily` at read time, so downstream consumers continue to see the 9-key return shape unchanged.

Legacy v1 fallback (only when a downstream skill or migration explicitly passes `schema_version=1`):

```python
config = build_config_from_draft(draft, schema_version=1, validation_summary=validation_results)
# Emits the old shape: colors.accent / colors.background / colors.text + fonts.{header,body,monospace}
```

Compute `config_hash = sha256(yaml.safe_dump(config["branding"], sort_keys=True).encode()).hexdigest()`.

#### 4d. Archive existing config (if present)

```python
existing = os.path.expanduser("~/.parallax/client-branding/config.yaml")
if os.path.exists(existing):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = os.path.expanduser(f"~/.parallax/client-branding/.archive/{ts}")
    os.makedirs(archive_dir, mode=0o700, exist_ok=True)
    shutil.copy2(existing, f"{archive_dir}/config.yaml")
```

Archive failures are non-blocking — log a warning but do not abort.

#### 4e. Write files

Write to a staging directory first, then atomic-swap:

```python
staging_dir = os.path.expanduser("~/.parallax/client-branding/.staging")
os.makedirs(staging_dir, mode=0o700, exist_ok=True)

# Write config.yaml to staging
config_path = f"{staging_dir}/config.yaml"
with open(config_path, "w") as f:
    yaml.safe_dump(config, f, sort_keys=False, allow_unicode=True)

# Move from staging to active (atomic)
shutil.move(f"{staging_dir}/config.yaml",
            os.path.expanduser("~/.parallax/client-branding/config.yaml"))

# Enforce permissions
os.chmod(os.path.expanduser("~/.parallax/client-branding/config.yaml"), 0o600)
os.chmod(assets_dir, 0o700)
```

On write failure: report "Save failed: <file> write error. No files written. Safe to retry." Do not proceed to Step 4e' or Step 4f.

#### 4e'. Write DESIGN.md (Google Labs spec)

Emit the DESIGN.md companion file from the in-memory draft and write it atomically alongside `config.yaml`:

```python
from skills._parallax.white_label.emit_design_md import emit_design_md
import hashlib

design_md_text = emit_design_md(
    draft,
    client_name=config["metadata"]["client_name"],
    extracted_at=config["metadata"]["extracted_at"],
    source_refs=[config["metadata"]["source"]["reference"]] if isinstance(config["metadata"].get("source"), dict) else [],
)

design_staging = f"{staging_dir}/DESIGN.md"
with open(design_staging, "w", encoding="utf-8") as f:
    f.write(design_md_text)
shutil.move(design_staging, os.path.expanduser("~/.parallax/client-branding/DESIGN.md"))
os.chmod(os.path.expanduser("~/.parallax/client-branding/DESIGN.md"), 0o600)

design_md_hash = hashlib.sha256(design_md_text.encode("utf-8")).hexdigest()
lint_status = validation_results.get("design_md", {}).get("status", "skipped")
```

`emit_design_md` raises `ValueError` on invalid hex tokens in the draft — caller should have validated at Step 2 already, but if it raises here, treat as a write failure and surface the path of the bad hex. Do not proceed to Step 4f.

#### 4f. Append hash-chained audit entry

**Audit-entry schema bump (intentional chain discontinuity).** With the DESIGN.md emit at Step 4e', save entries now include `design_md_hash` and `lint_status`. The chain hash is `sha256(prior-line-bytes)`, so the first new-shape entry after a v1 audit log will appear as a chain break to any downstream verifier comparing entry shape across the bump. This is intentional: keep the prior chain readable for forensics but treat entries before this point as belonging to the v1 audit schema. If a verifier exists, gate it on `entry.get("design_md_hash") is not None` to detect schema-2 entries; absent that field, treat the entry as v1.

```python
import json, hashlib

audit_path = os.path.expanduser("~/.parallax/client-branding/audit.jsonl")

# Read last entry hash for chaining
prev_hash = "0" * 64
if os.path.exists(audit_path):
    with open(audit_path) as f:
        lines = [l.strip() for l in f if l.strip()]
    if lines:
        prev_hash = hashlib.sha256(lines[-1].encode()).hexdigest()

entry = {
    "schema_version": 1,
    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "skill": "parallax-white-label-onboard",
    "action": "save",
    "applied": True,
    "source": config["metadata"]["source"],
    "config_hash": config_hash,
    "client_name": config["metadata"]["client_name"],
    "prev_entry_hash": prev_hash,
    "validation_status": {
        "colors": {k: v.get("status") for k, v in validation_results.get("colors", {}).items()},
        "logos":  {k: v.get("status") for k, v in validation_results.get("logos",  {}).items()},
        "fonts":  {k: v.get("status") for k, v in validation_results.get("fonts",  {}).items()},
    },
    "disposition": disposition,   # "confirmed" | "edited"
    "draft_yaml_hash": draft_yaml_hash,
    "design_md_hash": design_md_hash,   # sha256 of DESIGN.md text written at Step 4e'
    "lint_status": lint_status,         # "pass" | "warn" | "fail" | "skipped"
}

with open(audit_path, "a") as f:
    f.write(json.dumps(entry, separators=(",", ":")) + "\n")

os.chmod(audit_path, 0o600)
```

**Every extraction attempt that does not result in a save also appends an audit entry** (`action: "extraction_attempt"`, `applied: false`) with `disposition`: `confirmed` / `edited` / `re_extracted` / `rejected`. This includes aborted sessions.

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
| `--status` | Read `config.yaml`, render status block below. If no config: print "No active client branding configured." |
| `--clear` | Ask for explicit confirmation ("Type YES to remove client branding"). On confirm: archive `config.yaml`, `DESIGN.md`, and `assets/` to `.archive/<timestamp>-clear/`, remove live files. Append `{"action":"clear"}` audit entry. |
| `--regenerate-design-md` | Re-emit `DESIGN.md` from the current `config.yaml` without re-extracting from source. See section below. |

### Regenerate-from-config mode (`--regenerate-design-md`)

Purpose: keep `DESIGN.md` in sync with `config.yaml` after manual edits, without re-running source extraction. Single source of truth: `config.yaml` is canonical; `DESIGN.md` is derived.

**What `--regenerate-design-md` preserves and recomputes:**
- **Preserved from config.yaml:** all color tokens, typography/font declarations, rounded/spacing values, logos, voice section (if present), `extracted_at` timestamp, source provenance, `multi_source` block.
- **Recomputed:** DESIGN.md frontmatter YAML and 8-section markdown body. The `design_md_hash` in the audit chain is updated to reflect the new output.
- **Not archived:** the prior `DESIGN.md` is overwritten without an `.archive/` snapshot. If you need to retain the old file, copy it manually before running this flag.
- **v1 config behavior:** `fonts.header`/`fonts.body`/`fonts.monospace` are used as fallbacks for `typography.h1`/`body-md`/`code` slots (confidence 0.5). No `typography.*` block is required in the config.

```python
import os, hashlib, shutil, yaml
from datetime import datetime, timezone
from skills._parallax.white_label.emit_design_md import emit_design_md

config_path = os.path.expanduser("~/.parallax/client-branding/config.yaml")
if not os.path.exists(config_path):
    print("No active branding to regenerate from. Run /parallax-white-label-onboard first.")
    return

with open(config_path) as f:
    cfg = yaml.safe_load(f) or {}

# Validate minimum required keys for emission
required_ok = (
    cfg.get("branding", {}).get("colors", {}).get("primary")
    and (
        cfg.get("branding", {}).get("typography", {}).get("h1")
        or cfg.get("branding", {}).get("fonts", {}).get("header")
    )
)
if not required_ok:
    missing = []
    if not cfg.get("branding", {}).get("colors", {}).get("primary"):
        missing.append("branding.colors.primary")
    if not (cfg.get("branding", {}).get("typography", {}).get("h1") or cfg.get("branding", {}).get("fonts", {}).get("header")):
        missing.append("branding.typography.h1 or branding.fonts.header")
    print(f"Cannot regenerate — config.yaml missing required keys: {missing}. Re-run /parallax-white-label-onboard to repair.")
    return

# Reconstruct a synthetic draft (the inverse of build_config_from_draft)
draft = _config_to_draft(cfg)  # in loader.py; mirrors build_config_from_draft

design_md_text = emit_design_md(
    draft,
    client_name=cfg.get("metadata", {}).get("client_name", ""),
    extracted_at=cfg.get("metadata", {}).get("extracted_at", ""),
    source_refs=[(cfg.get("metadata", {}).get("source") or {}).get("reference", "regenerated-from-config")],
)

# Atomic write
design_md_path = os.path.expanduser("~/.parallax/client-branding/DESIGN.md")
staging = design_md_path + ".staging"
with open(staging, "w", encoding="utf-8") as f:
    f.write(design_md_text)
shutil.move(staging, design_md_path)
os.chmod(design_md_path, 0o600)

# Audit entry
audit_path = os.path.expanduser("~/.parallax/client-branding/audit.jsonl")
prev_hash = "0" * 64
if os.path.exists(audit_path):
    with open(audit_path) as f:
        lines = [l.strip() for l in f if l.strip()]
    if lines:
        prev_hash = hashlib.sha256(lines[-1].encode()).hexdigest()

entry = {
    "schema_version": 1,
    "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "skill": "parallax-white-label-onboard",
    "action": "regenerate_design_md",
    "applied": True,
    "design_md_hash": hashlib.sha256(design_md_text.encode("utf-8")).hexdigest(),
    "prev_entry_hash": prev_hash,
}
import json
with open(audit_path, "a") as f:
    f.write(json.dumps(entry, separators=(",", ":")) + "\n")
os.chmod(audit_path, 0o600)

print("DESIGN.md regenerated from config.yaml. Sources unchanged.")
```

Hard errors (printed + return, no partial emit):
- `config.yaml` not present → "No active branding to regenerate from. Run /parallax-white-label-onboard first."
- `config.yaml` present but missing `branding.colors.primary` or both typography & fonts → "Cannot regenerate — config.yaml missing required keys: ...". Do not write a partial `DESIGN.md`.

Behavior on a v1 config (no `typography.*` block): emitter takes `fonts.header` / `fonts.body` / `fonts.monospace` as the `typography.h1.fontFamily` / `body-md.fontFamily` / `code.fontFamily` defaults (with confidence-neutral 0.5).

### Status block (output of `--status`)

```
Active client branding
──────────────────────
Client:       <client_name>
Source:       <type>: <reference>
Configured:   <extracted_at>

Colors:
  Primary:    <hex> — <swatch text approximation>
  Secondary:  <hex>
  Accent:     <hex>
  Background: <hex>
  Text:       <hex>
  Contrast:   <ratio>:1 (<pass|warn|fail>)

Logos:
  Primary:    <local path | not configured>
  Favicon:    <local path | not configured>

Fonts:
  Header:     <name>
  Body:       <name>
  Monospace:  <name>

Voice:
  Enabled:    <yes | no>
  Register:   <e.g., formal-institutional>
  Tone:       <comma-list of primary_attributes | not configured>
  Corpus:     <N words from M documents | not configured>
  Confidence: <X.XX | not configured>

Validation:   <N pass, N warn, N fail>
Audit chain:  <ok | not yet initialized>
```

If `config.yaml` fails to load (YAML parse error, missing required keys), show: "! Config corrupted or outdated. Re-run /parallax-white-label-onboard to reconfigure."

---

## Error Handling & Edge Cases

**Config exists but is corrupted:** `yaml.safe_load()` raises an exception — catch it, warn ("Config at ~/.parallax/client-branding/config.yaml failed to parse: <error>"), offer to overwrite via full onboarding flow or abort.

**Logo download fails (network error, 404):** Warn and preserve the URL as `branding.logos.primary`. Downstream skills must handle missing local files gracefully by falling back to the URL or omitting the logo.

**All color extraction returns empty:** In URL mode, this is common for heavily JS-rendered sites. Surface the gap clearly: "No colors extracted — the site may require JavaScript rendering. Try providing the hex colors manually via wizard mode."

**Font not on system (FontValidator returns warn):** This is expected for web fonts (Google Fonts, Adobe Fonts, etc.). The warn is informational. Downstream skills should specify the fallback font from `FontValidator._suggest_fallback()` in their CSS/PDF output stack.

**WCAG contrast fails (ratio <3.0):** Surface the failure prominently at the confirmation gate. Do not block the save — the client's brand guidelines take precedence. Record the failure in `validation_summary.colors.contrast`.

**`~/.parallax/client-branding/` not writable:** Hard-fail with a clear error before any I/O. Do not create partial state.

**Staging write fails mid-way:** Clean up the staging directory. Report: "Save failed: <file> write error. No files written. Safe to retry." The active config (if any) remains unchanged.

**PDF has >10 pages:** Read only the first 10 pages via the `pages` parameter. If average confidence is <0.6, offer to continue page-by-page or switch to wizard.

---

## Success Criteria

A successful workflow produces:
- `~/.parallax/client-branding/config.yaml` written, permissions 0600, valid YAML parseable by `yaml.safe_load()`, conforming to schema.yaml field names
- `~/.parallax/client-branding/assets/` exists with at least one downloaded logo file (if a logo URL was provided), directory permissions 0700
- `~/.parallax/client-branding/audit.jsonl` has at least one entry with `"action":"save"` and a valid `prev_entry_hash` chain
- User saw the confirmation gate and explicitly chose "Confirm and save" before any file was written
- Validation summary is present in config.yaml with status per asset (even if some are warn/fail)
- Downstream visual-consumer check: `yaml.safe_load(open("~/.parallax/client-branding/config.yaml"))["branding"]["colors"]["primary"]` returns the configured hex string
- When voice was extracted: `cfg["voice"]["enabled"] is True`, `cfg["voice"]["positioning"]` is a non-empty string, `len(cfg["voice"]["core_rules"]) >= 2`, `len(cfg["voice"]["anti_filler"]) >= 3`, and `cfg["voice"]["source_corpus"]["word_count"] >= 500`
- When multi-source was used: `cfg["multi_source"]["sources"]` lists every input, mismatches were either resolved at the gate or recorded; no silent merges
- When voice was NOT extracted: `cfg["voice"]["enabled"] is False` and downstream voice consumers fall back to defaults silently
