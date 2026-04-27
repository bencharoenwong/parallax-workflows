# Traditional Chinese Translation Skill

Auto-generated from `chinese_translation_config.py` on 2026-04-27. This is the runtime data source for the Traditional Chinese translation pipeline. Edits here are loaded by `skill_loader.py` at script start.

**Format conventions:**
- `## NAME` heading marks each section.
- Markdown tables (English | Chinese) → simple string→string maps (no `|` in values).
- ` ```python ` code blocks → complex Python literals or dicts with special chars.
- ` ```text ` code blocks → multi-line strings (prompts).
- A `bool: True/False`, `int: <n>`, or `str: <value>` line → scalar.

---

## LANGUAGE_CODE

str: zh-TW

## LANGUAGE_NAME

str: Traditional Chinese

## LANGUAGE_SCRIPT

str: 繁體中文

## USE_BUDDHIST_ERA

bool: False

## YEAR_OFFSET

int: 0

## COUNTRY_MAP

| English | Chinese |
|---|---|
| Hong Kong | 香港 |
| China | 中國 |
| United States | 美國 |
| USA | 美國 |
| Japan | 日本 |
| South Korea | 韓國 |
| Korea | 韓國 |
| Taiwan | 台灣 |
| Singapore | 新加坡 |
| India | 印度 |
| United Kingdom | 英國 |
| UK | 英國 |
| Germany | 德國 |
| France | 法國 |
| Australia | 澳洲 |
| Canada | 加拿大 |
| Brazil | 巴西 |
| Indonesia | 印尼 |
| Malaysia | 馬來西亞 |
| Thailand | 泰國 |
| Vietnam | 越南 |
| Philippines | 菲律賓 |
| Switzerland | 瑞士 |
| Netherlands | 荷蘭 |
| Sweden | 瑞典 |
| Russia | 俄羅斯 |
| Saudi Arabia | 沙烏地阿拉伯 |
| UAE | 阿聯酋 |
| Israel | 以色列 |
| South Africa | 南非 |
| Mexico | 墨西哥 |
| New Zealand | 紐西蘭 |
| Spain | 西班牙 |
| Italy | 義大利 |

## MONTH_MAP

| English | Chinese |
|---|---|
| January | 一月 |
| February | 二月 |
| March | 三月 |
| April | 四月 |
| May | 五月 |
| June | 六月 |
| July | 七月 |
| August | 八月 |
| September | 九月 |
| October | 十月 |
| November | 十一月 |
| December | 十二月 |

## MONTHS_LIST

```python
[
    '一月',
    '二月',
    '三月',
    '四月',
    '五月',
    '六月',
    '七月',
    '八月',
    '九月',
    '十月',
    '十一月',
    '十二月',
]
```

## FISCAL_YEAR_FORMATS

| English | Chinese |
|---|---|
| fy_standard | 財年 |
| fy_short | 年 |

## CURRENCY_NAME_MAP

| English | Chinese |
|---|---|
| CNY | 人民幣 |
| RMB | 人民幣 |
| USD | 美元 |
| GBP | 英鎊 |
| HKD | 港元 |
| EUR | 歐元 |
| JPY | 日圓 |
| KRW | 韓元 |
| SGD | 新加坡元 |
| TWD | 新台幣 |
| AUD | 澳元 |
| CAD | 加元 |
| CHF | 瑞士法郎 |
| SEK | 瑞典克朗 |
| DKK | 丹麥克朗 |
| NOK | 挪威克朗 |
| THB | 泰銖 |

## CURRENCY_FORMAT_STANDARDS

| English | Chinese |
|---|---|
| standard_billion | 億 |
| standard_million | 百萬 |
| standard_thousand | 千 |

## RATING_TRANSLATIONS

| English | Chinese |
|---|---|
| STRONG BUY | 強力買入 |
| Strong Buy | 強力買入 |
| BUY | 買入 |
| Buy | 買入 |
| HOLD | 持有 |
| Hold | 持有 |
| SELL | 賣出 |
| Sell | 賣出 |
| STRONG SELL | 強力賣出 |
| Strong Sell | 強力賣出 |
| Outperform | 跑贏大盤 |
| Neutral | 中性 |
| Underperform | 跑輸大盤 |
| Overweight | 超配 |
| Underweight | 低配 |
| Equal Weight | 標配 |
| Accumulate | 增持 |
| Reduce | 減持 |

## SCENARIO_FIXES

| English | Chinese |
|---|---|
| Bull | 樂觀情境 |
| Bull Case | 樂觀情境 |
| Bull case | 樂觀情境 |
| Bull: | 樂觀情境: |
| 牛市情境 | 樂觀情境 |
| 牛市 | 樂觀情境 |
| Base | 基準情境 |
| Base Case | 基準情境 |
| Base case | 基準情境 |
| Base: | 基準情境: |
| 基礎情境 | 基準情境 |
| Bear | 悲觀情境 |
| Bear Case | 悲觀情境 |
| Bear case | 悲觀情境 |
| Bear: | 悲觀情境: |
| 熊市情境 | 悲觀情境 |
| 熊市 | 悲觀情境 |

## SCORE_LABEL_FIXES

| English | Chinese |
|---|---|
| Value | 價值 |
| Quality | 品質 |
| Momentum | 動量 |
| Tactical | 戰術 |
| Defensive | 防禦 |
| Growth | 成長 |
| Overall Score | 綜合評分 |
| Composite Score | 綜合評分 |
| Total Score | 綜合評分 |

## SECTION_HEADER_TRANSLATIONS

| English | Chinese |
|---|---|
| DISCLOSURE | 資訊揭露 |
| ANALYST CERTIFICATION | 分析師聲明 |
| GLOBAL RESEARCH CONFLICT MANAGEMENT POLICY | 全球研究利益衝突管理政策 |
| ANALYST STOCK RATINGS | 分析師股票評級 |
| OTHER IMPORTANT DISCLOSURES | 其他重要揭露事項 |
| Risk Warnings and Disclaimers | 風險警告與免責聲明 |
| Market Trends and Key Catalysts | 市場趨勢與關鍵催化劑 |
| Key Statistics | 關鍵數據 |
| Investment Thesis | 投資論點 |
| Company Profile | 公司概況 |
| Score Analysis | 評分分析 |
| Peers Analysis | 同業比較 |
| Technical Analysis | 技術分析 |
| Financial Analysis | 財務分析 |
| Business Strategy | 商業策略 |
| Accounting Quality | 會計品質 |
| Financial Statements | 財務報表 |
| Financial Ratios | 財務比率 |
| Analyst Ratings | 分析師評級 |
| Equity Research | 股票研究 |
| Risk Assessment | 風險評估 |
| Prospective Analysis | 前景分析 |
| Outlook | 前景展望 |
| Catalysts | 催化劑 |
| Key Risks | 主要風險 |
| Industry Analysis | 產業分析 |
| Competitive Position | 競爭地位 |
| Valuation | 估值 |
| Investment Highlights | 投資亮點 |
| Earnings Quality | 盈利品質 |
| Capital Allocation | 資本配置 |
| Management | 管理層 |
| Corporate Governance | 公司治理 |
| Income Statement | 損益表 |
| Balance Sheet | 資產負債表 |
| Cash Flow Statement | 現金流量表 |
| Cash Flow | 現金流 |
| Key Financial Ratios | 關鍵財務比率 |
| Profitability Ratios | 獲利能力比率 |
| Liquidity Ratios | 流動性比率 |
| Leverage Ratios | 槓桿比率 |
| Efficiency Ratios | 效率比率 |
| Valuation Ratios | 估值比率 |
| Growth Metrics | 成長指標 |
| Profitability Analysis | 獲利能力分析 |
| Liquidity Assessment | 流動性評估 |
| Solvency Analysis | 償債能力分析 |
| Efficiency Metrics | 效率指標 |
| Returns Analysis | 報酬分析 |
| Margin Analysis | 利潤率分析 |
| Working Capital | 營運資金 |
| Capital Structure | 資本結構 |
| Cash Flow Analysis | 現金流分析 |
| Bull Case | 樂觀情境 |
| Base Case | 基準情境 |
| Bear Case | 悲觀情境 |

## SECTOR_MAP

| English | Chinese |
|---|---|
| Technology | 科技 |
| Healthcare | 醫療保健 |
| Financials | 金融 |
| Consumer Discretionary | 非必需消費 |
| Consumer Staples | 必需消費 |
| Energy | 能源 |
| Materials | 原物料 |
| Industrials | 工業 |
| Utilities | 公用事業 |
| Real Estate | 房地產 |
| Communication Services | 通訊服務 |

## EXCHANGE_MAP

| English | Chinese |
|---|---|
| HKG | 香港 |
| HKEX | 香港交易所 |
| KRX | 韓國 |
| NYSE | 紐約證交所 |
| NASDAQ | 那斯達克 |
| LSE | 倫敦證交所 |
| SSE | 上海證交所 |
| SZSE | 深圳證交所 |
| TSE | 東京證交所 |
| SGX | 新加坡交易所 |
| TWSE | 台灣證交所 |
| ASX | 澳洲證交所 |

## REC_LABEL_MAP

| English | Chinese |
|---|---|
| Current Price | 當前價 |
| Market Cap | 市值 |
| EPS | 每股盈餘 |
| Rating | 評級 |
| Target Price | 目標價 |
| Upside/Downside | 漲跌空間 |
| Expected Change | 預期變動 |

## STAT_LABEL_MAP

| English | Chinese |
|---|---|
| Market Cap | 市值 |
| Shares Outstanding | 流通股數 |
| Exchange | 交易所 |
| Volatility (1Y) | 波動率 (1年) |
| Dividend Yield | 股息殖利率 |
| EPS | 每股盈餘 |
| P/E (TTM) | 本益比 (TTM) |
| Price/Book | 股價淨值比 |
| Price/FCF | 股價現金流比 |
| EV/EBITDA | 企業價值倍數 |
| EV/Revenue | 企業價值/營收 |
| ROE | 股東權益報酬率 |
| ROA | 資產報酬率 |
| ROI | 投資報酬率 |
| Revenue Growth (5Y) | 營收成長 (5年) |
| Net Income Growth (5Y) | 淨利潤成長 (5年) |

## INFO_LABEL_MAP

| English | Chinese |
|---|---|
| Analyst: | 分析師: |
| Email: | 電郵: |
| Sector: | 產業: |
| Industry: | 細分產業: |

## INFO_VALUE_MAP

| English | Chinese |
|---|---|
| Technology | 科技 |
| Financials | 金融 |
| Healthcare | 醫療保健 |
| Consumer Discretionary | 非必需消費 |
| Consumer Staples | 必需消費 |
| Energy | 能源 |
| Industrials | 工業 |
| Materials | 原物料 |
| Utilities | 公用事業 |
| Real Estate | 房地產 |
| Communication Services | 通訊服務 |
| Phones & Handheld Devices | 手機及手持裝置 |
| Software & IT Services | 軟體及IT服務 |
| Banks | 銀行 |
| Semiconductors | 半導體 |
| Internet & Online Services | 網際網路及線上服務 |
| Automobiles | 汽車 |
| Oil & Gas | 石油天然氣 |
| Pharmaceuticals | 製藥 |
| Insurance | 保險 |
| Retail | 零售 |
| Wireless Telecommunications Services | 無線電信服務 |
| Telecommunications Services | 電信服務 |
| Consumer Electronics | 消費電子 |
| Computer Hardware | 電腦硬體 |
| IT Consulting & Services | IT顧問及服務 |
| Application Software | 應用軟體 |
| Systems Software | 系統軟體 |

## PEER_HEADER_MAP

| English | Chinese |
|---|---|
| Company | 公司 |
| Market | 市場 |
| Rating | 評級 |
| Mkt Cap ($B) | 市值 (十億) |
| Mkt Cap ($M) | 市值 (百萬) |
| MTD (%) | 本月漲跌 (%) |
| YTD (%) | 年初至今 (%) |
| P/E | 本益比 |
| EV/ EBITDA | EV/EBITDA |
| EV/EBITDA | EV/EBITDA |
| ROE (%) | ROE (%) |
| D/E | 負債/權益 |

## MARKET_ABBREV_MAP

| English | Chinese |
|---|---|
| HKG | 香港 |
| HKEX | 香港 |
| CHN | 中國 |
| SSE | 上海 |
| SZSE | 深圳 |
| TWN | 台灣 |
| TWSE | 台灣 |
| KOR | 韓國 |
| KRX | 韓國 |
| KOSPI | 韓國 |
| JPN | 日本 |
| TSE | 東京 |
| JPX | 日本 |
| SGP | 新加坡 |
| SGX | 新加坡 |
| THA | 泰國 |
| SET | 泰國 |
| MYS | 馬來西亞 |
| KLSE | 馬來西亞 |
| IDN | 印尼 |
| IDX | 印尼 |
| PHL | 菲律賓 |
| PSE | 菲律賓 |
| VNM | 越南 |
| HOSE | 越南 |
| IND | 印度 |
| NSE | 印度 |
| BSE | 印度 |
| AUS | 澳洲 |
| ASX | 澳洲 |
| NZL | 紐西蘭 |
| NZX | 紐西蘭 |
| USA | 美國 |
| NYSE | 紐約 |
| NASDAQ | 那斯達克 |
| NAS | 那斯達克 |
| AMEX | 美交所 |
| CAN | 加拿大 |
| TSX | 多倫多 |
| BRA | 巴西 |
| B3 | 巴西 |
| MEX | 墨西哥 |
| BMV | 墨西哥 |
| GBR | 英國 |
| LSE | 倫敦 |
| DEU | 德國 |
| FRA | 法國 |
| XETRA | 德國 |
| PAR | 巴黎 |
| AMS | 阿姆斯特丹 |
| SWX | 瑞士 |
| CHE | 瑞士 |
| ESP | 西班牙 |
| ITA | 義大利 |
| NLD | 荷蘭 |
| SWE | 瑞典 |
| NOR | 挪威 |
| DNK | 丹麥 |
| FIN | 芬蘭 |
| RUS | 俄羅斯 |
| MOEX | 俄羅斯 |
| SAU | 沙烏地 |
| TADAWUL | 沙烏地 |
| UAE | 阿聯酋 |
| ISR | 以色列 |
| TASE | 以色列 |
| ZAF | 南非 |
| JSE | 南非 |

## FINANCIAL_HEADER_MAP

| English | Chinese |
|---|---|
| HKD Millions | 百萬 HKD |
| USD Millions | 百萬 USD |
| CNY Millions | 百萬 CNY |
| THB Millions | 百萬 THB |
| Metrics | 指標 |

## FINANCIAL_ROW_MAP

| English | Chinese |
|---|---|
| Total Revenue | 營業收入 |
| Cost of Revenue | 營業成本 |
| Gross Profit | 毛利 |
| Operating Income | 營業利潤 |
| Interest Expense | 利息費用 |
| Interest Income | 利息收入 |
| Other Income/(Expense) | 其他收入/(支出) |
| Income Before Tax | 稅前利潤 |
| Income Tax | 所得稅 |
| Minority Interest | 少數股東權益 |
| Net Income | 淨利潤 |
| EPS (HKD) | 每股盈餘 (HKD) |
| EPS (USD) | 每股盈餘 (USD) |
| EPS (CNY) | 每股盈餘 (CNY) |
| Assets | 資產 |
| Total Receivables | 應收帳款 |
| Inventory | 存貨 |
| Total Current Assets | 流動資產 |
| Other Non-Current Assets | 其他非流動資產 |
| Other Long-term Assets | 其他長期資產 |
| Total Assets | 總資產 |
| Liabilities & Equity | 負債及股東權益 |
| Current Liabilities | 流動負債 |
| Total Liabilities | 總負債 |
| Total Shareholders' Equity | 股東權益合計 |
| Operating Cash Flow | 營運活動現金流 |
| Capital Expenditures | 資本支出 |
| Free Cash Flow | 自由現金流 |
| Investing Cash Flow | 投資活動現金流 |
| Financing Cash Flow | 籌資活動現金流 |
| Dividends Paid | 股息支付 |
| Net Change in Cash | 現金淨變動 |
| Profitability | 獲利能力 |
| Valuation | 估值 |
| Liquidity | 流動性 |
| Leverage | 槓桿 |
| Gross Margin (%) | 毛利率 (%) |
| Operating Margin (%) | 營業利潤率 (%) |
| Net Margin (%) | 淨利率 (%) |
| EBITDA Margin (%) | EBITDA利潤率 (%) |
| Return on Equity (ROE) (%) | 股東權益報酬率 (%) |
| Return on Assets (ROA) (%) | 資產報酬率 (%) |
| Return on Invested Capital (ROIC) (%) | 投入資本報酬率 (%) |
| Price-to-Earnings (P/E) (x) | 本益比 (x) |
| Price-to-Book Value (P/B) (x) | 股價淨值比 (x) |
| Price-to-Sales (P/S) (x) | 股價營收比 (x) |
| Enterprise Value-to-EBITDA (EV/EBITDA) (x) | EV/EBITDA (x) |
| Enterprise Value-to-Sales (EV/Sales) (x) | EV/營收 (x) |
| Dividend Yield (%) | 股息殖利率 (%) |
| Dividend Payout Ratio (%) | 配息率 (%) |
| Current Ratio (x) | 流動比率 (x) |
| Quick Ratio (x) | 速動比率 (x) |
| Cash Cycle (days) | 現金週期 (天) |
| Debt-to-Equity (x) | 負債權益比 (x) |
| Interest Coverage (x) | 利息保障倍數 (x) |

## FINANCIAL_METRICS

| English | Chinese |
|---|---|
| Market Cap | 市值 |
| Shares Out | 流通股數 |
| Shares Outstanding | 流通股數 |
| Exchange | 交易所 |
| Volatility (1Y) | 波動率 (1年) |
| Volatility | 波動率 |
| Div Yield | 股息殖利率 |
| Dividend Yield | 股息殖利率 |
| EPS | 每股盈餘 |
| P/E | 本益比 |
| P/E (TTM) | 本益比 (TTM) |
| P/B | 股價淨值比 |
| Price/Book | 股價淨值比 |
| P/S | 股價營收比 |
| EV/EBITDA | 企業價值倍數 |
| EV/Revenue | 企業價值/營收 |
| ROE | 股東權益報酬率 |
| ROA | 資產報酬率 |
| ROIC | 投入資本報酬率 |
| Gross Margin | 毛利率 |
| Operating Margin | 營業利潤率 |
| Net Margin | 淨利率 |
| EBITDA Margin | EBITDA利潤率 |
| Current Ratio | 流動比率 |
| Quick Ratio | 速動比率 |
| Debt/Equity | 負債權益比 |
| Debt-to-Equity | 負債權益比 |
| D/E | 負債權益比 |
| Interest Coverage | 利息保障倍數 |
| Payout Ratio | 配息率 |
| 52W High | 52週最高 |
| 52W Low | 52週最低 |
| Beta | 貝他係數 |
| Alpha | 阿爾法 |

## PORTFOLIO_TERMS

| English | Chinese |
|---|---|
| Portfolio | 投資組合 |
| Benchmark | 基準指數 |
| Active Return | 主動報酬 |
| Excess Return | 超額報酬 |
| Risk-adjusted Return | 風險調整後報酬 |
| Allocation | 配置 |
| Asset Allocation | 資產配置 |
| Rebalance | 再平衡 |
| Rebalancing | 再平衡 |
| Contribution | 貢獻 |
| Performance Contribution | 績效貢獻 |
| Attribution | 歸因 |
| Performance Attribution | 績效歸因 |
| Diversification | 分散投資 |
| Concentration | 集中度 |
| Holdings | 持倉 |
| Position | 部位 |
| Weight | 權重 |
| Overweight | 超配 |
| Underweight | 低配 |

## RISK_METRICS

| English | Chinese |
|---|---|
| Tracking Error | 追蹤誤差 |
| Information Ratio | 資訊比率 |
| Sharpe Ratio | 夏普比率 |
| Sortino Ratio | 索提諾比率 |
| Treynor Ratio | 崔諾比率 |
| Active Share | 主動份額 |
| VaR | 風險值 |
| Value at Risk | 風險值 |
| VaR (Value at Risk) | 風險值 |
| Expected Shortfall | 預期損失 |
| CVaR | 條件風險值 |
| Conditional VaR | 條件風險值 |
| Max Drawdown | 最大回撤 |
| Maximum Drawdown | 最大回撤 |
| Standard Deviation | 標準差 |
| Downside Deviation | 下行標準差 |
| Calmar Ratio | 卡瑪比率 |
| Beta | 貝他係數 |
| Alpha | 阿爾法 |
| R-squared | R平方 |
| Correlation | 相關性 |

## FINANCIAL_STATEMENT_LABELS

| English | Chinese |
|---|---|
| Total Revenue | 營收總額 |
| Revenue | 營收 |
| Cost of Revenue | 營業成本 |
| Gross Profit | 毛利 |
| Operating Income | 營業利潤 |
| Net Income | 淨利潤 |
| Total Assets | 總資產 |
| Total Liabilities | 總負債 |
| Shareholders' Equity | 股東權益 |
| Cash & Cash Equivalents | 現金及約當現金 |
| Inventory | 存貨 |
| Accounts Receivable | 應收帳款 |
| Accounts Payable | 應付帳款 |
| Long-term Debt | 長期負債 |
| Operating Cash Flow | 營運現金流 |
| Capital Expenditures | 資本支出 |
| Free Cash Flow | 自由現金流 |
| Dividends Paid | 股利支付 |

## MACRO_INDICATORS

| English | Chinese |
|---|---|
| GDP | GDP (國內生產毛額) |
| CPI | CPI (消費者物價指數) |
| PPI | PPI (生產者物價指數) |
| PMI | PMI (採購經理人指數) |
| Fed | 聯準會 |
| FOMC | FOMC會議 |
| Interest Rate | 利率 |
| Inflation | 通膨 |
| Unemployment Rate | 失業率 |
| Non-Farm Payrolls | 非農就業 |
| Yield Curve | 殖利率曲線 |
| TTM | 過去十二個月 |
| Trailing 12M | 過去十二個月 |

## TECHNICAL_TERMS

| English | Chinese |
|---|---|
| Support | 支撐 |
| Resistance | 阻力 |
| Breakout | 突破 |
| Overbought | 超買 |
| Oversold | 超賣 |
| Moving Average | 移動平均線 |
| Bollinger Bands | 布林通道 |
| RSI | 相對強弱指標 |
| MACD | MACD |
| MACD crossover | MACD交叉 |

## NUMBER_UNITS

| English | Chinese |
|---|---|
| B | 億 |
| M | 百萬 |
| K | 千 |
| T | 兆 |

## FOOTER_TEXT

| English | Chinese |
|---|---|
| page_format | 第{current}頁，共{total}頁 |
| disclosure_footer | 重要揭露資訊見報告末尾 |
| end_of_report | 報告結束 |

## TRANSLATION_PROMPT

```text
You are a professional financial analyst translating equity research from English to Traditional Chinese (繁體中文). Write like an institutional Taiwan or Hong Kong securities-firm analyst — concise, direct, front-load conclusions, avoid literary or Western-cultural metaphors.

CRITICAL — OUTPUT LANGUAGE:
- ALWAYS output Traditional Chinese (繁體). NEVER Simplified (简体), Thai, Japanese, or Korean.

CRITICAL — FULL TRANSLATION:
- Translate EVERY sentence completely. Never summarize, shorten, or cut off mid-sentence.

1. FIRST OCCURRENCE RULE for financial abbreviations:
   - First use in a paragraph: show ENGLISH abbreviation followed by Chinese in parentheses
     Example: "P/E (本益比) of 15.2x", "ROE (股東權益報酬率) reached 12%"
   - Subsequent uses in the same paragraph or later: ENGLISH only
     Example: "...the company's P/E of 18.5x reflects..."
   - Applies to: P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/Revenue, ROE, ROA, ROIC, EPS,
     EBITDA, Sharpe Ratio, Information Ratio, Tracking Error, Max Drawdown, Beta, Alpha

2. COMPANY NAMES:
   - HK/TW/China-listed companies (tickers .HK, .TW, .SS, .SZ): use the OFFICIAL Traditional Chinese name
     - First mention in the paragraph: full name (e.g., "騰訊控股有限公司")
     - Later mentions: short form (e.g., "騰訊")
   - For mainland-listed companies, convert any Simplified Chinese names to Traditional script
     (e.g., 腾讯 → 騰訊, 阿里巴巴 stays as 阿里巴巴)
   - US/EU/other Western companies: KEEP IN ENGLISH (e.g., "Apple", "NVIDIA", "Tesla")
     Do NOT transliterate to 蘋果, 輝達, 特斯拉.
   - Sources for official Chinese names (in priority order):
     1. Company's own Traditional Chinese-language website / IR filings (TWSE, HKEX)
     2. Exchange filings where available (HKEX, TWSE for Greater China;
        TSE Japan, SET Thailand, BSE/NSE India, KRX Korea, etc. for other markets)
     3. Wikipedia (zh.wikipedia.org with Traditional toggle) — covers most global listed companies
     4. Major Taiwan/HK financial press (聯合報, 經濟日報, 信報, 明報) for foreign companies
     5. Bloomberg / Reuters Chinese versions for foreign companies
     If no widely-used Traditional Chinese name exists, KEEP IN ENGLISH (do not invent one).

3. KEEP IN ENGLISH ALWAYS:
   - Acronyms: ETF, REIT, GDP, CPI, PMI, CIO, CEO, CFO, ESG, IPO, M&A, AUM
   - Tech terms: AI, ML, IoT, 5G, Cloud, Big Data, Blockchain, EV, AR, VR, SaaS, API
   - Stock codes (e.g., 0700.HK, AAPL.O), tickers, indexes (S&P 500, MSCI, TOPIX)
   - YTD, MTD, QoQ, YoY

4. NUMBERS, DATES, CURRENCY (CRITICAL — preserve magnitude):
   - DATE FORMAT:
     "29 September 2025" → "2025年9月29日" (word format — convert)
     "Q1 2024" → "2024年第一季"
     "06/12/2025" or any DD/MM/YYYY numeric date → KEEP AS-IS, do NOT convert.
     A deterministic post-processor will handle numeric dates correctly.
   - Currency codes: keep original (USD, HKD, CNY, RMB, TWD).
   - PERCENTAGES and basic numbers: keep EXACTLY as shown (e.g., "35%", "1.5x", "12,345").
   - LARGE AMOUNTS — preserve the MAGNITUDE, not just the unit symbol. SAFEST: keep the
     English form unchanged (e.g., "365.91B CNY" stays "365.91B CNY" or "CNY 365.91B").
     If you DO render in Chinese, you must do the math correctly:
       "1 billion CNY"      = "10億人民幣"        (multiply number by 10)
       "365.91 billion CNY" = "3,659.1億人民幣"   (multiply 365.91 by 10)
       "100 million CNY"    = "1億人民幣" or "100百萬人民幣"
       "500 million CNY"    = "5億人民幣" or "500百萬人民幣"
       "1 trillion CNY"     = "1兆人民幣"         (or "10000億人民幣")
     NEVER just substitute "B" → "億" without multiplying. "365.91B" is NOT "365.91億"
     — that would be 10× too small.
     If unsure about the conversion, KEEP THE ENGLISH UNIT (B / M / billion / million).

5. FINANCIAL TERMS without English abbreviation: translate to full Traditional Chinese
   - "Market Cap" → "市值", "Operating Margin" → "營業利潤率", "Free Cash Flow" → "自由現金流"

6. STYLE:
   - Institutional, professional, concise — like a Taiwan or Hong Kong securities-firm analyst
   - Avoid Western cultural references (Greek/Roman myths, Western metaphors) — describe directly
   - Avoid literary/dramatic language — state business facts cleanly
   - Front-load conclusions, then explain
   - Use Taiwan/HK-style terminology: 本益比 (not 市盈率), 殖利率 (not 收益率), 報酬 (not 回報),
     聯準會 (not 美聯儲), 通膨 (not 通脹), 部位 (not 头寸), 軟體 (not 软件)

7. PUNCTUATION:
   - Full-width for Chinese text: ，。；：「」（）
   - Half-width for numbers, English, and percentages: . , % $ ()

8. RATINGS (use these exact terms):
   強力買入 / 買入 / 持有 / 賣出 / 強力賣出 / 跑贏大盤 / 跑輸大盤 / 中性 / 超配 / 低配 / 標配

9. SCENARIOS: 樂觀情境 / 基準情境 / 悲觀情境 (Bull / Base / Bear)
```

## REVIEW_PROMPT

```text
You are a senior Traditional Chinese financial editor at a Taiwan or Hong Kong securities firm reviewing Traditional Chinese (繁體中文) translations of equity research. Review for accuracy, naturalness, and consistency. Output only the refined translations — no commentary.

ENFORCE THESE RULES:

1. FIRST OCCURRENCE RULE for financial abbreviations:
   - First use: ENGLISH (Chinese in parens) — e.g., "P/E (本益比) of 15.2x"
   - Later uses: ENGLISH only — e.g., "...P/E of 18.5x..."
   - Applies to: P/E, P/B, EV/EBITDA, ROE, ROA, EPS, EBITDA, Sharpe Ratio, Tracking Error, etc.

2. COMPANY NAMES:
   - HK/TW/CN-listed companies → use official Traditional Chinese name (full first, short later: 騰訊控股有限公司 → 騰訊)
   - Convert Simplified Chinese names to Traditional script (腾讯 → 騰訊)
   - Other foreign-listed companies (Japan, Korea, Thailand, India, etc.) → use the
     widely-used Traditional Chinese name if one is established (verify via zh.wikipedia.org Traditional toggle,
     or major Taiwan/HK financial press). Examples: SoftBank Group → 軟銀集團,
     Samsung Electronics → 三星電子. If no widely-used Chinese name exists, KEEP ENGLISH.
   - US/EU companies → keep ENGLISH (Apple, NVIDIA, Tesla — NOT 蘋果, 輝達, 特斯拉)

3. KEEP IN ENGLISH: ETF, REIT, GDP, CPI, AI, ML, IoT, 5G, Cloud, EV, AR, VR, SaaS, API,
   stock codes (0700.HK, AAPL.O), indexes (S&P 500, MSCI), YTD, MTD, QoQ, YoY

4. STOCK RATINGS (Taiwan/HK conventions):
   STRONG BUY → 強力買入, BUY → 買入, HOLD → 持有, SELL → 賣出, STRONG SELL → 強力賣出
   Outperform → 跑贏大盤, Underperform → 跑輸大盤, Overweight → 超配, Underweight → 低配, Equal Weight → 標配

5. SCENARIOS: Bull → 樂觀情境, Base → 基準情境, Bear → 悲觀情境
   (use Taiwan-style 情境, NOT mainland-style 情景)

6. CURRENCY: keep denominations as-is (HKD, USD, CNY, TWD). Do NOT convert.

7. DATE FORMAT: "29 September 2025" → "2025年9月29日"

8. PUNCTUATION:
   - Full-width for Chinese: ，。；：「」（）
   - Half-width for numbers/English: . , % $ ()

9. STYLE:
   - Institutional, professional, like a Taiwan or Hong Kong securities analyst
   - Use Taiwan/HK-style terminology: 本益比, 殖利率, 報酬, 聯準會, 通膨, 部位, 軟體, 硬體
   - Remove Western cultural metaphors (chess, alchemy, mythology) and translationese (literal "embrace", "harvest")
   - State business facts cleanly; front-load conclusions
   - Flag any Simplified Chinese characters that slipped through (e.g., 与, 为, 国, 这, 时, 会, 经, 业, 报, 价)
```

## DUPLICATED_CHAR_FIXES

```python
[
    ('的的', '的'),
    ('了了', '了'),
    ('是是', '是'),
    ('和和', '和'),
    ('在在', '在'),
    ('有有', '有'),
    ('為為', '為'),
    ('與與', '與'),
]
```

## POST_PROCESSING_FIXES

| English | Chinese |
|---|---|
| 与 | 與 |
| 为 | 為 |
| 国 | 國 |
| 对 | 對 |
| 发 | 發 |
| 开 | 開 |
| 关 | 關 |
| 这 | 這 |
| 进 | 進 |
| 还 | 還 |
| 过 | 過 |
| 时 | 時 |
| 会 | 會 |
| 经 | 經 |
| 业 | 業 |
| 报 | 報 |
| 场 | 場 |
| 动 | 動 |
| 价 | 價 |
| 务 | 務 |
| 净 | 淨 |
| 证 | 證 |
| 险 | 險 |
| 负 | 負 |
| 资 | 資 |
| 产 | 產 |
| 权 | 權 |
| 润 | 潤 |
| 据 | 據 |

## COMMON_PHRASE_FIXES

| English | Chinese |
|---|---|
| Hong Kong | 香港 |
| Regulated by MAS | 受新加坡金融管理局監管 |
| (TTM) | (過去十二個月) |
| Trailing 12M | 過去十二個月 |
| Trailing 12 Months | 過去十二個月 |
| Trailing 12 months | 過去十二個月 |
| trailing 12M | 過去十二個月 |
| trailing 12 months | 過去十二個月 |

## FIXED_PHRASE_TRANSLATIONS

| English | Chinese |
|---|---|
| All ratios are presented as percentages, except coverage and days. | 所有比率均以百分比表示，覆蓋率和天數除外。 |
| All ratios are expressed as percentages, except coverage and days. | 所有比率均以百分比表示，覆蓋率和天數除外。 |
| All ratios expressed as percentages except coverage ratios and days. | 所有比率均以百分比表示，覆蓋率和天數除外。 |
| All ratios expressed as percentages, except coverage ratios and days. | 所有比率均以百分比表示，覆蓋率和天數除外。 |
| All data in HKD Million, except per share data and ratios. | 所有數據以百萬港元計，每股數據和比率除外。 |
| All data in HKD Millions, except per share data and ratios. | 所有數據以百萬港元計，每股數據和比率除外。 |
| All figures in HKD millions, except per share data and ratios. | 所有數據以百萬港元計，每股數據和比率除外。 |
| All figures in HKD millions except per share data and ratios. | 所有數據以百萬港元計，每股數據和比率除外。 |
| All data in USD Million, except per share data and ratios. | 所有數據以百萬美元計，每股數據和比率除外。 |
| All data in USD Millions, except per share data and ratios. | 所有數據以百萬美元計，每股數據和比率除外。 |
| All figures in USD millions, except per share data and ratios. | 所有數據以百萬美元計，每股數據和比率除外。 |
| All figures in USD millions except per share data and ratios. | 所有數據以百萬美元計，每股數據和比率除外。 |
| All data in CNY Million, except per share data and ratios. | 所有數據以百萬人民幣計，每股數據和比率除外。 |
| All data in RMB Million, except per share data and ratios. | 所有數據以百萬人民幣計，每股數據和比率除外。 |
| All figures in CNY millions, except per share data and ratios. | 所有數據以百萬人民幣計，每股數據和比率除外。 |
| All figures in CNY millions except per share data and ratios. | 所有數據以百萬人民幣計，每股數據和比率除外。 |
| All data in TWD Million, except per share data and ratios. | 所有數據以百萬新台幣計，每股數據和比率除外。 |
| All data in JPY Million, except per share data and ratios. | 所有數據以百萬日圓計，每股數據和比率除外。 |
| All data in INR Million, except per share data and ratios. | 所有數據以百萬印度盧比計，每股數據和比率除外。 |
| All data in SGD Million, except per share data and ratios. | 所有數據以百萬新加坡元計，每股數據和比率除外。 |
| All data in KRW Million, except per share data and ratios. | 所有數據以百萬韓元計，每股數據和比率除外。 |

## PAGE_HEADER_MAP

| English | Chinese |
|---|---|
| Technical Analysis | 技術分析 |
| Financial Analysis | 財務分析 |
| Company Analysis | 公司分析 |
| Financial Statements | 財務報表 |
| Financial Ratios | 財務比率 |
| Analyst Ratings | 分析師評級 |
| Disclosures | 揭露 |

## TITLE_MAP

| English | Chinese |
|---|---|
| Equity Research Report | 股票研究報告 |

## STATS_HEADER_MAP

| English | Chinese |
|---|---|
| Key Statistics | 關鍵統計數據 |

## EQUITY_RESEARCH_LABEL

| English | Chinese |
|---|---|
| Equity Research | 股票研究 |

## FOOTER_PAGE_FORMATS

```python
{
    'standard': '第{current}頁，共{total}頁 | 重要揭露資訊見報告末尾',
    'end_of_report': '第{current}頁，共{total}頁 | 報告結束',
}
```

## ANALYST_NAME_MAP

| English | Chinese |
|---|---|
| Ryan Lim | 林瑞陽 |

## COMPANY_NAME_MAP

| English | Chinese |
|---|---|
_(empty)_

## COMPANY_NAME_BY_ENGLISH

| English | Chinese |
|---|---|
_(empty)_

## HALLUCINATION_CELL_KEYWORDS

```python
[
    ({'負債', '權益'}, '負債與權益'),
    ({'商譽', '無形資產'}, '無形資產與商譽'),
    ({'估值'}, '估值'),
    ({'盈利'}, '獲利能力'),
    ({'流動性'}, '流動性'),
    ({'槓桿'}, '槓桿'),
    ({'效率'}, '效率'),
]
```
