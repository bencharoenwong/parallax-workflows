# White-Label Onboarding Skill

Enable Parallax clients to extract and integrate their brand assets (colors, logos, fonts) into analysis output PDFs, maintaining consistency across all client reports.

## Overview

The white-label onboarding skill provides a complete workflow for:

1. **Extraction** — Detect brand assets from flexible sources: website URLs, PDF documents, or manual entry via interactive wizard
2. **Validation** — Verify color contrast (WCAG AA compliance), logo dimensions, font availability, and confidence scoring
3. **Confirmation** — User-facing review and approval gate before saving
4. **Storage** — Save to a global, persistent location (`~/.parallax/client-branding/config.yaml`)
5. **Application** — Downstream skills automatically apply branding to all PDF outputs

## Features

- **Multi-source extraction**: URL scraping, PDF OCR, or manual wizard intake
- **Comprehensive validation**: WCAG contrast ratios, logo dimensions/formats, font fallback chains
- **Graceful degradation**: Partial branding accepted; missing assets don't block PDF generation
- **Global configuration**: Single source of truth at `~/.parallax/client-branding/` for all downstream skills
- **Audit logging**: Configuration version history, extraction confidence scores, validation warnings
- **Zero-overhead on success**: Silent logging for clean loads; detailed warnings only for issues

## Usage

### Quick Start

```bash
# Enter the white-label onboarding skill
/parallax-white-label-onboard
```

The skill will guide you through:
1. Selecting extraction method (URL, PDF, or wizard)
2. Reviewing extracted assets and confidence scores
3. Confirming your branding preferences
4. Automatic save to `~/.parallax/client-branding/config.yaml`

### For Downstream Skills

Any Parallax skill that generates PDF output automatically loads and applies client branding:

```python
from skills._parallax.white_label.loader import load_client_branding

branding = load_client_branding()

if branding["error"]:
    logger.warning("Client branding degraded: %s", branding["error"])

# Apply branding
pdf_builder.set_primary_color(branding["colors"].get("primary", "#000000"))
pdf_builder.set_logo(branding["logos"].get("primary", None))
pdf_builder.set_font(branding["fonts"].get("header", "Helvetica"))
```

## Architecture

### Components

- **`extract.py`** — Asset extraction from URLs (web scraping), PDFs (OCR), or wizard intake
  - `ColorExtractor` — Hex color and RGB pattern matching
  - `LogoExtractor` — URL and file path detection
  - `FontExtractor` — CSS font-family parsing and OCR text analysis
  - `extract_from_url()`, `extract_from_pdf()`, `extract_from_wizard()`

- **`validator.py`** — Validation rules and scoring
  - `ColorValidator` — Hex format, WCAG AA contrast checking (with gamma correction), RGB range
  - `LogoValidator` — Format (PNG/SVG/JPG), dimensions, file size, transparency detection
  - `FontValidator` — System availability via matplotlib, web-safe fallbacks

- **`loader.py`** — Configuration loading and graceful degradation
  - `load_client_branding()` — Main public API
  - Handles 4 failure modes: missing config, corrupt YAML, schema validation, missing logo files
  - Never raises exceptions; always returns 6-key result dict

- **`schema.yaml`** — JSON Schema for config validation

### Data Flow

```
URL/PDF/Wizard → Extract → Normalize → Validate → Confirm Gate → Save → ~/.parallax/client-branding/config.yaml
                                                                              ↓
                                                                   Downstream Skills ← Load → PDF with Branding
```

## File Structure

```
skills/white-label-onboard/
├── README.md (this file)
├── SKILL.md (orchestration / entry point)
├── INSTALLATION.md (setup instructions)
├── references/
│   ├── validation-rules.md (color/logo/font validation reference)
│   └── supported-fonts.md (web-safe fonts + fallback chains)
└── (Python modules in skills/_parallax/white-label/)
    ├── __init__.py
    ├── extract.py
    ├── validator.py
    ├── loader.py
    ├── schema.yaml
    └── tests/
        ├── conftest.py
        ├── test_extract.py
        ├── test_validator.py
        ├── test_loader.py
        └── test_integration.py
```

## Configuration

### Storage Location

Configuration is stored at `~/.parallax/client-branding/config.yaml`:

```yaml
metadata:
  schema_version: 1
  client_name: "Acme Capital"
  extracted_at: "2026-04-30T12:00:00Z"
  source:
    type: "url"  # or "pdf" or "wizard"
    reference: "https://acme.example.com"
    confidence: 0.95

branding:
  colors:
    primary: "#1A2B3C"
    secondary: "#FFFFFF"
    accent: "#FF6600"
    background: "#F5F5F5"
    text: "#333333"
  logos:
    primary: "~/.parallax/client-branding/assets/logo.png"
    favicon: "~/.parallax/client-branding/assets/favicon.ico"
  fonts:
    header: "Inter"
    body: "Roboto"
    monospace: "JetBrains Mono"

confidence_scores:
  color_primary: 0.99
  logo_primary: 0.85
  font_header: 0.95
```

### Permission Model

- Config file: `0600` (read/write by owner only)
- Assets directory: `0700` (owner-only access)
- Logo files: Resolved to absolute paths; missing files degrade gracefully

## Validation Rules

### Colors

- **Format**: 6-digit or 3-digit hex (`#RRGGBB`, `#RGB`)
- **Contrast**: WCAG AA compliance (≥4.5:1 for body text, ≥3:1 for large text)
- **Calculation**: Gamma-corrected relative luminance with threshold 0.04045

Reference: `skills/white-label-onboard/references/validation-rules.md`

### Logos

- **Formats**: PNG (preferred), SVG, JPG — lossless, transparency support
- **Dimensions**: ≥200×200 px (recommended)
- **File size**: ≤5 MB
- **Transparency**: Detected and preserved for PNG/SVG

Reference: `skills/white-label-onboard/references/validation-rules.md`

### Fonts

- **System availability**: Checked via matplotlib `FontManager`
- **Web-safe fallbacks**: Suggested if not installed
- **Categories**: header (h1–h6), body (p, text), monospace (code, pre)

Reference: `skills/white-label-onboard/references/supported-fonts.md`

## Testing

### Run All Tests

```bash
pytest skills/_parallax/white-label/tests/ -v
```

### Test Coverage

- **21 extraction tests** — Color/logo/font extraction from CSS, PDF text, HTML
- **21 validation tests** — Color contrast, logo dimensions, font availability, fallbacks
- **12 loader tests** — Config loading, error handling, graceful degradation, schema validation
- **6 integration tests** — End-to-end workflows: extract → validate → save → load cycles

All 67 tests pass with real assertions (no stubs).

## Error Handling

The loader never raises exceptions. All failures are logged with severity level and composed into the `error` field:

| Failure Mode | Error Field | Data Keys | Behavior |
|---|---|---|---|
| Missing config | `"config_not_found"` | All empty dicts | Silent onboarding (returns empty branding) |
| Corrupt YAML | `"yaml_parse_error: ..."` | All empty dicts | Config file syntax error — skip it |
| Schema validation | `"schema_invalid: ..."` | All empty dicts | Structure mismatch — wait for user correction |
| Missing logo files | `"logo_missing: primary path not found: ..."` | Colors/fonts intact, logos empty | Partial branding accepted; PDF generated without logo |
| Schema unavailable | `"schema_unavailable"` | Best-effort data loaded | Schema.yaml deleted (rare); validation skipped |

## Downstream Integration

All Parallax skills that generate PDFs automatically use this skill. No additional wiring required.

Example skills that use branding:
- `/parallax-client-review` — RM meeting report with client logo + colors
- `/parallax-due-diligence` — Company deep-dive PDF with header branding
- `/parallax-morning-brief` — Fund manager daily brief with header fonts

## Troubleshooting

### "Config not found" error

The config has never been saved. Run `/parallax-white-label-onboard` to onboard a client.

### "logo_missing: primary path not found"

The logo file path in config.yaml points to a missing file. Check:
1. Logo file exists at `~/.parallax/client-branding/assets/`
2. Path in config.yaml is correct (use tilde `~` for home directory)
3. File permissions allow read access

### "Schema validation failed"

Config.yaml structure doesn't match schema. Check:
1. Required fields are present: metadata, branding, confidence_scores
2. `metadata.schema_version` is an integer (not a string)
3. `source.confidence` is a number between 0.0 and 1.0

### Fonts not rendering in PDF

Check:
1. Font name is spelled correctly
2. Font is installed on rendering machine (check via system font list)
3. Fallback chain in config includes web-safe alternatives (see supported-fonts.md)

## Development

### Adding New Extractors

Extend `extract.py`:

```python
def extract_from_figma(figma_url: str) -> dict[str, Any]:
    """Extract branding from Figma design file."""
    # Fetch design tokens from Figma API
    # Parse colors, fonts, assets
    # Return standard config shape
    return {
        "colors": {...},
        "logos": {...},
        "fonts": {...},
        "source": {"type": "figma", "reference": figma_url, "confidence": ...},
        "extracted_at": ...,
        "confidence_scores": {...},
    }
```

### Adding New Validators

Extend `validator.py`:

```python
class AccessibilityValidator:
    @staticmethod
    def check_readability_score(colors: dict) -> dict:
        """Validate color readability for dyslexia, colorblindness, etc."""
        ...
```

## License & Attribution

White-label onboarding skill for Parallax equity research platform.
Part of the Chicago Global intelligence infrastructure.

## Support

For issues, questions, or feature requests:
- Check `INSTALLATION.md` for setup help
- Review `references/validation-rules.md` for validation details
- See `references/supported-fonts.md` for font recommendations
- Consult test files for usage examples
