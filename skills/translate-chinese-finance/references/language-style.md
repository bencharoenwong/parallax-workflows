# Language style reference

Read only the relevant section. Source fidelity overrides style.

## Core Rules

### 1. First-Occurrence Rule for Financial Abbreviations (Mainland Convention)

Mainland Chinese analysts use English abbreviations directly. Translating them sounds machine-generated, but a parenthetical Chinese gloss on first use aids the reader.

| Position | Format | Example |
|----------|--------|---------|
| First use in document | `ENGLISH (中文)` | `P/E (市盈率) of 15.2x`, `ROE (净资产收益率) reached 12%` |
| Subsequent uses | `ENGLISH only` | `...the company's P/E of 18.5x reflects...` |

**Always English (with optional first-use Chinese gloss):** P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/Revenue, ROE, ROA, ROIC, EPS, EBITDA, Sharpe Ratio, Information Ratio, Tracking Error, Max Drawdown, Beta, Alpha, Active Share, Hit Ratio.

**English identifiers; a retail gloss is optional:** ETF, REIT, GDP, CPI, PMI, CIO, CEO, CFO, ESG, IPO, M&A, AUM, AI, ML, IoT, 5G, Cloud, EV, AR, VR, SaaS, API, YTD, MTD, QoQ, YoY.

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

**Keep source numerical notation and magnitude units unchanged.** `365.91B CNY` stays `365.91B CNY`; never replace `B` with `亿/億`. A requested conversion requires a separate deterministic conversion and a reconciled source; it is outside this translation pass. Dates may translate month words, but preserve every numeric token.

**Dates:**
- `29 September 2025` → `2025年九月29日` (word format — convert)
- `Q1 2024` → `2024年第1季度`
- `06/12/2025` (DD/MM/YYYY numeric) → keep as-is. A deterministic post-processor handles numeric dates.

**Currency:**
- Codes stay in English: `USD`, `HKD`, `CNY`, `RMB`, `TWD`, `JPY`, `KRW`, `SGD`.
- Words can be Chinese: `人民币`, `港元`, `美元`, `新台币`, `日元`, `韩元`, `新加坡元`.
- Preserve the source currency for each amount. Listing, reporting, and comparison currencies can differ.

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

Translating rating labels does not change distribution posture. Retail distribution may require a locally licensed distributor and locally approved disclosures; see the "Choosing a mode (jurisdiction and audience)" section of `parallax-white-label-stock-report/SKILL.md`. `register: retail` changes linguistic register only; it does not authorize retail distribution.

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

### 10. Chinese Locales

For zh-HK use `references/locale-hk.md`; shared Traditional script does not imply Taiwan vocabulary.

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

Review unexpected script against the selected locale and source. Use context-aware conversion; never apply a reverse character map. See `references/terminology-corrections.md` for the full table.

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

## Retail Register (optional)

Apply this section only when the routing block specifies `register: retail`; otherwise use the institutional register above.

- Glossable financial abbreviations from Section 1's "always English with optional first-use Chinese gloss" list render Chinese-led on first use: `中文 (ENGLISH)`. After first use, use Chinese-only where a standard Chinese form exists.
- Section 1's "always English, no gloss needed" list, tickers, codes, and indexes stay English.
- Proprietary factor labels stay English but receive a one-time plain-Chinese parenthetical gloss.
- Rating labels render dual-label on every occurrence, e.g. `买入 (Buy)` / `買入 (Buy)`.
- Unchanged in retail: script consistency, punctuation rules, magnitude discipline, sentence-length limits, company-name rules, and validator applicability.

Translating or dual-labeling ratings does not change distribution posture. Retail distribution may require a locally licensed distributor and locally approved disclosures; see the "Choosing a mode (jurisdiction and audience)" section of `parallax-white-label-stock-report/SKILL.md`. `register: retail` changes linguistic register only; it does not authorize retail distribution.
