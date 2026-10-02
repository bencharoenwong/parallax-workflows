# Language style reference

Read only the relevant section. Source fidelity overrides style.

## Core Rules

### 1. Sentence Length

Arabic sentences with multiple coordinated clauses (chained with و) get hard to scan quickly in a scanning/skimming read, the way an institutional reader skims a report.

| Length | Action |
|--------|--------|
| ≤120 chars | OK |
| 120–160 chars | Split if multiple independent clauses |
| **>160 chars** | **MUST SPLIT** into 2–3 sentences |
| >220 chars | CRITICAL — split into 3+ sentences |

**Ideal:** 60–110 characters per sentence. (Thresholds are a draft estimate, not measured against real Arabic finance prose — confirm with a native reviewer before treating as final.)

### 2. Code-Switching — Keep These in English

The English identifiers below are product house style. Standard Arabic finance terms are valid; use a reviewed Arabic gloss when it helps the audience.

**Always English:** Tracking Error, Sector Rotation, Expected Shortfall, CVaR, VaR, Alpha, Beta, Gamma, Delta, Theta, Vega, Rho, Epsilon, Max Drawdown, Information Ratio, Sharpe Ratio, Sortino Ratio, Active Share, Hit Ratio, Effective Number of Holdings, Performance Attribution, Return Attribution, Overweight, Underweight, Bull case, Base case, Bear case

**All factor labels English:** Momentum, Tactical, Defensive, Value, Growth, Quality, Sentiment, Volatility

**All financial ratios English:** P/E, P/B, P/FCF, FCF, EV/EBITDA, ROE, ROA, ROIC, YTD, MTD, EPS, EBITDA

**Macro indicators English:** Economic Surprise Index, Initial Jobless Claims, ISM PMI, DXY, CPI, FOMC, NFP, PCE

**Proprietary factor and score labels English:** keep any composite-score labels, factor scores, or sub-factor identifiers in English with their numeric values (e.g., "Factor +0.40", "Score -0.18"). Do not translate label text; never alter sign or magnitude.

**Company names:** Always English/Latin script for non-Saudi listings. Never translate suffixes (Holdings, Corp, Inc, Ltd, Group). For Tadawul-listed companies, use the company's official Arabic name where one is published by Tadawul or the company itself (e.g., مصرف الراجحي, أرامكو السعودية) — confirm the exact registered form against Tadawul's own listing before using any example name from this file, this skill's own examples are drafts too; if no official Arabic name is published, keep the English/Latin name.

### 3. Terminology Consistency

Pick ONE Arabic form per concept and use it throughout the document. This table is a draft seed — confirm every row with a native reviewer before treating it as fixed:

- **Portfolio:** المحفظة (preferred) — never mix with الحافظة الاستثمارية
- **Sector:** القطاع — keep consistent; do not alternate with الصناعة for the same concept
- **Benchmark:** المؤشر المرجعي
- **Metric/Indicator:** المؤشر (note: same root as "index" — context must disambiguate; if ambiguity risk is high, keep "Metric" in English)
- **Volatility:** التقلب
- **Allocation:** التخصيص
- **Contribution (performance attribution sense):** المساهمة

See `references/terminology-corrections.md` for the seed find→replace table.

### 4. CRITICAL Factual Error Guards

| Term | Meaning | Context |
|------|---------|---------|
| **ECL** (Expected Credit Loss) | Expected credit losses on financial assets and credit commitments under IFRS 9 | Banking/Accounting |
| **ES** (Expected Shortfall) | Average loss beyond VaR (= CVaR) | Portfolio Risk |
| **Zakat** | Islamic religious levy on qualifying Saudi/GCC entities, distinct from corporate income tax | Saudi-specific financial statements |
| **CMA** (Capital Market Authority) vs **SAMA** (Saudi Central Bank) | Two different regulators — CMA governs Tadawul/securities, SAMA governs banking; the Insurance Authority (IA / هيئة التأمين) governs insurance | Never conflate |

In CIO/portfolio reports, "Expected Shortfall" is a risk metric, not a credit-loss provision — translating it as an ECL term is a factual error a Saudi risk analyst will catch immediately. Zakat and corporate tax are separate line items in Saudi financial statements; do not merge them into one translated line.

### 5. Right-to-Left (RTL) and Bidirectional (Bidi) Handling

This is the section with no Thai/Chinese equivalent — Arabic is the first RTL target this repo has shipped.

- **Base direction is RTL.** Arabic prose flows right to left. Numbers, tickers, and embedded English terms stay left-to-right internally, but the run as a whole sits inside the RTL flow — do not manually reverse digit order or Latin-letter order.
- **Never manually reverse text** to "fix" apparent ordering. Garbled-looking mixed RTL/LTR text in a terminal or plain-text preview is often a rendering artifact of the *viewer*, not a translation error — verify in an actual RTL-aware renderer before concluding the source text is wrong.
- **Numerals:** use Western digits (0–9), not Eastern Arabic-Indic digits (٠١٢٣...), for all financial figures, unless the target document is explicitly using Eastern Arabic-Indic numerals elsewhere (uncommon in Gulf institutional finance, but confirm — this is a draft default, not a confirmed convention).
- **Currency:** SAR amounts — confirm placement (symbol/code before or after the number) with a native reviewer; do not guess. Draft default: keep `SAR` as the code before the number (`SAR 41.22`), matching the Latin-code convention used for other currencies in this pipeline (see Currency Format below).
- **Punctuation:** Arabic uses its own comma (،) and question mark (؟) in Arabic-only prose; keep standard `.` `,` `%` `$` `()` inside numbers, tickers, and English terms embedded in the Arabic sentence.
- **HTML/bidi markup (CIO pipeline only):** when the output is HTML, wrap embedded LTR runs (tickers, English terms, numbers where the surrounding markup requires it) in `<span dir="ltr">...</span>` or use Unicode bidi isolate characters (U+2066 LRI / U+2069 PDI) rather than the deprecated embedding/override characters (LRE/RLE/PDF), to prevent the run from visually reordering inside RTL paragraph flow. This is a draft rule pending a real RTL rendering test — see `references/INTEGRATION.md`.

### 6. Section Headers and Style

**Section headers MUST be in Arabic.** Strategy names on title pages MUST be in Arabic where an established Arabic name exists; otherwise keep the English name rather than inventing one.

- Concise, direct, front-load conclusions, then explain — matches the register used by Argaam/Mubasher institutional coverage.
- Avoid literal Western idiom translation ("navigate the market," "headwinds") — state the business fact directly.
- Remove hedging phrasing (يبدو أن...) unless the source genuinely hedges.

### 7. Stock Ratings

Draft seed table — confirm exact Tadawul-market convention with a native reviewer before treating as final:

- STRONG BUY = شراء قوي
- BUY = شراء
- HOLD = احتفاظ
- SELL = بيع
- STRONG SELL = بيع قوي

Translating rating labels does not change distribution posture. Retail distribution may require a locally licensed distributor and locally approved disclosures; see the "Choosing a mode (jurisdiction and audience)" section of `parallax-white-label-stock-report/SKILL.md`. `register: retail` changes linguistic register only; it does not authorize retail distribution.

### 8. Currency Format

- Currency code stays in English/Latin script: `SAR`, `USD`, `AED`, `KWD`. Preserve the source currency for each amount. SAR can legitimately appear in an analysis of a non-Saudi issuer.
- Draft default: code precedes the number (`SAR 41.22`) — confirm against real Saudi finance publications before treating as fixed (see Section 5).
- Numerals: Western digits (see Section 5).

### 9. Dates

- Gregorian dates are standard in institutional finance documents; Hijri dates may appear alongside them in some Saudi regulatory or Zakat-related contexts. Draft default: keep Gregorian only unless the source document explicitly carries a Hijri date, in which case preserve both — confirm this convention with a native reviewer.
- Numeric dates (DD/MM/YYYY) pass through unchanged, same as the Thai/Chinese skills.

### 10. Common AI Errors — Auto-Fix

This list is a placeholder. The Thai and Chinese equivalents (see their the Common AI Errors section in this reference) were built from real observed model errors in corrected output; no equivalent corpus exists yet for Arabic. Known general categories to watch for once real samples arrive:

- Hamza spelling variants (ء / أ / إ / آ / ؤ / ئ) used inconsistently for the same word.
- Confusion between ة (ta marbuta) and ه (ha) at word endings.
- Confusion between ى (alef maksura) and ي (ya) at word endings.
- Doubled consecutive words (same failure mode as Thai/Chinese — check for it, no Arabic-specific examples yet).
- HTML entity corruption (`&lt;`, `&gt;`, `&amp;`, `&quot;`).

Populate this table with real find→fix pairs once native-reviewed samples exist — see "Open decisions" below.

---

## Open decisions (resolve before treating this skill as production-ready)

1. **MSA vs. dialect confirmation** — confirm with the native reviewer that MSA-with-Saudi-conventions, not colloquial Najdi/Gulf dialect, is the right register for every document type this skill will be asked to translate.
2. **Numeral style** (Section 5) — Western vs. Eastern Arabic-Indic digits.
3. **Currency placement** (Section 5/8) — code before or after the number.
4. **Date convention** (Section 9) — Gregorian-only vs. Gregorian+Hijri.
5. **Stock rating terms** (Section 7) — confirm against real Tadawul-market usage.
6. **RTL/bidi rendering** (Section 5) — needs an actual rendering test in the target HTML pipeline before the isolate-character guidance is trusted.
7. **Terminology and common-error tables** — need 3–5 real sample translations, corrected by a native Saudi finance reviewer, to replace the drafted seed content in `references/dictionaries.md`, `references/terminology-corrections.md`, and `references/validate-translation.py`'s wrong-terms dictionary.

---

## Retail Register (optional)

Apply this section only when the routing block specifies `register: retail`; otherwise use the institutional register above. Retail register is still Modern Standard Arabic — never colloquial dialect.

- Factor labels and risk metrics stay English but receive a one-time plain-Arabic descriptive gloss on first use. The gloss must be descriptive, never transliterated; if no natural gloss exists, keep English alone.
- Rating labels render dual-label on every occurrence, e.g. `شراء (Buy)`.
- Unchanged in retail: the terminology-consistency table, the factual-error guards, RTL/bidi rules, sentence-length limits, currency rules, and validator applicability.

Translating or dual-labeling ratings does not change distribution posture. Retail distribution may require a locally licensed distributor and locally approved disclosures; see the "Choosing a mode (jurisdiction and audience)" section of `parallax-white-label-stock-report/SKILL.md`. `register: retail` changes linguistic register only; it does not authorize retail distribution.
