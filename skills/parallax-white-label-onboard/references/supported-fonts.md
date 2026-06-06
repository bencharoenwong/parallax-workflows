# Supported Fonts — Web-Safe Reference

Reference guide for font recommendations and fallback chains in white-label onboarding.

## Overview

Fonts are validated against two criteria:
1. **System availability** — installed locally on the rendering machine
2. **Web-safe fallback** — substitutes when the primary font is unavailable

This guide enumerates recommended fonts per category (header, body, monospace) with complete fallback chains.

---

## Header Fonts (h1–h6, headings)

Header fonts should convey hierarchy and brand presence. Modern sans-serifs are preferred for screen display.

| Font Name | Category | Availability | Notes |
|---|---|---|---|
| **Inter** | Sans-serif | System + web | Modern, highly legible, excellent metrics; preferred for Parallax clients |
| **Roboto** | Sans-serif | System + web | Geometric, professional; widely installed |
| **Helvetica** | Sans-serif | System + web | Classic fallback; universal availability |
| **Georgia** | Serif | System + web | Elegant serif option; high x-height for screens |
| **Times New Roman** | Serif | System + web | Universal serif fallback |
| **Segoe UI** | Sans-serif | System (Windows) + web | Windows native; modern proportions |
| **Trebuchet MS** | Sans-serif | System (Win/Mac) + web | Humanist sans; good for friendly brands |

### Recommended Fallback Chain — Header

**Primary web fonts first; system fallback last:**

```css
/* Option A: Sans-serif (recommended) */
font-family: Inter, Roboto, Helvetica, "Segoe UI", sans-serif;

/* Option B: Serif (for traditional brands) */
font-family: Georgia, "Times New Roman", serif;

/* Option C: Humanist (friendly/approachable) */
font-family: "Trebuchet MS", Helvetica, sans-serif;
```

**Loading strategy:**
- If `Inter` is installed locally → use it
- If `Inter` not available but in CDN/google-fonts → web-load it (slower, but matches brand)
- If neither → fall back to `Roboto` → `Helvetica` → system sans-serif

---

## Body Fonts (body, p, text, default)

Body fonts must maximize readability at smaller sizes. Balanced proportions and generous spacing are critical.

| Font Name | Category | Availability | Notes |
|---|---|---|---|
| **Inter** | Sans-serif | System + web | Excellent metrics for body text (11–16px); default recommendation |
| **Roboto** | Sans-serif | System + web | Proven in production; open-source (Apache 2.0) |
| **Segoe UI** | Sans-serif | System (Windows) + web | Windows standard; professional appearance |
| **Helvetica Neue** | Sans-serif | System (Mac) + web | macOS native; refined proportions |
| **Lucida Grande** | Sans-serif | System (Win/Mac) | Humanist proportions; excellent at small sizes |
| **Arial** | Sans-serif | System + web | Universal fallback; metrically similar to Helvetica |
| **Verdana** | Sans-serif | System + web | Optimized for screen; generous x-height |
| **Georgia** | Serif | System + web | Serif option; high readability on screens |

### Recommended Fallback Chain — Body

**Optimized for 12–16px reading sizes:**

```css
/* Option A: Modern sans-serif (recommended) */
font-family: Inter, Roboto, "Segoe UI", Helvetica, Arial, sans-serif;

/* Option B: Generous (accessible, especially for older readers) */
font-family: Verdana, "Lucida Grande", "Trebuchet MS", sans-serif;

/* Option C: Serif (traditional reports, whitepaper tone) */
font-family: Georgia, "Times New Roman", serif;
```

**Loading strategy:**
- Start with `Inter` (modern, refined)
- Fall back through `Roboto` → `Segoe UI` → system sans-serif
- For accessibility-focused clients, use `Verdana` + `Lucida Grande` (larger x-height)

---

## Monospace Fonts (pre, code, kbd, var)

Monospace fonts are used in code blocks, configuration examples, and technical documentation. Width uniformity is non-negotiable.

| Font Name | Category | Availability | Notes |
|---|---|---|---|
| **JetBrains Mono** | Monospace | System + web | Modern IDE font; excellent for code; open-source |
| **Fira Code** | Monospace | System + web | Programming font with ligatures; open-source (OFL) |
| **Consolas** | Monospace | System (Windows) + web | Windows native; widely used in VS Code |
| **Monaco** | Monospace | System (Mac) | macOS native; used in Terminal.app |
| **Courier New** | Monospace | System + web | Universal fallback; slightly narrow |
| **Courier** | Monospace | System + web | Serif monospace fallback |
| **Liberation Mono** | Monospace | System + web | Metrically compatible with Courier; open-source |

### Recommended Fallback Chain — Monospace

**Prioritize readability in technical contexts:**

```css
/* Option A: Modern programming font (recommended) */
font-family: "JetBrains Mono", "Fira Code", Consolas, Monaco, "Courier New", monospace;

/* Option B: Conservative (maximum compatibility) */
font-family: Consolas, "Courier New", Courier, monospace;

/* Option C: Humanist monospace */
font-family: "Fira Code", "Liberation Mono", monospace;
```

**Loading strategy:**
- Prefer `JetBrains Mono` or `Fira Code` (modern, designed for code)
- Fall back to `Consolas` (Windows) or `Monaco` (Mac) — platform-native
- Final fallback to `Courier New` (universal, but narrow)

---

## Font Loading & Performance

### Web Font Sources

When a font is not installed locally, load it via:

| Source | CDN | License | Notes |
|---|---|---|---|
| **Google Fonts** | fonts.googleapis.com | Open (mostly) | Largest free library; excellent performance |
| **Bunny Fonts** | fonts.bunny.net | Open | Privacy-focused; GDPR-compliant CDN |
| **Self-hosted** | Your CDN | Varies | Best performance; requires licensing verification |

### Loading Syntax (CSS @import)

```css
/* Google Fonts — Inter + Roboto */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Roboto:wght@400;500&display=swap');

/* Bunny Fonts — JetBrains Mono */
@import url('https://fonts.bunny.net/css?family=jetbrains-mono:400,600');

/* Self-hosted (if font files are in /assets/fonts/) */
@font-face {
  font-family: 'CustomFont';
  src: url('/assets/fonts/custom-font.woff2') format('woff2');
  font-weight: 400;
  font-display: swap;
}
```

### Performance Best Practice

Use `font-display: swap` to prevent invisible text during font load:
- Text renders immediately in fallback font
- Custom font swaps in when ready
- No "flash of invisible text" (FOIT)

---

## Validation & Extraction Rules

### Detection via Matplotlib

During white-label onboarding, fonts are detected from CSS declarations. Verify availability:

```python
import matplotlib.font_manager as fm

def font_available(font_name: str) -> bool:
    """Check if font is installed on system."""
    system_fonts = set()
    for font_path in fm.findSystemFonts():
        try:
            prop = fm.FontProperties(fname=font_path)
            system_fonts.add(prop.get_name())
        except Exception:
            pass
    return font_name in system_fonts

# Check if client's custom font exists
if not font_available("Custom Brand Font"):
    print("Font not installed; using fallback: Roboto")
```

### Extraction Confidence

Fonts are extracted with varying confidence scores:

| Source | Confidence | Treatment |
|---|---|---|
| Explicit CSS `font-family` declaration | 0.95 | High trust; use as primary |
| PDF OCR text (e.g., "uses Helvetica") | 0.70 | Moderate; confirm with client |
| User manual entry (wizard) | 1.00 | Highest trust; use as-is |
| Heuristic (selector context matching) | 0.60 | Low; use as suggestion only |

---

## Recommendations by Brand Type

### Tech / Startup Brands
- Header: **Inter** or **Roboto**
- Body: **Inter** or **Roboto**
- Monospace: **JetBrains Mono** or **Fira Code**
- Tone: Modern, clean, accessible

### Traditional / Professional Brands
- Header: **Helvetica** or **Georgia**
- Body: **Helvetica Neue** or **Georgia**
- Monospace: **Courier New** or **Liberation Mono**
- Tone: Established, trustworthy, formal

### Financial / Enterprise Brands
- Header: **Roboto** or **Segoe UI**
- Body: **Roboto** or **Verdana**
- Monospace: **Consolas** or **Courier New**
- Tone: Professional, data-driven, precise

### Accessibility-Focused Brands
- Header: **Inter** (excellent metrics)
- Body: **Verdana** (larger x-height, generous spacing)
- Monospace: **JetBrains Mono** or **Fira Code**
- Tone: Legible at all sizes; high contrast

---

## Migration & Fallback Strategy

### When a Brand Font Is Unavailable

If a client provides a custom font that cannot be installed system-wide:

1. **Check web availability** — Is the font available via Google Fonts, Bunny, or licensing CDN?
   - Yes → Load via CDN + swap fallback
   - No → Proceed to step 2

2. **Use primary fallback** — Apply the recommended fallback chain (e.g., `Inter` → `Roboto` → `Helvetica`)

3. **Log degradation** — Include in confidence_scores and warn the user:
   ```yaml
   confidence_scores:
     font_header: 0.0  # Custom font unavailable
     font_header_fallback: 0.85  # Using Roboto instead
   ```

4. **Document the substitution** — Store in audit log for transparency

---

## Updating This Guide

When new fonts are recommended or validated in production:

1. Add to the relevant category table
2. Update fallback chain recommendations if needed
3. Test availability via matplotlib (Section "Validation & Extraction Rules")
4. Re-review with design/brand team before committing
