# White-Label Branding Validation Rules

Reference guide for color, logo, and font validation in the white-label onboarding skill.

## Colors

### Extraction

Colors are extracted from:
- **CSS**: `font-family` declarations, hex color values in stylesheets
- **HTML**: inline `style` attributes, data attributes
- **Design files**: color specifications in hex, RGB, or named formats
- **PDFs**: OCR text containing color references

Colors are normalized to **6-digit hex format** (#RRGGBB) during extraction.

### Validation Rules

| Check | Pass Criteria | Warn Criteria | Fail Criteria | Recommendation |
|---|---|---|---|---|
| **Hex Validity** | Valid 6-digit or 3-digit hex | — | Invalid format, wrong length, non-hex chars | Ensure format matches #RRGGBB or #RGB |
| **WCAG AA Contrast (text on background)** | Ratio ≥ 4.5:1 | Ratio 3.0–4.5:1 | Ratio < 3.0:1 | If text contrast fails, suggest lighter/darker variant via algorithm |
| **RGB Range** | All channels 0–255 | — | Out of range | Clamp to valid range |

### WCAG Contrast Calculation

The contrast ratio is calculated using the **WCAG 2.0 formula**:

1. **Relative luminance** for each color:
   ```
   For each channel (R, G, B):
     if value ≤ 0.04045:
       channel_linear = value / 12.92
     else:
       channel_linear = ((value + 0.055) / 1.055) ^ 2.4
   
   L = 0.2126 × R_linear + 0.7152 × G_linear + 0.0722 × B_linear
   ```

2. **Contrast ratio**:
   ```
   ratio = (L_lighter + 0.05) / (L_darker + 0.05)
   ```

3. **Interpretation**:
   - Ratio ≥ 4.5:1 → Pass (AA compliance for body text)
   - Ratio 3.0–4.5:1 → Warn (AA for large text, consider adjustment)
   - Ratio < 3.0:1 → Fail (insufficient contrast)

### Example: Primary Color Validation

**Input**: `#FF5733` (primary), `#F5F5F5` (background), text content

```
Primary #FF5733 on background #F5F5F5:
  L_primary = 0.21 (linear calculation)
  L_background = 0.97 (linear calculation)
  Contrast ratio = (0.97 + 0.05) / (0.21 + 0.05) = 4.12
  Status: WARN — ratio 4.12 is below 4.5:1
  Recommendation: Darken primary to #E63F1F or lighten background to #FFFFFF
```

---

## Logos

### Extraction

Logos are extracted from:
- **URLs**: markdown image syntax `![alt](url)`, bare URLs containing "logo" keyword
- **PDFs**: image regions detected via OCR + heuristics
- **Manual entry**: user-supplied paths or URLs during wizard mode

Confidence scoring:
- High (0.9): URL/path contains "logo", "brand", or "icon" keyword
- Medium (0.75): Image file extension present (.png, .svg, .jpg, .gif)
- Low (0.6): Generic image URL without branding keywords

### Validation Rules

| Check | Pass Criteria | Warn Criteria | Fail Criteria | Recommendation |
|---|---|---|---|---|
| **Format** | PNG, SVG, JPG, JPEG | GIF (may lose animation) | Unsupported (BMP, TIFF, etc.) | Convert to PNG or SVG |
| **Dimensions** | ≥ 200×200 px | < 200×200 px (pixelation risk) | — | Provide higher-resolution version |
| **File Size** | ≤ 5 MB | — | > 5 MB | Compress or reduce dimensions |
| **Transparency** | Note if present | — | — | Transparent PNGs/SVGs layer well on colored backgrounds |
| **Existence** | File found on disk or URL resolves | URL temporarily unreachable | 404/broken link | Verify path or update URL |

### Logo Dimension Check

Use **PIL/Pillow** to read image dimensions:

```python
from PIL import Image
from pathlib import Path

path = Path(logo_path)
if path.exists():
    with Image.open(path) as img:
        width, height = img.size
        if width < 200 or height < 200:
            warn(f"Logo {width}×{height} below recommended 200×200")
```

### Logo Format Support

| Format | Support | Notes |
|---|---|---|
| PNG | ✅ Preferred | Supports transparency, lossless |
| SVG | ✅ Preferred | Scales infinitely, smallest file size |
| JPG/JPEG | ✅ Supported | No transparency; ensure high quality |
| GIF | ⚠️ Warned | Animation lost in static PDF output |
| WebP | ❌ Not supported | Convert to PNG/JPG |
| BMP/TIFF | ❌ Not supported | Convert to PNG/JPG |

---

## Fonts

### Extraction

Fonts are extracted from:
- **CSS**: `font-family` declarations with selector context (header, body, code)
- **PDFs**: OCR of text with font-style cues (bold = header font, mono = code font)
- **Manual entry**: user-supplied font names during wizard mode

Font usage categorization:
- **Header**: h1, h2, h3, h4, h5, h6, heading selectors
- **Body**: body, p, text, default selectors
- **Monospace**: pre, code, kbd, var, monospace selectors

### Validation Rules

| Check | Pass Criteria | Warn Criteria | Fail Criteria | Recommendation |
|---|---|---|---|---|
| **System Availability** | Font installed on system | Not installed | — | Suggest web-safe fallback (see Supported Fonts) |
| **Web-Safe** | Yes (system + web fonts) | Non-standard (requires import) | — | Include @font-face URL or fallback chain |
| **Fallback Chain** | Serif → Georgia, Sans-serif → Helvetica, Mono → Courier | — | — | Ensure fallback font specified |

### Font Detection via Matplotlib

Check system-installed fonts using matplotlib:

```python
import matplotlib.font_manager as fm

def get_system_fonts() -> set[str]:
    """List all fonts installed on the system."""
    font_list = fm.findSystemFonts()
    font_names = set()
    for font_path in font_list:
        try:
            prop = fm.FontProperties(fname=font_path)
            font_names.add(prop.get_name())
        except Exception:
            pass
    return font_names

if "Inter" in get_system_fonts():
    status = "available"
else:
    status = "not installed; use Helvetica as fallback"
```

### Font Confidence Scoring

| Source | Confidence |
|---|---|
| Explicit CSS `font-family` declaration | 0.95 |
| PDF OCR text mentioning font name | 0.70 |
| User manual entry (wizard) | 1.00 |
| Heuristic detection (header styling) | 0.60 |

---

## Validation Workflow in Skills

Downstream skills (`/parallax-client-review`, etc.) **always** call `load_client_branding()` to load saved branding. The loader never raises exceptions — all validation failures are logged but result in graceful degradation:

```python
from skills._parallax.white_label.loader import load_client_branding

branding = load_client_branding()

if branding["error"]:
    logger.warning("Client branding degraded: %s", branding["error"])
    # Use whatever is available (partial colors, missing logos, etc.)

# Apply branding to PDF generation
pdf_builder.set_primary_color(branding["colors"].get("primary", "#000000"))
pdf_builder.set_logo(branding["logos"].get("primary", None))  # None = skip logo
```

Warnings never block PDF generation — the output is always produced, with or without custom branding.
