# Structural Preservation Rules

Elements that must pass through translation unchanged. Corrupting any of these breaks downstream parsing or rendering. This file is the Arabic port of the Thai/Chinese equivalent — sections 1–9 are language-agnostic and carry over directly. Section 10 (RTL/bidi) is new to this skill.

---

## 1. JSON String Escaping

Translation operates on string values inside JSON. Never corrupt the JSON structure itself.

- **JSON keys** — never translate. `"MarketNewsDevText"`, `"Momentum"`, `"factors"`, `"period"` are code.
- **Escape sequences** — `\"`, `\n`, `\\`, `\t` must survive. Never produce unescaped `"` inside a JSON string value.
- **Curly braces** — `{` and `}` in JSON structure are never touched. Only translate text content inside `"arabic_translation": "..."`.
- **Null/boolean/numeric values** — `null`, `true`, `false`, numbers pass through literally. Don't wrap in quotes or translate.
- **Validate output** — after writing, the JSON must parse cleanly: `python3 -c "import json; json.load(open('file.json'))"`.

---

## 2. HTML Tag Passthrough (CIO Reports)

CIO reports are HTML. Translate text content between tags only.

**Never translate:**
- Tags: `<div>`, `<span>`, `<table>`, `<tr>`, `<td>`, `<th>`, `<br>`, `<p>`, `<h1>`–`<h6>`, `<img>`, `<a>`
- Attributes: `class="..."`, `id="..."`, `style="..."`, `href="..."`, `src="..."`, `dir="..."`
- Inline CSS: `font-size: 14px`, `color: #333`, `text-align: center`
- Comments: `<!-- ... -->`

**Do translate:**
- Text content between tags: `<td>Market Trends</td>` → `<td>اتجاهات السوق</td>`
- Alt text of images (if present): `alt="Factor chart"` → `alt="مخطط Factor"`

**Common error:** Translating `class="sector-header"` to an Arabic class name — this breaks CSS. Never touch attribute values, including `dir="rtl"` / `dir="ltr"` attributes (see Section 10 — these are structural, not content).

---

## 3. Template and Placeholder Variables

Pass through literally. These are substituted programmatically after translation.

| Pattern | Example | Action |
|---------|---------|--------|
| `{VARIABLE}` | `{REPORT_NUMBER}`, `{DATE}` | Pass through |
| `{{variable}}` | `{{market_name}}` | Pass through |
| `%s`, `%d`, `%f` | `العائد %s%%` | Pass through |
| `{0}`, `{1}` | Positional format strings | Pass through |
| `${...}` | JS template literals | Pass through |

---

## 4. Ticker Symbols, RICs, and Index Names

Never translate, transliterate, split, or reformat:

- **Tickers:** `AAPL`, `MSFT`, `2222.SE` (Tadawul RIC suffix), `1120.SE`
- **RICs:** `AAPL.O`, `2222.SE`
- **Index names:** `S&P 500`, `TASI` (Tadawul All Share Index), `MSCI World`, `Hang Seng`
- **Exchange codes:** `NYSE`, `NASDAQ`, `Tadawul`
- **Benchmark tickers:** `^GSPC`, `^TASI.SE`

**Gotcha:** `S&P 500` contains `&` — don't encode to `&amp;` in plain text, but do in HTML context. Ticker and RIC strings must render left-to-right even embedded in an RTL sentence — see Section 10.

---

## 5. Numeric Data Integrity

Copy all numbers exactly. Don't round, reformat, or convert units, and do not convert digit script (Western 0–9 vs Eastern Arabic-Indic ٠١٢٣) unless SKILL.md's open decision on numeral style has been resolved for this delivery.

| Type | Example | Rule |
|------|---------|------|
| Percentages | `2.7%`, `+0.40`, `-3.1%` | Exact digits, keep sign |
| Basis points | `275 bps`, `+74.2 bps` | Keep "bps" in English |
| Currency amounts | `SAR 41.22`, `USD 41.22` | Exact amount, translate unit word only if a unit word (not the currency code) is present |
| Dates (ISO) | `2026-03-26`, `Q2 2026` | Pass through as-is |
| Index levels | `1,462.23`, `49.37` | Exact digits including commas |
| Ratios/scores | `Factor +0.40`, `Z-score -0.701` | Keep label English, exact number |
| Ranges | `1.35–1.39`, `50.0%–100.0%` | Keep both endpoints exact |

**Never:** Round `51.3` to `51`, convert `SAR` to a different currency, change `2.25%` to `2.3%`, or silently switch digit script mid-document.

---

## 6. URLs, Email Addresses, File Paths

Pass through untouched:

- `https://...` — never translate any part
- `mailto:...` — never translate
- File paths — never translate
- API endpoints — never translate

---

## 7. Markdown Formatting

When input contains markdown, preserve formatting markers:

- **Bold:** `**text**` → `**نص**` (translate inside, keep markers)
- **Italic:** `*text*` → `*نص*`
- **Links:** `[text](url)` → `[نص](url)` (translate link text, keep URL)
- **Line breaks:** `\n` paragraph breaks → preserve exactly
- **Lists:** `- item` or `1. item` → keep markers, translate text
- **Headers:** `## Section` → `## قسم` (keep `##`, translate text)

---

## 8. Footnote and Superscript Markers

Pass through without moving or translating:

- Superscript numbers: `¹`, `²`, `³`
- Asterisk footnotes: `*`, `**`, `†`, `‡`
- Bracketed refs: `[1]`, `[2]`
- HTML footnotes: `<sup>1</sup>` — keep tag structure

**Position rule:** If a footnote marker appears at the end of a sentence in English, place it at the corresponding position in the Arabic sentence's visual flow, not literally re-appended at the string's end — RTL sentence-final position in the underlying character stream is not the same as visual-end position. Verify in a rendered preview when possible; when not possible, keep the marker adjacent to the same clause it followed in English.

---

## 9. Disclosure and No-Translate Blocks

Respect translation boundary markers:

- `<!-- DO NOT TRANSLATE -->` ... `<!-- END NO TRANSLATE -->` — pass through entire block
- `<!-- DISCLOSURE -->` blocks — translate content but keep all HTML structure
- Legal entity names in disclaimers: "Example Capital Ltd" — keep in English
- License/registration numbers (including CMA license numbers) — pass through exactly

---

## 10. Right-to-Left and Bidirectional (Bidi) Preservation — Arabic-specific

No Thai/Chinese equivalent needed this section; Arabic is the first RTL language this repo has shipped.

- **Base direction:** the document or containing element sets `dir="rtl"`. Never invert this per-paragraph to "fix" a rendering issue — fix the embedded-run isolation instead (below).
- **Embedded LTR runs inside RTL text:** tickers, RICs, English finance terms, currency codes, and numbers must render left-to-right internally while sitting inside the RTL paragraph flow. In HTML, wrap them in `<span dir="ltr">...</span>` where the surrounding context makes reordering likely (e.g., a ticker immediately followed by Arabic punctuation), or use Unicode bidi isolate characters (U+2066 LRI ... U+2069 PDI) in plain text. Do not use the deprecated LRE/RLE/PDF embedding characters.
- **Never manually reverse a string** to make it "look right" in a plain-text preview. A terminal, chat window, or plain-text editor without proper bidi support is a common source of apparent-but-false reordering — verify in an actual RTL-capable renderer (a browser, a properly configured terminal, or the target HTML pipeline) before concluding the underlying text is wrong.
- **Digit script:** see SKILL.md §5's open decision. Whichever digit script is chosen, do not mix Western and Eastern Arabic-Indic digits within the same document.
- **Table and layout mirroring (CIO HTML pipeline only):** table column order, alignment, and navigation elements should mirror for RTL rendering. This is pipeline/CSS work, not a translation-content rule — see `references/cio-report-format.md` and `references/INTEGRATION.md`.

---

## Quick Checklist (Run After Translation)

- [ ] JSON parses without error
- [ ] All `{`, `}` balanced and in correct positions
- [ ] No unescaped `"` inside string values
- [ ] `\n` breaks preserved (same paragraph count as source)
- [ ] All ticker symbols/RICs unchanged and render LTR
- [ ] All numbers match source exactly, digit script consistent throughout
- [ ] No HTML tags translated or corrupted, including `dir` attributes
- [ ] No `class=` or `style=` attributes modified
- [ ] Template variables (`{VAR}`, `{{var}}`) intact
- [ ] HTML entities match input encoding
- [ ] No manual string reversal anywhere in the pipeline
