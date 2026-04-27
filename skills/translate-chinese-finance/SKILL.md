---
name: translate-chinese-finance
description: Translate financial content (stock reports, CIO reports, macro reports) to Chinese — Simplified (zh-CN) or Traditional (zh-TW/zh-HK) — with correct code-switching, terminology, and natural phrasing. Use when translating text to Chinese for institutional finance audiences.
user-invocable: true
---

# Chinese Financial Translation Skill

Translate provided content into Chinese following institutional finance translation rules. Mainland Chinese securities analysts code-switch English abbreviations into otherwise Chinese prose; Hong Kong / Taiwan analysts use Traditional script with their own terminology conventions. Respect both.

**Variants supported:**
- **Simplified (zh-CN)** — mainland China conventions. Default.
- **Traditional (zh-TW)** — Taiwan conventions.
- **Traditional (zh-HK)** — Hong Kong conventions (largely shares zh-TW script; some terminology differs, esp. for HK-listed companies).

Pick the variant from the user's request. If unspecified for a Greater-China stock report, default to Simplified for SSE/SZSE listings, Traditional for TWSE, and ask for HK listings (HK reports often go out in Simplified for mainland readers but can be Traditional).

**Output formats:**
- **CIO reports** → HTML via checkpoint pipeline (see `references/cio-report-format.md`)
- **Stock reports, macro reports** → JSON (see JSON Output Format below)
- **General content** → Plain Chinese text

**NOT for:** General Chinese translation without finance context, transliteration of Western brand names (keep them in English), creative writing in Chinese, proofreading existing Chinese translations, or writing Chinese reports from scratch.

---

## Core Rules

### 1. First-Occurrence Rule for Financial Abbreviations (Mainland Convention)

Mainland Chinese analysts use English abbreviations directly. Translating them sounds machine-generated, but a parenthetical Chinese gloss on first use aids the reader.

| Position | Format | Example |
|----------|--------|---------|
| First use in paragraph | `ENGLISH (中文)` | `P/E (市盈率) of 15.2x`, `ROE (股本回报率) reached 12%` |
| Subsequent uses | `ENGLISH only` | `...the company's P/E of 18.5x reflects...` |

**Always English (with optional first-use Chinese gloss):** P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/Revenue, ROE, ROA, ROIC, EPS, EBITDA, Sharpe Ratio, Information Ratio, Tracking Error, Max Drawdown, Beta, Alpha, Active Share, Hit Ratio.

**Always English, no gloss needed:** ETF, REIT, GDP, CPI, PMI, CIO, CEO, CFO, ESG, IPO, M&A, AUM, AI, ML, IoT, 5G, Cloud, EV, AR, VR, SaaS, API, YTD, MTD, QoQ, YoY.

**Stock codes / tickers / indexes:** always English (`0700.HK`, `AAPL.O`, `S&P 500`, `MSCI`, `TOPIX`, `Hang Seng`).

### 2. Company Names

| Listing | Treatment |
|---------|-----------|
| HK / TW / China-listed (`.HK`, `.TW`, `.SS`, `.SZ`) | Use OFFICIAL Chinese name. Full first mention (`腾讯控股有限公司`); short form afterwards (`腾讯`). |
| Other Asian listings (Japan, Korea, India, etc.) | Use widely-used Chinese name if established (e.g., `软银集团`, `三星电子`). If none, keep English. |
| US / EU / Western | **Keep in English.** Do NOT transliterate to `苹果`, `辉达`, `特斯拉`. Use `Apple`, `NVIDIA`, `Tesla`. |

**Sources for official Chinese names** (priority order):
1. Company's own Chinese-language website / IR filings
2. Exchange filings (HKEX, TWSE, SSE, SZSE, etc.)
3. Wikipedia (zh.wikipedia.org)
4. Baidu Baike (baike.baidu.com)
5. Bloomberg / Reuters / major Chinese financial press

If no widely-used Chinese name exists, KEEP ENGLISH. Do not invent one.

### 3. Sentence Length and Punctuation

Chinese has no word spaces but uses full-width punctuation as visual breakpoints. Long sentences are still hard to scan.

| Length | Action |
|--------|--------|
| ≤80 chars | OK |
| 80-120 chars | Split if multiple clauses |
| **>120 chars** | **MUST SPLIT** into 2-3 sentences |
| >180 chars | CRITICAL — split into 3+ sentences |

**Punctuation:**
- Full-width for Chinese text: `，。；：「」（）` (Traditional) or `，。；：""''（）` (Simplified — usually curly quotes)
- Half-width for numbers, English, and percentages: `. , % $ ()`
- Never mix full-width punctuation around English-only content.

### 4. Numbers, Dates, Currency — Magnitude Discipline

**Critical: Chinese uses 亿 (10⁸) and 万亿 (10¹²), not "billion / trillion."** Mixing systems silently breaks magnitudes by 10×.

| English | Chinese (correct) | Wrong |
|---------|-------------------|-------|
| 1 billion CNY | `10亿人民币` (multiply by 10) | `1亿人民币` |
| 365.91 billion CNY | `3,659.1亿人民币` (multiply 365.91 by 10) | `365.91亿人民币` |
| 100 million CNY | `1亿人民币` or `100百万人民币` | |
| 1 trillion CNY | `1万亿人民币` or `10000亿人民币` | |

**Safest rule:** keep the English unit unchanged (`365.91B CNY` stays `365.91B CNY`). Only convert if you do the math.

**Dates:**
- `29 September 2025` → `2025年9月29日` (word format — convert)
- `Q1 2024` → `2024年第一季度`
- `06/12/2025` (DD/MM/YYYY numeric) → keep as-is. A deterministic post-processor handles numeric dates.

**Currency:**
- Codes stay in English: `USD`, `HKD`, `CNY`, `RMB`, `TWD`, `JPY`, `KRW`, `SGD`.
- Words can be Chinese: `人民币`, `港元`, `美元`, `新台币`, `日元`, `韩元`, `新加坡元`.
- Match currency to market: HK stocks → HKD, US stocks → USD, China A-shares → CNY/RMB, Taiwan → TWD. Never substitute one for another.

**Percentages and basic numbers:** keep EXACTLY as shown (`35%`, `1.5x`, `12,345`).

### 5. Stock Ratings

Parallax pipeline uses mainland-style ratings across both scripts (do NOT substitute Taiwan-firm `加碼/減碼/中立/優於大盤` even in zh-TW output):

| English | Simplified | Traditional |
|---------|------------|-------------|
| STRONG BUY | 强力买入 | 強力買入 |
| BUY | 买入 | 買入 |
| HOLD | 持有 | 持有 |
| SELL | 卖出 | 賣出 |
| STRONG SELL | 强力卖出 | 強力賣出 |
| Outperform | 跑赢大盘 | 跑贏大盤 |
| Underperform | 跑输大盘 | 跑輸大盤 |
| Neutral | 中性 | 中性 |
| Overweight | 超配 | 超配 |
| Underweight | 低配 | 低配 |
| Equal Weight | 标配 | 標配 |
| Accumulate | 增持 | 增持 |
| Reduce | 减持 | 減持 |

### 6. Scenario Labels — Use These Exact Terms

| English | Simplified | Traditional |
|---------|------------|-------------|
| Bull / Bull Case | 乐观情景 | 樂觀情境 |
| Base / Base Case | 基准情景 | 基準情境 |
| Bear / Bear Case | 悲观情景 | 悲觀情境 |

**zh-CN do NOT use:** `牛市情景`, `熊市情景`, `基础情景`. **zh-TW do NOT use:** `牛市情境`, `熊市情境`, `基礎情境`. The mainland uses `情景`, Taiwan uses `情境` — never mix.

### 7. Section Headers MUST Be Chinese

Strategy names on title pages MUST be in Chinese. See `references/dictionaries.md` for the standard header translations.

### 8. Style — Institutional Securities-Firm Voice

- Concise, direct, front-load conclusions, then explain.
- Avoid Western cultural references (Greek/Roman myths, chess, alchemy, Western metaphors). Describe directly.
- Avoid translationese: literal "embrace" / "harvest" / "navigate the market." State business facts cleanly.
- Avoid colloquial / transliterated terms: prefer `亮点` over `高光`, `强劲` over `霸气`.
- Remove hedging adverbs (`似乎`, `看起来`) unless the source genuinely hedges.

### 9. Spacing Rules

- Space between Chinese and English: `投资P/E` → `投资 P/E`
- Space between Chinese and numbers when numbers are standalone metrics: `市盈率15倍` → `市盈率 15 倍`
- No space inside Chinese punctuation: `他说，` not `他说 ，`
- No space between Chinese characters (obviously) — flag any that appear; usually a tokenizer artifact.

### 10. Simplified vs Traditional — Don't Mix

**Mainland Simplified (zh-CN):**
- Script: 简体中文 — `与`, `为`, `国`, `这`, `时`, `会`, `经`, `业`, `资`, `产`, `证`, `负`, `净`
- Conventions: `软件`, `信息`, `数据库`, `视频`, `网络`, `服务器`, `用户`

**Traditional Taiwan (zh-TW):**
- Script: 繁體中文 — `與`, `為`, `國`, `這`, `時`, `會`, `經`, `業`, `資`, `產`, `證`, `負`, `淨`
- Conventions: `軟體`, `資訊`, `資料庫`, `影片`, `網路`, `伺服器`, `使用者`

**Traditional Hong Kong (zh-HK):**
- Script: same Traditional characters as TW
- Conventions: closer to mainland for finance terms but TW for general tech (`軟件` is often used in HK; Taiwan uses `軟體`)
- For HK-listed financials, follow HKEX disclosure conventions.

**Common stale-conversion artifacts** (when Traditional bleeds into a Simplified document, or vice versa):
- 與 ↔ 与, 為 ↔ 为, 國 ↔ 国, 對 ↔ 对, 發 ↔ 发, 開 ↔ 开, 關 ↔ 关, 這 ↔ 这, 進 ↔ 进, 還 ↔ 还, 過 ↔ 过, 時 ↔ 时, 會 ↔ 会, 經 ↔ 经, 業 ↔ 业, 報 ↔ 报, 場 ↔ 场, 動 ↔ 动, 價 ↔ 价, 務 ↔ 务, 淨 ↔ 净, 證 ↔ 证, 險 ↔ 险, 負 ↔ 负, 資 ↔ 资, 產 ↔ 产, 權 ↔ 权, 潤 ↔ 润, 據 ↔ 据.

After translation, search for any character of the wrong script and convert. See `references/terminology-corrections.md` for the full table.

### 11. Common AI Errors — Auto-Fix

| Error | Fix |
|-------|-----|
| `的的` | `的` |
| `了了` | `了` |
| `是是` | `是` |
| `和和` | `和` |
| `在在` | `在` |
| `有有` | `有` |
| `为为` | `为` |
| `与与` | `与` |

Also fix: doubled consecutive English words, HTML entity corruption (`&lt;`, `&gt;`, `&amp;`, `&quot;`), extra spaces in mid-sentence.

---

## Quality Checklist (Before Finalization)

- [ ] All code-switching abbreviations kept in English (P/E, ROE, EBITDA, etc.)
- [ ] First-use parenthetical Chinese gloss applied consistently
- [ ] No doubled characters (`的的`, `了了`, etc.)
- [ ] Spaces around all English terms embedded in Chinese
- [ ] No magnitude errors in `B`/`亿` conversions
- [ ] Currency matches market (no `人民币` for US stocks, no `港元` for A-shares)
- [ ] Script is consistently Simplified or Traditional throughout — no mixed
- [ ] No Western-cultural metaphors
- [ ] No sentences >120 Chinese characters without splitting
- [ ] Stock ratings use the exact terms in Section 5
- [ ] Section headers translated (see `references/dictionaries.md`)

---

## JSON Output Format (Stock Reports, Macro Reports)

Translate text sections only. Pass through data fields unchanged.

**Input** (flat keys — typical Parallax macro report):
```json
{"market": "China", "date": "...", "MarketNewsDevText": "...", "TacticalAllocationTable": [...], "charts": [...]}
```

**Output** (nested with metadata):
```json
{
  "metadata": {
    "market": "<from input>",
    "report_date": "<from input date>",
    "source_file": "<input filename>",
    "translation_language": "Chinese (Simplified)",
    "translation_locale": "zh-CN",
    "translation_date": "<today YYYY-MM-DD>",
    "original_language": "English"
  },
  "sections": {
    "MarketNewsDevText": {
      "original_key": "MarketNewsDevText",
      "chinese_translation": "..."
    }
  }
}
```

For Traditional output, set `translation_language` to `Chinese (Traditional)` and `translation_locale` to `zh-TW` or `zh-HK`.

**Rules:**
- Translate all keys ending in `Text` (`MarketNewsDevText`, `FactorText`, `SectorPositioningText`, etc.)
- Pass through tables, charts, liquidity_metrics, and metadata fields unchanged (omit from output or include as-is)
- Preserve `\n` paragraph breaks from the original
- After writing the JSON, run `references/validate-translation.py` to check quality

---

## Reference Files

| File | Contents |
|------|----------|
| `references/dictionaries.md` | Country names, months, section headers, sectors, exchanges, ratings, scenarios — Simplified and Traditional columns |
| `references/terminology-corrections.md` | Find→replace tables: wrong Chinese → correct English/Chinese; risk metrics; financial terms; technical terms; macro terms; stale-conversion character fixes |
| `references/structural-preservation.md` | What NOT to translate: JSON keys, HTML tags, tickers/RICs, template variables, numbers, URLs, footnotes, disclosure blocks, HTML entity handling |
| `references/cio-report-format.md` | CIO report pipeline, checkpoint script usage, footer standardization, table header conventions |
| `references/validate-translation.py` | Post-translation quality validator — checks doubled characters, wrong terms, magnitude errors, currency mismatches, mixed script. Run: `python3 references/validate-translation.py <output.json>` |
| `skill_simplified.md` (top level) | Self-contained zh-CN web-upload skill. Auto-generated from `chinese_translation_config.py`. Loaded by `references/load_skill.py` and consumed by the Parallax CIO/stock pipeline. Do not hand-edit. |
| `skill_traditional.md` (top level) | Self-contained zh-TW web-upload skill (hand-tuned canonical until a `chinese_translation_config_tw.py` exists). |
| `references/load_skill.py` | Python loader. Parses both top-level skill files into dicts/prompts. CLI smoke test: `python3 load_skill.py --locale zh-CN`. |
| `references/INTEGRATION.md` | Pipeline integration punch list — what scripts to fork from the Thai equivalents. |

---

## Condensed Prompt for LLM API / OpenRouter Usage

```
Translate to {Simplified|Traditional} Chinese following these rules:
1. RATINGS: Strong Buy=强力买入/強力買入, Buy=买入/買入, Hold=持有, Sell=卖出/賣出, Strong Sell=强力卖出/強力賣出
2. SCENARIOS (mainland): Bull=乐观情景, Base=基准情景, Bear=悲观情景. (Taiwan: 情境 acceptable instead of 情景.)
3. COMPANY NAMES: HK/TW/CN listings → official Chinese name (full first, short later). Western (US/EU) companies → keep English (Apple, NVIDIA, Tesla — never 苹果/辉达/特斯拉).
4. FINANCIAL ABBREVIATIONS: First use shows ENGLISH (中文); subsequent uses ENGLISH only. Applies to P/E, P/B, ROE, ROA, ROIC, EPS, EBITDA, EV/EBITDA, Sharpe Ratio, Tracking Error, Max Drawdown, Beta, Alpha.
5. KEEP ENGLISH ALWAYS: ETF, REIT, GDP, CPI, AI, ML, IoT, 5G, EV, SaaS, API, stock codes, indexes, YTD, MTD, QoQ, YoY.
6. NUMBERS: Keep percentages and counts exact. For magnitudes, do NOT substitute B→亿 without multiplying by 10. Safest: keep English unit (e.g., "365.91B CNY" stays as-is).
7. DATES: "29 September 2025" → "2025年9月29日". Numeric DD/MM/YYYY dates pass through.
8. CURRENCY: Codes English (USD, HKD, CNY). Words Chinese (人民币, 港元, 美元). Match currency to market.
9. PUNCTUATION: Full-width for Chinese (，。；：（）). Half-width for numbers/English/percent.
10. SCRIPT: Output ONE script (Simplified OR Traditional) consistently. Never mix 与/與 or 国/國 within the same document.
11. STYLE: Institutional, like a mainland securities-firm analyst (or HK/TW for Traditional). Front-load conclusions. No Western metaphors, no translationese.
12. FIX DUPLICATES: 的的→的, 了了→了, 是是→是, 和和→和, 在在→在.
13. SENTENCE LENGTH: >120 chars MUST split. Ideal: 50-80 chars per sentence.
14. NO HALLUCINATED TERMS: If no standard Chinese equivalent exists for a Western company / niche term, keep English.
```
