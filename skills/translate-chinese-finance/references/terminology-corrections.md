# Terminology Corrections Reference

Find→replace tables for Chinese financial translation. Most are POST-TRANSLATION fixes — the LLM may produce wrong translations and this table corrects them. Each table notes whether it applies to Simplified, Traditional, or both.

---

## 1. Doubled-Character Auto-Fix (Both Scripts)

The LLM often duplicates a single-character function word.

| Wrong | Correct |
|-------|---------|
| 的的 | 的 |
| 了了 | 了 |
| 是是 | 是 |
| 和和 | 和 |
| 在在 | 在 |
| 有有 | 有 |
| 为为 / 為為 | 为 / 為 |
| 与与 / 與與 | 与 / 與 |
| 也也 | 也 |
| 都都 | 都 |
| 而而 | 而 |
| 但但 | 但 |
| 就就 | 就 |
| 不不 | 不 |

Same rule applies to ASCII words: doubled identical English tokens (`P/E P/E`, `the the`) should be deduplicated.

---

## 2. Stale-Conversion Character Fixes (Traditional → Simplified)

When a Traditional document is partially converted to Simplified but stragglers remain. Run as a final post-processor on Simplified output.

| Traditional (wrong in zh-CN) | Simplified (correct) |
|-------|---------|
| 與 | 与 |
| 為 | 为 |
| 國 | 国 |
| 對 | 对 |
| 發 | 发 |
| 開 | 开 |
| 關 | 关 |
| 這 | 这 |
| 進 | 进 |
| 還 | 还 |
| 過 | 过 |
| 時 | 时 |
| 會 | 会 |
| 經 | 经 |
| 業 | 业 |
| 報 | 报 |
| 場 | 场 |
| 動 | 动 |
| 價 | 价 |
| 務 | 务 |
| 淨 | 净 |
| 證 | 证 |
| 險 | 险 |
| 負 | 负 |
| 資 | 资 |
| 產 | 产 |
| 權 | 权 |
| 潤 | 润 |
| 據 | 据 |
| 從 | 从 |
| 個 | 个 |
| 們 | 们 |
| 來 | 来 |
| 學 | 学 |
| 體 | 体 |
| 點 | 点 |
| 種 | 种 |
| 樣 | 样 |
| 義 | 义 |
| 變 | 变 |
| 應 | 应 |
| 隨 | 随 |
| 處 | 处 |
| 優 | 优 |
| 寫 | 写 |
| 讀 | 读 |
| 強 | 强 |
| 銷 | 销 |
| 維 | 维 |
| 認 | 认 |
| 識 | 识 |
| 計 | 计 |

For Traditional output, run the reverse map.

---

## 3. Scenario Label Normalization (Both Scripts)

| Wrong (zh-CN) | Correct (zh-CN) |
|---------------|----------------|
| Bull / Bull Case / Bull case / Bull: | 乐观情景 |
| 牛市情景 / 牛市 | 乐观情景 |
| Base / Base Case / Base case / Base: | 基准情景 |
| 基础情景 | 基准情景 |
| Bear / Bear Case / Bear case / Bear: | 悲观情景 |
| 熊市情景 / 熊市 | 悲观情景 |

| Wrong (zh-TW) | Correct (zh-TW) |
|---------------|----------------|
| Bull / Bull Case | 樂觀情境 |
| 牛市情境 / 牛市 | 樂觀情境 |
| Base / Base Case | 基準情境 |
| 基礎情境 | 基準情境 |
| Bear / Bear Case | 悲觀情境 |
| 熊市情境 / 熊市 | 悲觀情境 |

---

## 4. Western Companies — Should Stay English

| Wrong (transliterated) | Correct |
|----|---------|
| 苹果 (when not 苹果公司 in retail context) | Apple |
| 辉达 / 英伟达 | NVIDIA |
| 特斯拉 (in equity report) | Tesla |
| 微软 (in equity report) | Microsoft |
| 谷歌 (in equity report) | Google / Alphabet |
| 亚马逊 (in equity report) | Amazon |
| 脸书 / 元宇宙 (when meaning Meta) | Meta |
| 网飞 | Netflix |

(In macro/news commentary the transliterated form may be acceptable. In equity research, keep English.)

For HK/TW/CN-listed companies, the Chinese name IS the official name — keep it.

---

## 5. Hallucinated / Awkward Compound Translations

| Wrong | Correct (Simplified) | Notes |
|-------|----------------------|-------|
| 评分分析的分析 | 评分分析 | Doubled clause |
| 财务报表表 | 财务报表 | Trailing duplicate char |
| 估值估值 | 估值 | |
| 盈利能力能力 | 盈利能力 | |
| 现金流流量 | 现金流量 or 现金流 | |

**Hallucination check (cell-keyword consensus):** when a translated table cell would contain BOTH `负债` AND `权益`, the canonical label is `负债与权益` (or `负债及股东权益`). When it contains BOTH `商誉` AND `无形资产`, it should be `无形资产与商誉`. Force these canonical forms.

---

## 6. Ratings — Local-Firm Variants to Avoid

The Parallax pipeline uses mainland-style ratings consistently across both scripts (`超配/低配/標配/跑贏大盤/跑輸大盤`). Some Taiwan securities firms locally prefer the alternatives below, but those are NOT the canonical Parallax forms.

| Local-firm variant (avoid in pipeline output) | Parallax canonical (zh-CN) | Parallax canonical (zh-TW) |
|------------------------------------------------|----------------------------|----------------------------|
| 优于大盘 / 優於大盤 | 跑赢大盘 | 跑贏大盤 |
| 落后大盘 / 落後大盤 | 跑输大盘 | 跑輸大盤 |
| 加码 / 加碼 | 超配 | 超配 |
| 减码 / 減碼 | 低配 | 低配 |
| 中立 (when meaning Equal Weight) | 标配 | 標配 |

---

## 7. CIO Report Term Corrections

| Wrong (zh-CN) | Correct (zh-CN) | Notes |
|---------------|----------------|-------|
| 最大缩水 | Max Drawdown / 最大回撤 | "缩水" sounds colloquial |
| 最大下跌 | Max Drawdown / 最大回撤 | Means generic decline, not drawdown |
| 跟踪误差率 | Tracking Error | Keep English in mainland reports |
| 信息比率 (ambiguous) | Information Ratio | Keep English to avoid CPI-related confusion |
| 阿尔法系数 | Alpha | |
| 贝塔系数 (in main text) | Beta | OK in glossaries; in narrative use English |
| 夏普值 | Sharpe Ratio | |
| 风险价值 (where context = ES) | Expected Shortfall | ES, not VaR |
| 条件风险价值 (in main text) | CVaR | Keep English in main text |

---

## 8. Risk Metrics

| English | zh-CN preferred | zh-TW preferred |
|---------|----------------|-----------------|
| Active Risk | 主动风险 | 主動風險 |
| Active Management | 主动管理 | 主動管理 |
| Active Return | 主动收益 | 主動報酬 |
| Passive Investment | 被动投资 | 被動投資 |
| Tail Risk | 尾部风险 | 尾部風險 |
| VaR | VaR (风险价值 on first use) | VaR (風險價值 on first use) |
| Expected Shortfall | Expected Shortfall (预期损失 on first use) | Expected Shortfall (預期損失 on first use) |
| Max Drawdown | Max Drawdown (最大回撤 on first use) | Max Drawdown (最大回撤 on first use) |

---

## 9. Financial Terms — Wrong Forms to Avoid

| English | Correct (zh-CN) | Wrong (zh-CN) |
|---------|----------------|--------------|
| Recurring revenue | 经常性收入 | 循环收入 / 重复收入 |
| Operating leverage | 经营杠杆 | 运营杠杆效应 (overly literal) |
| Resilience | 韧性 | 弹性 (means elasticity, different concept) |
| Margin expansion | 利润率扩张 | 利润扩张 (drops the margin word) |
| Sector headwinds | 行业逆风 | 板块阻力 (wrong register) |
| Concentration | 集中度 | 拥挤度 |
| Diversification | 分散投资 | 多元化 (acceptable but less specific) |
| Interest rate trajectory | 利率走势 | 利率轨迹 (overly literal) |
| Limited upside | 上行空间有限 | 增长上限 |
| Premium (pricing) | 溢价 | 额外费用 |
| Fundamental misunderstanding | 市场对基本面认识不足 | 基本面误解 |
| Momentum slowdown | 动量放缓 | 动力下降 |

---

## 10. Technical Analysis Terms

| English | zh-CN | zh-TW |
|---------|-------|-------|
| Support | 支撑 / 支撑位 | 支撐 |
| Resistance | 阻力 / 阻力位 | 壓力 / 阻力 |
| Breakout | 突破 | 突破 |
| Overbought | 超买 / overbought | 超買 |
| Oversold | 超卖 / oversold | 超賣 |
| Moving Average | 移动平均线 | 移動平均線 |
| Bollinger Bands | 布林带 | 布林通道 |
| RSI | RSI (相对强弱指标) | RSI (相對強弱指標) |
| MACD | MACD | MACD |
| MACD crossover | MACD交叉 | MACD交叉 |
| Bullish signal | 看涨信号 | 看漲訊號 |
| Bearish signal | 看跌信号 | 看跌訊號 |

---

## 11. Macro Indicators

| English | zh-CN | zh-TW |
|---------|-------|-------|
| GDP | GDP (国内生产总值 first use) | GDP (國內生產毛額 first use) |
| CPI | CPI (消费者物价指数 first use) | CPI (消費者物價指數 first use) |
| PPI | PPI (生产者物价指数 first use) | PPI (生產者物價指數 first use) |
| PMI | PMI (采购经理人指数 first use) | PMI (採購經理人指數 first use) |
| Fed | 美联储 | 聯準會 |
| FOMC | 联邦公开市场委员会 / FOMC | 聯邦公開市場委員會 / FOMC |
| Interest Rate | 利率 | 利率 |
| Inflation | 通胀 | 通膨 |
| Unemployment Rate | 失业率 | 失業率 |
| Non-Farm Payrolls | 非农就业 / NFP | 非農就業 / NFP |
| Yield Curve | 收益率曲线 | 殖利率曲線 |
| Economic Surprise Index | Economic Surprise Index | Economic Surprise Index |
| Initial Jobless Claims | Initial Jobless Claims | Initial Jobless Claims |

---

## 12. Footnote Conciseness (Institutional Audience)

Mainland and TW analysts know CAPM. Don't over-explain.

- **Alpha footnote:** `Alpha：经风险调整后的超额收益，衡量超越市场的能力。` (No CAPM formula needed.)
- **Beta footnote:** `Beta：系统性市场风险，衡量相对市场的波动性。`
- **Sharpe Ratio footnote:** `Sharpe Ratio：每单位总风险的超额收益。`

For Traditional, swap to `經風險調整`, `衡量`, `波動性`, `每單位總風險的超額收益` etc.
