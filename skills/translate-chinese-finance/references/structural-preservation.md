# Structural Preservation Rules

Elements that must pass through translation unchanged. Corrupting any of these breaks downstream parsing or rendering. Identical between Simplified and Traditional output.

---

## 1. JSON String Escaping

Translation operates on string values inside JSON. Never corrupt the JSON structure itself.

- **JSON keys** — never translate. `"MarketNewsDevText"`, `"Momentum"`, `"factors"`, `"period"` are code.
- **Escape sequences** — `\"`, `\n`, `\\`, `\t` must survive. Never produce unescaped `"` inside a JSON string value.
- **Curly braces** — `{` and `}` in JSON structure are never touched. Only translate text content inside `"chinese_translation": "..."`.
- **Null/boolean/numeric values** — `null`, `true`, `false`, numbers pass through literally. Don't wrap in quotes or translate.
- **Validate output** — after writing, the JSON must parse cleanly: `python3 -c "import json; json.load(open('file.json'))"`.

---

## 2. HTML Tag Passthrough (CIO Reports)

CIO reports are HTML. Translate text content between tags only.

**Never translate:**
- Tags: `<div>`, `<span>`, `<table>`, `<tr>`, `<td>`, `<th>`, `<br>`, `<p>`, `<h1>`–`<h6>`, `<img>`, `<a>`
- Attributes: `class="..."`, `id="..."`, `style="..."`, `href="..."`, `src="..."`
- Inline CSS: `font-size: 14px`, `color: #333`, `text-align: center`
- Comments: `<!-- ... -->`

**Do translate:**
- Text content between tags: `<td>Market Trends</td>` → `<td>市场趋势</td>`
- Alt text of images (if present): `alt="Factor chart"` → `alt="因子图表"`

**Common error:** Translating `class="sector-header"` to `class="板块标题"` — this breaks CSS. Never touch attribute values.

---

## 3. Template and Placeholder Variables

Pass through literally. These are substituted programmatically after translation.

| Pattern | Example | Action |
|---------|---------|--------|
| `{VARIABLE}` | `{REPORT_NUMBER}`, `{DATE}` | Pass through |
| `{{variable}}` | `{{market_name}}` | Pass through |
| `%s`, `%d`, `%f` | `收益 %s%%` | Pass through |
| `{0}`, `{1}` | Positional format strings | Pass through |
| `${...}` | JS template literals | Pass through |

---

## 4. Ticker Symbols, RICs, and Index Names

Never translate, transliterate, split, or reformat:

- **Tickers:** `AAPL`, `MSFT`, `0700.HK`, `005930.KS`, `2330.TW`, `600519.SS`
- **RICs:** `AAPL.O`, `BHP.AX`, `1299.HK`, `2330.TWO`
- **Index names:** `S&P 500`, `TSX`, `KOSPI`, `Hang Seng`, `恒生指数` (acceptable for HK reports), `SSE Composite`, `MSCI World`
- **Exchange codes:** `NYSE`, `NASDAQ`, `HKEX`, `SGX`, `TWSE`
- **Benchmark tickers:** `^GSPC`, `^IXIC`, `XBB.TO`

**Gotcha:** `S&P 500` contains `&` — don't encode to `&amp;` in plain text, but do in HTML context.

---

## 5. Numeric Data Integrity

Copy all numbers exactly. Don't round, reformat, or convert units (except where SKILL.md §4 explicitly requires `B → 亿` magnitude conversion, in which case multiply correctly).

| Type | Example | Rule |
|------|---------|------|
| Percentages | `2.7%`, `+0.40`, `-3.1%` | Exact digits, keep sign |
| Basis points | `275 bps`, `+74.2 bps` | Keep "bps" in English |
| Currency amounts | `C$51.3 billion`, `USD 41.22`, `HKD 41.22` | Exact amount, translate unit word only |
| Dates (ISO) | `2026-03-26`, `Q2 2026` | Pass through as-is |
| Index levels | `1,462.23`, `49.37` | Exact digits including commas |
| Ratios/scores | `Factor +0.40`, `Z-score -0.701` | Keep label English, exact number |
| Ranges | `1.35–1.39`, `50.0%–100.0%` | Keep both endpoints exact |

**Never:** Round `51.3` to `51`, change `2.25%` to `2.3%`. Never silently substitute `B` for `亿` without the ×10 multiplier (see SKILL.md §4).

---

## 6. URLs, Email Addresses, File Paths

Pass through untouched:

- `https://...` — never translate any part
- `mailto:...` — never translate
- File paths: `/output/chinese/zh-CN/final/` — never translate
- API endpoints: never translate

---

## 7. Markdown Formatting

When input contains markdown, preserve formatting markers:

- **Bold:** `**text**` → `**文本**` (translate inside, keep markers)
- **Italic:** `*text*` → `*文本*`
- **Links:** `[text](url)` → `[文本](url)` (translate link text, keep URL)
- **Line breaks:** `\n` paragraph breaks → preserve exactly
- **Lists:** `- item` or `1. item` → keep markers, translate text
- **Headers:** `## Section` → `## 部分` (keep `##`, translate text)

---

## 8. Footnote and Superscript Markers

Pass through without moving or translating:

- Superscript numbers: `¹`, `²`, `³`
- Asterisk footnotes: `*`, `**`, `†`, `‡`
- Bracketed refs: `[1]`, `[2]`
- HTML footnotes: `<sup>1</sup>` — keep tag structure

**Position rule:** If a footnote marker appears at the end of a sentence in English, place it at the end of the corresponding Chinese sentence. Don't move it to mid-sentence.

---

## 9. Disclosure and No-Translate Blocks

Respect translation boundary markers:

- `<!-- DO NOT TRANSLATE -->` ... `<!-- END NO TRANSLATE -->` — pass through entire block
- `<!-- DISCLOSURE -->` blocks — translate content but keep all HTML structure
- Legal entity names in disclaimers: "Chicago Global Capital Pte Ltd" — keep in English
- License/registration numbers — pass through exactly

---

## 10. HTML Entity Handling

| Context | Input | Correct Output | Wrong Output |
|---------|-------|---------------|--------------|
| Plain text (JSON) | `S&P 500` | `S&P 500` | `S&amp;P 500` |
| HTML content | `S&amp;P 500` | `S&amp;P 500` | `S&P 500` (would break HTML) |
| HTML display | `&lt;table&gt;` | `&lt;table&gt;` (if intentional) | `<table>` (would create element) |
| JSON inside HTML | `\"value\"` | `\"value\"` | `"value"` (breaks JSON) |

**Rule:** Match the encoding of the input. If the source uses `&amp;`, keep `&amp;`. Don't decode or double-encode.

---

## 11. Script Consistency (Simplified vs Traditional)

After translation, run a script-purity check:
- For zh-CN output: scan for any character in the Traditional set (`與 為 國 對 發 開 關 這 進 還 過 時 會 經 業 報 場 動 價 務 淨 證 險 負 資 產 權 潤 據`). Convert via `references/terminology-corrections.md` §2.
- For zh-TW output: scan for the Simplified equivalents and convert in reverse.

A document with mixed scripts will read as obviously machine-translated to a Chinese reader.

---

## Quick Checklist (Run After Translation)

- [ ] JSON parses without error
- [ ] All `{`, `}` balanced and in correct positions
- [ ] No unescaped `"` inside string values
- [ ] `\n` breaks preserved (same paragraph count as source)
- [ ] All ticker symbols/RICs unchanged
- [ ] All numbers match source exactly (and any `B`/`亿` conversion is mathematically correct)
- [ ] No HTML tags translated or corrupted
- [ ] No `class=` or `style=` attributes modified
- [ ] Template variables (`{VAR}`, `{{var}}`) intact
- [ ] HTML entities match input encoding
- [ ] Script (Simplified or Traditional) is uniform throughout the document
