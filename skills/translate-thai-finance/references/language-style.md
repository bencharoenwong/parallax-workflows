# Language style reference

Read only the relevant section. Source fidelity overrides style.

## Core Rules

### 1. Sentence Length (Thai has no word spaces — long sentences are unreadable)

| Length | Action |
|--------|--------|
| ≤100 chars | OK |
| 100-130 chars | Split if multiple clauses |
| **>130 chars** | Review clause structure; split when natural without omitting content |
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
| **ECL** (Expected Credit Loss) | Expected credit losses on financial assets and credit commitments under IFRS 9 | Banking/Accounting |
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
| ดูเหมือนจะ | Preserve when the source expresses uncertainty; otherwise remove invented hedging |

**Section headers MUST be in Thai.** Strategy names on title pages MUST be in Thai.

### 8. Stock Ratings

- STRONG BUY = ซื้อสะสม (NOT ซื้อเข้ม, ซื้อเชิงรุก)
- BUY = ซื้อ
- HOLD = ถือ
- SELL = ขาย
- STRONG SELL = ขายออก (NOT ขายเชิงรุก)

Translating rating labels does not change distribution posture. Retail distribution may require a locally licensed distributor and locally approved disclosures; see the "Choosing a mode (jurisdiction and audience)" section of `parallax-white-label-stock-report/SKILL.md`. `register: retail` changes linguistic register only; it does not authorize retail distribution.

### 9. Currency Format

- Symbol always IN FRONT: HKD 41.22 (NOT 41.22 HKD)
- Use: พันล้านดอลลาร์, ล้านดอลลาร์ (not พันล้านเหรียญสหรัฐ)
- Remove ฯ after full words: ดอลลาร์สหรัฐ (not ดอลลาร์สหรัฐฯ)
- **Preserve source currency:** a listing market does not determine every currency in an analysis. Keep reporting, trading, and comparison currencies distinct.

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

## Retail Register (optional)

Apply this section only when the routing block specifies `register: retail`; otherwise use the institutional register above.

- Factor labels and risk metrics stay English but receive a one-time plain-Thai descriptive gloss on first use. The gloss must be descriptive, never transliterated; if no natural gloss exists, keep English alone.
- Rating labels render dual-label on every occurrence, e.g. `ซื้อ (Buy)`.
- Unchanged in retail: the terminology-consistency table, the ECL/ES guard, spacing rules, sentence-length limits, currency rules, and validator applicability.

Translating or dual-labeling ratings does not change distribution posture. Retail distribution may require a locally licensed distributor and locally approved disclosures; see the "Choosing a mode (jurisdiction and audience)" section of `parallax-white-label-stock-report/SKILL.md`. `register: retail` changes linguistic register only; it does not authorize retail distribution.
