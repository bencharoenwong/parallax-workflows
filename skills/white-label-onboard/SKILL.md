name: parallax-white-label-onboard
description: "Configure white-label client branding for Parallax report output. Extracts colors, logos, and fonts from a website URL, PDF brand guide, or guided wizard intake. Validates assets against WCAG accessibility standards, presents a confirmation gate, then saves branding to ~/.parallax/client-branding/ where downstream skills (client-review, due-diligence, deep-dive) inject it into PDF output. Use to onboard a new client brand, update an existing one, or audit what branding is currently active."
negative-triggers:
  - Generating a client report → use /parallax-client-review (it loads the saved branding automatically)
  - One-off color/font question → answer inline, don't save as config
  - Portfolio construction → use /parallax-portfolio-builder
gotchas:
  - JIT-load _parallax/white-label/schema.yaml before extraction — it is the single source of truth for config.yaml shape
  - JIT-load _parallax/white-label/extract.py and _parallax/white-label/validator.py before running Steps 1 and 2
  - URL input — use defuddle (Bash: `defuddle parse <url> --md`) if available, else WebFetch; do NOT defuddle PDFs
  - PDF input — use the Read tool with `pages` parameter; read up to first 10 pages unless the brand guide is clearly deeper
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
/parallax-white-label-onboard                           # wizard mode — guided intake via prompts
/parallax-white-label-onboard <https://client.com>      # auto-extract from website
/parallax-white-label-onboard <path/to/brand-guide.pdf> # extract from PDF brand guide
/parallax-white-label-onboard --status                  # show active branding summary
/parallax-white-label-onboard --clear                   # remove active branding (requires confirmation)
```

## Where branding lives

`~/.parallax/client-branding/`
- `config.yaml` — canonical config per `_parallax/white-label/schema.yaml`
- `assets/` — downloaded logo files (logo-primary.png, favicon.ico, etc.)
- `audit.jsonl` — append-only hash-chained log
- `.archive/<timestamp>-<source>/` — superseded configs kept for traceability

Files are written `0600`; `assets/` is `0700`; the directory is `0700` on creation.

## Integration with Downstream Skills

When `/parallax-client-review`, `/parallax-due-diligence`, or `/parallax-deep-dive` generate PDF or formatted output, they check for `~/.parallax/client-branding/config.yaml`. If present and valid, they inject the client's colors, logo, and fonts. If absent or corrupted, they fall back to default Parallax branding silently — this skill never breaks downstream consumers.

**Loading pattern for consumer skills:**
```python
import yaml, os
config_path = os.path.expanduser("~/.parallax/client-branding/config.yaml")
if os.path.exists(config_path):
    with open(config_path) as f:
        branding = yaml.safe_load(f)
    # Use branding["branding"]["colors"]["primary"] etc.
```

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

Examine the invocation argument:

| Condition | Mode |
|---|---|
| No argument | Wizard |
| Argument starts with `http://` or `https://` | URL extraction |
| Argument is a file path ending in `.pdf` | PDF extraction |
| Argument is `--status` | Show status block |
| Argument is `--clear` | Clear branding |

For `--status` and `--clear`, jump directly to the Operational Modes section. For the three extraction modes, proceed to Step 1.

If the argument does not match any of the above (e.g., a `.docx` file, a plain ticker, a relative path without extension), stop and ask: "I couldn't identify the input type. Please provide a URL, a PDF path, or run without arguments for wizard mode."

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

**Draft structure after extraction:**

All three modes produce a `draft` dict with this shape:
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
    "source": {"type": "url"|"pdf"|"wizard", "reference": "..."},
    "extracted_at": "2026-04-30T00:00:00Z",
    "confidence_scores": {...},
}
```

Missing fields (empty dict values or absent keys) are acceptable — they will surface as warnings at Step 2 and can be filled at Step 3.

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

--- VALIDATION SUMMARY ---
<validation table from Step 2>

--- MISSING FIELDS ---
<list of fields with confidence 0.0 or absent, or "none">

============================================================
```

For color swatches (the `████` blocks), use Unicode block characters filled with a text approximation if terminal color is unavailable: `[#FF5733]`.

Then ask via `AskUserQuestion`:

> Confirm this branding configuration?
> - **Confirm and save** (Recommended if extraction looks right)
> - **Edit specific fields** — you'll be prompted for which fields to change
> - **Re-extract from different source** — provide a different URL or PDF path
> - **Abort** — abandon this session, no save

**If "Edit specific fields":**

1. Serialize the pre-edit draft to an in-memory holding buffer (`pre_edit_draft = copy.deepcopy(draft)`).
2. Ask: "Which fields do you want to edit? (e.g., colors.primary, logos.primary, fonts.header)" — accept comma-separated list.
3. For each named field, ask for the new value via `AskUserQuestion`.
4. Update `draft` with the new values. Set confidence to 1.0 for any manually edited field.
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

Build the config dict conforming to `_parallax/white-label/schema.yaml`:

```python
import yaml, uuid
from datetime import datetime, timezone

config = {
    "metadata": {
        "schema_version": 1,
        "client_name": draft.get("client_name", ""),
        "extracted_at": draft["extracted_at"],
        "source": draft["source"],
        "extracted_by": draft.get("extracted_by", ""),
        "notes": draft.get("notes", ""),
    },
    "branding": {
        "colors": {
            "primary":    draft["colors"].get("primary",    {}).get("hex", ""),
            "secondary":  draft["colors"].get("secondary",  {}).get("hex", ""),
            "accent":     draft["colors"].get("accent",     {}).get("hex", ""),
            "background": draft["colors"].get("background", {}).get("hex", "#FFFFFF"),
            "text":       draft["colors"].get("text",       {}).get("hex", "#333333"),
        },
        "logos": {
            "primary": draft["logos"].get("primary", {}).get("local_path")
                       or draft["logos"].get("primary", {}).get("url", ""),
            "favicon": draft["logos"].get("favicon", {}).get("local_path")
                       or draft["logos"].get("favicon", {}).get("url", ""),
        },
        "fonts": {
            "header":    draft["fonts"].get("header",    {}).get("name", "Arial"),
            "body":      draft["fonts"].get("body",      {}).get("name", "Helvetica"),
            "monospace": draft["fonts"].get("monospace", {}).get("name", "Courier New"),
        },
    },
    "validation_summary": validation_results,   # from Step 2, updated with post-download logo checks
    "confidence_scores": draft["confidence_scores"],
}
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

On write failure: report "Save failed: <file> write error. No files written. Safe to retry." Do not proceed to Step 4f.

#### 4f. Append hash-chained audit entry

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
  source:      <type>: <reference>
  colors:      <count of non-empty color slots> configured
  logos:       <count> downloaded to assets/
  fonts:       <count of non-empty font slots> configured
  warnings:    <count of warn/fail checks> (see validation above)

Active in: client-review, due-diligence, deep-dive.
Fallback: if branding load fails, downstream skills use default Parallax styling.

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
| `--clear` | Ask for explicit confirmation ("Type YES to remove client branding"). On confirm: archive `config.yaml` and `assets/` to `.archive/<timestamp>-clear/`, remove live files. Append `{"action":"clear"}` audit entry. |

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
- Downstream skill check: `yaml.safe_load(open("~/.parallax/client-branding/config.yaml"))["branding"]["colors"]["primary"]` returns the configured hex string
