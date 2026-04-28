---
name: translate-thai-finance
description: Translate financial content (stock reports, CIO reports, macro reports) to Thai with correct code-switching, terminology, and natural phrasing. Use when translating text to Thai for institutional finance audiences.
user-invocable: true
---

# Thai Financial Translation Skill

Translate provided content into Thai following institutional finance translation rules. Thai finance professionals heavily code-switch between Thai and English — respect this convention.

**Output formats:**
- **CIO reports** → HTML via checkpoint pipeline (see `references/cio-report-format.md`)
- **Stock reports, macro reports** → JSON (see JSON Output Format below)
- **General content** → Plain Thai text

**NOT for:** General Thai translation without finance context, transliteration of brand names, creative writing in Thai, proofreading existing Thai translations, or writing Thai reports from scratch.

---

## Core Rules

### 1. Sentence Length (Thai has no word spaces — long sentences are unreadable)

| Length | Action |
|--------|--------|
| ≤100 chars | OK |
| 100-130 chars | Split if multiple clauses |
| **>130 chars** | **MUST SPLIT** into 2-3 sentences |
| >180 chars | CRITICAL — split into 3+ sentences |

**Ideal:** 50-80 characters per sentence.

### 2. Code-Switching — Keep These in English

Thai analysts use these English terms directly. Translating them sounds machine-generated.

**Always English:** Tracking Error, Sector Rotation, Expected Shortfall, CVaR, VaR, Alpha, Beta, Gamma, Delta, Theta, Vega, Rho, Epsilon, Max Drawdown, Information Ratio, Sharpe Ratio, Sortino Ratio, Active Share, Hit Ratio, Effective Number of Holdings, Performance Attribution, Return Attribution, Overweight, Underweight, Bull case, Base case, Bear case

**All factor labels English:** Momentum, Tactical, Defensive, Value, Growth, Quality, Sentiment, Volatility

**All financial ratios English:** P/E, P/B, P/FCF, FCF, EV/EBITDA, ROE, ROA, ROIC, YTD, MTD, EPS, EBITDA

**Macro indicators English:** Economic Surprise Index, Initial Jobless Claims, ISM PMI, DXY, CPI, FOMC, NFP, PCE

**Proprietary factor and score labels English:** keep any composite-score labels, factor scores, or sub-factor identifiers in English with their numeric values (e.g., "Factor +0.40", "Score -0.18"). Do not translate label text; never alter sign or magnitude.

**Company names:** Always English. Never translate suffixes (Holdings, Corp, Inc, Ltd, Group).

### 3. Terminology Consistency

Pick ONE form per concept and use it throughout the document:
- **Portfolio:** พอร์ต (preferred) — never mix with พอร์ตโฟลิโอ or พอร์ตการลงทุน
- **Sector:** use English "Sector" — never mix ภาคธุรกิจ, กลุ่มอุตสาหกรรม, สายอุตสาหกรรม
- **Benchmark:** ดัชนีอ้างอิง (NOT เกณฑ์อ้างอิง)
- **Metric/Indicator:** ตัวชี้วัด (NOT เมตริก)
- **Volatility:** ความผันผวน (full form, not ความผวน)
- **Allocation:** การจัดสรร (not การจัดพอร์ต)
- **Contribution:** การมีส่วนช่วย (not การมีส่วนสนับสนุน)

See `references/terminology-corrections.md` for the full find→replace table.

### 4. CRITICAL Factual Error Guard: ECL vs Expected Shortfall

| Term | Meaning | Context |
|------|---------|---------|
| **ECL** (Expected Credit Loss) | Loan loss provisions under IFRS 9 | Banking/Accounting |
| **ES** (Expected Shortfall) | Average loss beyond VaR (= CVaR) | Portfolio Risk |

In CIO/portfolio reports, "Expected Shortfall" is a risk metric. Translating it as ECL or ผลขาดทุนด้านเครดิต is a **factual error** Thai risk analysts will immediately catch.

### 5. Spacing Rules

- **Always space between Thai and English:** `ปัจจัยMomentum` → `ปัจจัย Momentum`
- **Space after company names:** `Xiaomiเป็น` → `Xiaomi เป็น`
- **No space before Sara Am:** `ก ำไร` → `กำไร`
- **No space before repeat mark:** `บาง ๆ` → `บางๆ`

### 6. No Awkward Thai Prefix + English Combos

**Self-check:** After translating, search for the regex pattern `การ [A-Z]` in output. Any match is likely wrong — rephrase using "จุดยืน [term]" (for positioning), "[term] ใน..." (for actions), or full Thai equivalent. Exception: Thai compound words ending in การ followed by a proper noun (e.g., "ผู้ว่าการ Macklem") are correct — การ is part of the preceding word, not a standalone prefix.

| Wrong | Correct (English) | Correct (Full Thai) |
|-------|-------------------|---------------------|
| การ Overweight | Overweight กลุ่มเทค | น้ำหนักเกินในกลุ่มเทค |
| การ Underweight | Underweight กลุ่มพลังงาน | น้ำหนักต่ำกว่าในกลุ่มพลังงาน |
| การ Rebalance | Rebalance พอร์ต | ปรับสมดุลพอร์ต |
| การ Outperform | Outperform ดัชนี | ผลตอบแทนเหนือดัชนี |

### 7. Writing Style (CIO/Institutional Reports)

**Never use colloquial/transliterated terms:**

| Wrong | Correct |
|-------|---------|
| ไฮไลท์ / ไฮไลต์ | ประเด็นสำคัญ or จุดเด่น |
| พังทลาย | ร่วงลง or ปรับลดลง |
| ชนะ (beating benchmark) | สูงกว่า, เหนือกว่า |
| นำทัพ | นำโดย, โดย...เป็นหลัก |
| ดูเหมือนจะ | Remove hedging — be direct |

**Section headers MUST be in Thai.** Strategy names on title pages MUST be in Thai.

### 8. Stock Ratings

- STRONG BUY = ซื้อสะสม (NOT ซื้อเข้ม, ซื้อเชิงรุก)
- BUY = ซื้อ
- HOLD = ถือ
- SELL = ขาย
- STRONG SELL = ขายออก (NOT ขายเชิงรุก)

### 9. Currency Format

- Symbol always IN FRONT: HKD 41.22 (NOT 41.22 HKD)
- Use: พันล้านดอลลาร์, ล้านดอลลาร์ (not พันล้านเหรียญสหรัฐ)
- Remove ฯ after full words: ดอลลาร์สหรัฐ (not ดอลลาร์สหรัฐฯ)
- **Match currency to market:** HK stocks → HKD, US stocks → USD, China → RMB (never บาท for non-Thai stocks)

### 10. Common AI Errors — Auto-Fix

| Error | Fix |
|-------|-----|
| ราราคา | ราคา |
| คาดว่าว่า | คาดว่า |
| ที่ที่ | ที่ |
| จะจะ | จะ |
| และและ | และ |
| การเสถียรภาพ | เสถียรภาพ |
| สมารท์โฟน | สมาร์ทโฟน |
| พันธบัตร์ | พันธบัตร |
| ไทหวัน | ไต้หวัน |
| ทักษิด ชินวัตร | ทักษิณ ชินวัตร |

Also fix: doubled consecutive words, HTML entity corruption (&lt; &gt; &amp; &quot;), extra spaces in mid-sentence.

---

## Quality Checklist (Before Finalization)

- [ ] All code-switching terms kept in English (see Section 2)
- [ ] No doubled consecutive words
- [ ] Spaces around all English terms embedded in Thai
- [ ] Consistent terminology throughout (portfolio, sector, volatility, allocation, contribution)
- [ ] No ECL/ES confusion
- [ ] No sentences >130 Thai characters
- [ ] No truncated/incomplete text
- [ ] Data values match across all mentions
- [ ] No awkward การ + English combos
- [ ] Currency matches market (no บาท for non-Thai stocks)

---

## JSON Output Format (Stock Reports, Macro Reports)

Translate text sections only. Pass through data fields unchanged.

**Input** (flat keys — typical Parallax macro report):
```json
{"market": "Canada", "date": "...", "MarketNewsDevText": "...", "TacticalAllocationTable": [...], "charts": [...]}
```

**Output** (nested with metadata):
```json
{
  "metadata": {
    "market": "<from input>",
    "report_date": "<from input date>",
    "source_file": "<input filename>",
    "translation_language": "Thai",
    "translation_date": "<today YYYY-MM-DD>",
    "original_language": "English"
  },
  "sections": {
    "MarketNewsDevText": {
      "original_key": "MarketNewsDevText",
      "thai_translation": "..."
    }
  }
}
```

**Rules:**
- Translate all keys ending in `Text` (MarketNewsDevText, FactorText, SectorPositioningText, etc.)
- Pass through tables, charts, liquidity_metrics, and metadata fields unchanged (omit from output or include as-is)
- Preserve `\n` paragraph breaks from the original
- After writing the JSON, run `references/validate-translation.py` to check quality

---

## Reference Files

| File | Contents |
|------|----------|
| `references/terminology-corrections.md` | Full find→replace tables: wrong Thai → correct English/Thai, risk metrics, financial terms, technical analysis, macro terms |
| `references/dictionaries.md` | Country names, months, section header translations, strategy name translations |
| `references/cio-report-format.md` | CIO report pipeline, checkpoint script usage, footer standardization, table header conventions |
| `references/structural-preservation.md` | What NOT to translate: JSON escaping, HTML tags, tickers/RICs, template variables, numbers, URLs, footnotes, disclosure blocks, HTML entity handling |
| `references/validate-translation.py` | Post-translation quality validator — checks doubled words, wrong terms, ECL/ES confusion, spacing, currency mismatches. Run: `python3 references/validate-translation.py <output.json>` |

---

## Condensed Prompt for LLM API / OpenRouter Usage

```
Translate to Thai following these rules:
1. RATINGS: Strong Buy=ซื้อสะสม, Buy=ซื้อ, Hold=ถือ, Sell=ขาย, Strong Sell=ขายออก
2. SCENARIOS: Keep English - Bull case, Base case, Bear case
3. COMPANY NAMES: Keep all in English, never translate suffixes
4. FINANCIAL RATIOS: Keep English (P/E, P/B, ROE, ROA, ROIC, YTD, EPS, EBITDA)
5. CURRENCY: พันล้านดอลลาร์ (not พันล้านเหรียญสหรัฐ), symbol before number
6. SPACING: Always space between English and Thai
7. NATURAL THAI: Front-load conclusions, avoid overly formal/literal translations
8. FIX DUPLICATES: ราราคา→ราคา, คาดว่าว่า→คาดว่า
9. CODE-SWITCHING: Keep English: Tracking Error, Sector Rotation, Expected Shortfall, CVaR, VaR, Alpha, Beta, Max Drawdown, Sharpe Ratio, Active Share, Hit Ratio, all factor labels
10. TERMINOLOGY CONSISTENCY: Use พอร์ต (not mixed). Use Sector in English (not mixed Thai forms)
11. ECL vs ES: ECL=banking (IFRS 9). Expected Shortfall=portfolio risk. NEVER confuse them.
12. SENTENCE LENGTH: >130 chars MUST split. Ideal: 50-80 chars. Thai has no word spaces.
13. NO HALLUCINATED TERMS: If no standard Thai equivalent exists, keep the English term.
```
