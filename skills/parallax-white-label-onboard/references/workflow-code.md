# Workflow Code Reference

Full Python code blocks for `/parallax-white-label-onboard`. SKILL.md keeps the runtime decision logic and breadcrumbs; this file holds the verbose code Claude JIT-loads when actually executing.

JIT-load `_parallax/white-label/extract/` (the extract package), `_parallax/white-label/validator.py`, and `_parallax/white-label/loader.py` before using the patterns below.

---

## Step 1 — Folder extraction (after F-3 operator confirmation)

Folder mode F-4 — extract per classification, merge OOXML drafts, append voice-only chunks:

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

---

## Step 1 — Multi-source extraction (URL + folder + any 2+ sources)

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

---

## Step 1 — Draft structure after extraction

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

---

## Step 1.75 — Completeness audit checks

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

---

## Step 2 — Per-validator code blocks

Run all validators in parallel (no inter-dependency). Collect results into a `validation_results` dict.

### Color contrast (WCAG AA)

```python
text_color = draft["colors"].get("text", {}).get("hex", "#333333")
bg_color   = draft["colors"].get("background", {}).get("hex", "#FFFFFF")
contrast   = ColorValidator.validate_text_contrast(text_color, bg_color)
# contrast = {"status": "pass"|"warn"|"fail", "ratio": float, "recommendation": str|None}
```

### Individual hex validation

```python
for role in ["primary", "secondary", "accent", "background", "text"]:
    hex_val = draft["colors"].get(role, {}).get("hex", "")
    if hex_val:
        valid = ColorValidator.is_valid_hex(hex_val)
        # If not valid: fail that color slot
```

### Logo validation (local files only)

```python
if "path" in draft["logos"].get("primary", {}):
    logo_result = LogoValidator.validate_logo(draft["logos"]["primary"]["path"])
# For URLs: mark as "pending" — validate after download in Step 4
```

### Font validation

```python
for role in ["header", "body", "monospace"]:
    font_name = draft["fonts"].get(role, {}).get("name", "")
    if font_name:
        font_result = FontValidator.validate_font(font_name)
```

### Voice validation

Skip when `draft["voice"]["enabled"]` is False — `status: "skipped"` is the default for visual-only sources and is informational, never an error.

```python
from skills._parallax.white_label.validator import VoiceValidator
voice_result = VoiceValidator.validate_voice(draft.get("voice", {"enabled": False}))
# voice_result = {"status": "pass"|"warn"|"fail"|"skipped", "checks": {"corpus": {...}, "completeness": {...}}}
```

### Confidence summary

```python
avg_conf = sum(draft["confidence_scores"].values()) / max(len(draft["confidence_scores"]), 1)
lowest_field = min(draft["confidence_scores"], key=draft["confidence_scores"].get, default="n/a")
```

---

## Step 4b — Download logos to local assets/

```python
import os, urllib.request
from pathlib import Path
from urllib.parse import urlparse

assets_dir = os.path.expanduser("~/.parallax/client-branding/assets")
os.makedirs(assets_dir, mode=0o700, exist_ok=True)
```

For each logo with a URL (not already a local path):

```python
# Primary logo
if "url" in draft["logos"].get("primary", {}):
    url = draft["logos"]["primary"]["url"]
    ext = Path(urlparse(url).path).suffix or ".png"
    dest = f"{assets_dir}/logo-primary{ext}"
    urllib.request.urlretrieve(url, dest)
    draft["logos"]["primary"]["local_path"] = dest

# Favicon
if "url" in draft["logos"].get("favicon", {}):
    url = draft["logos"]["favicon"]["url"]
    ext = Path(urlparse(url).path).suffix or ".ico"
    dest = f"{assets_dir}/favicon{ext}"
    urllib.request.urlretrieve(url, dest)
    draft["logos"]["favicon"]["local_path"] = dest
```

On download failure: warn (`"Logo download failed: <error>. URL preserved in config; local copy unavailable."`) and set `local_path` to `None`. Do not abort the save.

After download, re-run `LogoValidator.validate_logo(dest)` and append results to the validation summary.

---

## Step 4c — Construct config.yaml via `build_config_from_draft`

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

`fonts.*` is **not** emitted in v2. The loader's `_normalize_branding_v2_to_return_shape` derives the legacy `fonts.{header,body,monospace}` keys from `typography.{h1,body-md,code}.fontFamily` at read time, so downstream consumers continue to see the legacy fonts keys regardless of on-disk schema version. The full `load_client_branding()` return shape is 14 keys on every path (the four v2 token-tree keys — `typography`, `rounded`, `spacing`, `components` — plus the `render` defaults key are populated as empty dicts on v1 and error paths so consumers can read them unconditionally).

Legacy v1 fallback (only when a downstream skill or migration explicitly passes `schema_version=1`):

```python
config = build_config_from_draft(draft, schema_version=1, validation_summary=validation_results)
# Emits the old shape: colors.accent / colors.background / colors.text + fonts.{header,body,monospace}
```

Compute `config_hash = sha256(yaml.safe_dump(config["branding"], sort_keys=True).encode()).hexdigest()`.

---

## Step 4d — Archive existing config (if present)

```python
import shutil

existing = os.path.expanduser("~/.parallax/client-branding/config.yaml")
if os.path.exists(existing):
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = os.path.expanduser(f"~/.parallax/client-branding/.archive/{ts}")
    os.makedirs(archive_dir, mode=0o700, exist_ok=True)
    shutil.copy2(existing, f"{archive_dir}/config.yaml")
```

Archive failures are non-blocking — log a warning but do not abort.

---

## Step 4e — Staging write + atomic-swap

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

On write failure: report `"Save failed: <file> write error. No files written. Safe to retry."` Do not proceed to Step 4e' or Step 4f.

---

## Step 4e' — Write DESIGN.md (Google Labs spec)

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

---

## Step 4f — Append hash-chained audit entry

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

---

## Regenerate-from-config — Python block

For the `--regenerate-design-md` operational mode. Validates required keys, reconstructs a synthetic draft via `_config_to_draft`, calls `emit_design_md`, writes atomically, appends audit entry.

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
