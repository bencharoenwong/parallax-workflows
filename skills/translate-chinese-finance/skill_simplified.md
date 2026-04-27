# Chinese Translation Skill

Auto-generated from `chinese_translation_config.py` on 2026-04-27. This is the runtime data source for the Chinese translation pipeline. Edits here are loaded by `skill_loader.py` at script start.

**Format conventions:**
- `## NAME` heading marks each section.
- Markdown tables (English | Chinese) → simple string→string maps (no `|` in values).
- ` ```python ` code blocks → complex Python literals or dicts with special chars.
- ` ```text ` code blocks → multi-line strings (prompts).
- A `bool: True/False`, `int: <n>`, or `str: <value>` line → scalar.

---

## LANGUAGE_CODE

str: zh-CN

## LANGUAGE_NAME

str: Simplified Chinese

## LANGUAGE_SCRIPT

str: 简体中文

## USE_BUDDHIST_ERA

bool: False

## YEAR_OFFSET

int: 0

## COUNTRY_MAP

| English | Chinese |
|---|---|
| Hong Kong | 香港 |
| China | 中国 |
| United States | 美国 |
| USA | 美国 |
| Japan | 日本 |
| South Korea | 韩国 |
| Korea | 韩国 |
| Taiwan | 台湾 |
| Singapore | 新加坡 |
| India | 印度 |
| United Kingdom | 英国 |
| UK | 英国 |
| Germany | 德国 |
| France | 法国 |
| Australia | 澳大利亚 |
| Canada | 加拿大 |
| Brazil | 巴西 |
| Indonesia | 印度尼西亚 |
| Malaysia | 马来西亚 |
| Thailand | 泰国 |
| Vietnam | 越南 |
| Philippines | 菲律宾 |
| Switzerland | 瑞士 |
| Netherlands | 荷兰 |
| Sweden | 瑞典 |
| Russia | 俄罗斯 |
| Saudi Arabia | 沙特阿拉伯 |
| UAE | 阿联酋 |
| Israel | 以色列 |
| South Africa | 南非 |
| Mexico | 墨西哥 |
| New Zealand | 新西兰 |
| Spain | 西班牙 |
| Italy | 意大利 |

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
| fy_standard | 财年 |
| fy_short | 年 |

## CURRENCY_NAME_MAP

| English | Chinese |
|---|---|
| CNY | 人民币 |
| RMB | 人民币 |
| USD | 美元 |
| GBP | 英镑 |
| HKD | 港元 |
| EUR | 欧元 |
| JPY | 日元 |
| KRW | 韩元 |
| SGD | 新加坡元 |
| TWD | 新台币 |
| AUD | 澳元 |
| CAD | 加元 |
| CHF | 瑞士法郎 |
| SEK | 瑞典克朗 |
| DKK | 丹麦克朗 |
| NOK | 挪威克朗 |
| THB | 泰铢 |

## CURRENCY_FORMAT_STANDARDS

| English | Chinese |
|---|---|
| standard_billion | 亿 |
| standard_million | 百万 |
| standard_thousand | 千 |

## RATING_TRANSLATIONS

| English | Chinese |
|---|---|
| STRONG BUY | 强力买入 |
| Strong Buy | 强力买入 |
| BUY | 买入 |
| Buy | 买入 |
| HOLD | 持有 |
| Hold | 持有 |
| SELL | 卖出 |
| Sell | 卖出 |
| STRONG SELL | 强力卖出 |
| Strong Sell | 强力卖出 |
| Outperform | 跑赢大盘 |
| Neutral | 中性 |
| Underperform | 跑输大盘 |
| Overweight | 超配 |
| Underweight | 低配 |
| Equal Weight | 标配 |
| Accumulate | 增持 |
| Reduce | 减持 |

## SCENARIO_FIXES

| English | Chinese |
|---|---|
| Bull | 乐观情景 |
| Bull Case | 乐观情景 |
| Bull case | 乐观情景 |
| Bull: | 乐观情景: |
| 牛市情景 | 乐观情景 |
| 牛市 | 乐观情景 |
| Base | 基准情景 |
| Base Case | 基准情景 |
| Base case | 基准情景 |
| Base: | 基准情景: |
| 基础情景 | 基准情景 |
| Bear | 悲观情景 |
| Bear Case | 悲观情景 |
| Bear case | 悲观情景 |
| Bear: | 悲观情景: |
| 熊市情景 | 悲观情景 |
| 熊市 | 悲观情景 |

## SCORE_LABEL_FIXES

| English | Chinese |
|---|---|
| Value | 价值 |
| Quality | 质量 |
| Momentum | 动量 |
| Tactical | 战术 |
| Defensive | 防御 |
| Growth | 成长 |
| Overall Score | 综合评分 |
| Composite Score | 综合评分 |
| Total Score | 综合评分 |

## SECTION_HEADER_TRANSLATIONS

| English | Chinese |
|---|---|
| DISCLOSURE | 信息披露 |
| ANALYST CERTIFICATION | 分析师声明 |
| GLOBAL RESEARCH CONFLICT MANAGEMENT POLICY | 全球研究利益冲突管理政策 |
| ANALYST STOCK RATINGS | 分析师股票评级 |
| OTHER IMPORTANT DISCLOSURES | 其他重要披露事项 |
| Risk Warnings and Disclaimers | 风险警告与免责声明 |
| Market Trends and Key Catalysts | 市场趋势与关键催化剂 |
| Key Statistics | 关键数据 |
| Investment Thesis | 投资论点 |
| Company Profile | 公司概况 |
| Score Analysis | 评分分析 |
| Peers Analysis | 同业比较 |
| Technical Analysis | 技术分析 |
| Financial Analysis | 财务分析 |
| Business Strategy | 商业策略 |
| Accounting Quality | 会计质量 |
| Financial Statements | 财务报表 |
| Financial Ratios | 财务比率 |
| Analyst Ratings | 分析师评级 |
| Equity Research | 股票研究 |
| Risk Assessment | 风险评估 |
| Prospective Analysis | 前景分析 |
| Outlook | 前景展望 |
| Catalysts | 催化剂 |
| Key Risks | 主要风险 |
| Industry Analysis | 行业分析 |
| Competitive Position | 竞争地位 |
| Valuation | 估值 |
| Investment Highlights | 投资亮点 |
| Earnings Quality | 盈利质量 |
| Capital Allocation | 资本配置 |
| Management | 管理层 |
| Corporate Governance | 公司治理 |
| Income Statement | 利润表 |
| Balance Sheet | 资产负债表 |
| Cash Flow Statement | 现金流量表 |
| Cash Flow | 现金流 |
| Key Financial Ratios | 关键财务比率 |
| Profitability Ratios | 盈利能力比率 |
| Liquidity Ratios | 流动性比率 |
| Leverage Ratios | 杠杆比率 |
| Efficiency Ratios | 效率比率 |
| Valuation Ratios | 估值比率 |
| Growth Metrics | 增长指标 |
| Profitability Analysis | 盈利能力分析 |
| Liquidity Assessment | 流动性评估 |
| Solvency Analysis | 偿债能力分析 |
| Efficiency Metrics | 效率指标 |
| Returns Analysis | 回报分析 |
| Margin Analysis | 利润率分析 |
| Working Capital | 营运资金 |
| Capital Structure | 资本结构 |
| Cash Flow Analysis | 现金流分析 |
| Bull Case | 乐观情景 |
| Base Case | 基准情景 |
| Bear Case | 悲观情景 |

## SECTOR_MAP

| English | Chinese |
|---|---|
| Technology | 科技 |
| Healthcare | 医疗保健 |
| Financials | 金融 |
| Consumer Discretionary | 非必需消费 |
| Consumer Staples | 必需消费 |
| Energy | 能源 |
| Materials | 原材料 |
| Industrials | 工业 |
| Utilities | 公用事业 |
| Real Estate | 房地产 |
| Communication Services | 通信服务 |

## EXCHANGE_MAP

| English | Chinese |
|---|---|
| HKG | 香港 |
| HKEX | 香港交易所 |
| KRX | 韩国 |
| NYSE | 纽约证交所 |
| NASDAQ | 纳斯达克 |
| LSE | 伦敦证交所 |
| SSE | 上海证交所 |
| SZSE | 深圳证交所 |
| TSE | 东京证交所 |
| SGX | 新加坡交易所 |
| TWSE | 台湾证交所 |
| ASX | 澳洲证交所 |

## REC_LABEL_MAP

| English | Chinese |
|---|---|
| Current Price | 当前价 |
| Market Cap | 市值 |
| EPS | 每股收益 |
| Rating | 评级 |
| Target Price | 目标价 |
| Upside/Downside | 涨跌空间 |
| Expected Change | 预期变动 |

## STAT_LABEL_MAP

| English | Chinese |
|---|---|
| Market Cap | 市值 |
| Shares Outstanding | 流通股数 |
| Exchange | 交易所 |
| Volatility (1Y) | 波动率 (1年) |
| Dividend Yield | 股息率 |
| EPS | 每股收益 |
| P/E (TTM) | 市盈率 (TTM) |
| Price/Book | 市净率 |
| Price/FCF | 市现率 |
| EV/EBITDA | 企业价值倍数 |
| EV/Revenue | 企业价值/营收 |
| ROE | 股本回报率 |
| ROA | 资产回报率 |
| ROI | 投资回报率 |
| Revenue Growth (5Y) | 营收增长 (5年) |
| Net Income Growth (5Y) | 净利润增长 (5年) |

## INFO_LABEL_MAP

| English | Chinese |
|---|---|
| Analyst: | 分析师: |
| Email: | 邮箱: |
| Sector: | 行业: |
| Industry: | 细分行业: |

## INFO_VALUE_MAP

| English | Chinese |
|---|---|
| Technology | 科技 |
| Financials | 金融 |
| Healthcare | 医疗保健 |
| Consumer Discretionary | 可选消费 |
| Consumer Staples | 必需消费 |
| Energy | 能源 |
| Industrials | 工业 |
| Materials | 材料 |
| Utilities | 公用事业 |
| Real Estate | 房地产 |
| Communication Services | 通信服务 |
| Phones & Handheld Devices | 手机及手持设备 |
| Software & IT Services | 软件及IT服务 |
| Banks | 银行 |
| Semiconductors | 半导体 |
| Internet & Online Services | 互联网及在线服务 |
| Automobiles | 汽车 |
| Oil & Gas | 石油天然气 |
| Pharmaceuticals | 制药 |
| Insurance | 保险 |
| Retail | 零售 |
| Wireless Telecommunications Services | 无线电信服务 |
| Telecommunications Services | 电信服务 |
| Consumer Electronics | 消费电子 |
| Computer Hardware | 计算机硬件 |
| IT Consulting & Services | IT咨询及服务 |
| Application Software | 应用软件 |
| Systems Software | 系统软件 |

## PEER_HEADER_MAP

| English | Chinese |
|---|---|
| Company | 公司 |
| Market | 市场 |
| Rating | 评级 |
| Mkt Cap ($B) | 市值 (十亿) |
| Mkt Cap ($M) | 市值 (百万) |
| MTD (%) | 本月涨跌 (%) |
| YTD (%) | 年初至今 (%) |
| P/E | 市盈率 |
| EV/ EBITDA | EV/EBITDA |
| EV/EBITDA | EV/EBITDA |
| ROE (%) | ROE (%) |
| D/E | 负债/权益 |

## MARKET_ABBREV_MAP

| English | Chinese |
|---|---|
| HKG | 香港 |
| HKEX | 香港 |
| CHN | 中国 |
| SSE | 上海 |
| SZSE | 深圳 |
| TWN | 台湾 |
| TWSE | 台湾 |
| KOR | 韩国 |
| KRX | 韩国 |
| KOSPI | 韩国 |
| JPN | 日本 |
| TSE | 东京 |
| JPX | 日本 |
| SGP | 新加坡 |
| SGX | 新加坡 |
| THA | 泰国 |
| SET | 泰国 |
| MYS | 马来西亚 |
| KLSE | 马来西亚 |
| IDN | 印尼 |
| IDX | 印尼 |
| PHL | 菲律宾 |
| PSE | 菲律宾 |
| VNM | 越南 |
| HOSE | 越南 |
| IND | 印度 |
| NSE | 印度 |
| BSE | 印度 |
| AUS | 澳大利亚 |
| ASX | 澳大利亚 |
| NZL | 新西兰 |
| NZX | 新西兰 |
| USA | 美国 |
| NYSE | 纽约 |
| NASDAQ | 纳斯达克 |
| NAS | 纳斯达克 |
| AMEX | 美交所 |
| CAN | 加拿大 |
| TSX | 多伦多 |
| BRA | 巴西 |
| B3 | 巴西 |
| MEX | 墨西哥 |
| BMV | 墨西哥 |
| GBR | 英国 |
| LSE | 伦敦 |
| DEU | 德国 |
| FRA | 法国 |
| XETRA | 德国 |
| PAR | 巴黎 |
| AMS | 阿姆斯特丹 |
| SWX | 瑞士 |
| CHE | 瑞士 |
| ESP | 西班牙 |
| ITA | 意大利 |
| NLD | 荷兰 |
| SWE | 瑞典 |
| NOR | 挪威 |
| DNK | 丹麦 |
| FIN | 芬兰 |
| RUS | 俄罗斯 |
| MOEX | 俄罗斯 |
| SAU | 沙特 |
| TADAWUL | 沙特 |
| UAE | 阿联酋 |
| ISR | 以色列 |
| TASE | 以色列 |
| ZAF | 南非 |
| JSE | 南非 |

## FINANCIAL_HEADER_MAP

| English | Chinese |
|---|---|
| HKD Millions | 百万 HKD |
| USD Millions | 百万 USD |
| CNY Millions | 百万 CNY |
| THB Millions | 百万 THB |
| Metrics | 指标 |

## FINANCIAL_ROW_MAP

| English | Chinese |
|---|---|
| Total Revenue | 营业收入 |
| Cost of Revenue | 营业成本 |
| Gross Profit | 毛利 |
| Operating Income | 营业利润 |
| Interest Expense | 利息费用 |
| Interest Income | 利息收入 |
| Other Income/(Expense) | 其他收入/(支出) |
| Income Before Tax | 税前利润 |
| Income Tax | 所得税 |
| Minority Interest | 少数股东权益 |
| Net Income | 净利润 |
| EPS (HKD) | 每股收益 (HKD) |
| EPS (USD) | 每股收益 (USD) |
| EPS (CNY) | 每股收益 (CNY) |
| Assets | 资产 |
| Total Receivables | 应收账款 |
| Inventory | 存货 |
| Total Current Assets | 流动资产 |
| Other Non-Current Assets | 其他非流动资产 |
| Other Long-term Assets | 其他长期资产 |
| Total Assets | 总资产 |
| Liabilities & Equity | 负债及股东权益 |
| Current Liabilities | 流动负债 |
| Total Liabilities | 总负债 |
| Total Shareholders' Equity | 股东权益合计 |
| Operating Cash Flow | 经营活动现金流 |
| Capital Expenditures | 资本支出 |
| Free Cash Flow | 自由现金流 |
| Investing Cash Flow | 投资活动现金流 |
| Financing Cash Flow | 筹资活动现金流 |
| Dividends Paid | 股息支付 |
| Net Change in Cash | 现金净变动 |
| Profitability | 盈利能力 |
| Valuation | 估值 |
| Liquidity | 流动性 |
| Leverage | 杠杆 |
| Gross Margin (%) | 毛利率 (%) |
| Operating Margin (%) | 营业利润率 (%) |
| Net Margin (%) | 净利率 (%) |
| EBITDA Margin (%) | EBITDA利润率 (%) |
| Return on Equity (ROE) (%) | 股本回报率 (%) |
| Return on Assets (ROA) (%) | 资产回报率 (%) |
| Return on Invested Capital (ROIC) (%) | 投入资本回报率 (%) |
| Price-to-Earnings (P/E) (x) | 市盈率 (x) |
| Price-to-Book Value (P/B) (x) | 市净率 (x) |
| Price-to-Sales (P/S) (x) | 市销率 (x) |
| Enterprise Value-to-EBITDA (EV/EBITDA) (x) | EV/EBITDA (x) |
| Enterprise Value-to-Sales (EV/Sales) (x) | EV/营收 (x) |
| Dividend Yield (%) | 股息率 (%) |
| Dividend Payout Ratio (%) | 派息率 (%) |
| Current Ratio (x) | 流动比率 (x) |
| Quick Ratio (x) | 速动比率 (x) |
| Cash Cycle (days) | 现金周期 (天) |
| Debt-to-Equity (x) | 负债权益比 (x) |
| Interest Coverage (x) | 利息保障倍数 (x) |

## FINANCIAL_METRICS

| English | Chinese |
|---|---|
| Market Cap | 市值 |
| Shares Out | 流通股数 |
| Shares Outstanding | 流通股数 |
| Exchange | 交易所 |
| Volatility (1Y) | 波动率 (1年) |
| Volatility | 波动率 |
| Div Yield | 股息率 |
| Dividend Yield | 股息率 |
| EPS | 每股收益 |
| P/E | 市盈率 |
| P/E (TTM) | 市盈率 (TTM) |
| P/B | 市净率 |
| Price/Book | 市净率 |
| P/S | 市销率 |
| EV/EBITDA | 企业价值倍数 |
| EV/Revenue | 企业价值/营收 |
| ROE | 股本回报率 |
| ROA | 资产回报率 |
| ROIC | 投入资本回报率 |
| Gross Margin | 毛利率 |
| Operating Margin | 营业利润率 |
| Net Margin | 净利率 |
| EBITDA Margin | EBITDA利润率 |
| Current Ratio | 流动比率 |
| Quick Ratio | 速动比率 |
| Debt/Equity | 负债权益比 |
| Debt-to-Equity | 负债权益比 |
| D/E | 负债权益比 |
| Interest Coverage | 利息保障倍数 |
| Payout Ratio | 派息率 |
| 52W High | 52周最高 |
| 52W Low | 52周最低 |
| Beta | 贝塔系数 |
| Alpha | 阿尔法 |

## PORTFOLIO_TERMS

| English | Chinese |
|---|---|
| Portfolio | 投资组合 |
| Benchmark | 基准指数 |
| Active Return | 主动收益 |
| Excess Return | 超额收益 |
| Risk-adjusted Return | 风险调整后收益 |
| Allocation | 配置 |
| Asset Allocation | 资产配置 |
| Rebalance | 再平衡 |
| Rebalancing | 再平衡 |
| Contribution | 贡献 |
| Performance Contribution | 业绩贡献 |
| Attribution | 归因 |
| Performance Attribution | 业绩归因 |
| Diversification | 分散投资 |
| Concentration | 集中度 |
| Holdings | 持仓 |
| Position | 头寸 |
| Weight | 权重 |
| Overweight | 超配 |
| Underweight | 低配 |

## RISK_METRICS

| English | Chinese |
|---|---|
| Tracking Error | 跟踪误差 |
| Information Ratio | 信息比率 |
| Sharpe Ratio | 夏普比率 |
| Sortino Ratio | 索提诺比率 |
| Treynor Ratio | 特雷诺比率 |
| Active Share | 主动份额 |
| VaR | 风险价值 |
| Value at Risk | 风险价值 |
| VaR (Value at Risk) | 风险价值 |
| Expected Shortfall | 预期损失 |
| CVaR | 条件风险价值 |
| Conditional VaR | 条件风险价值 |
| Max Drawdown | 最大回撤 |
| Maximum Drawdown | 最大回撤 |
| Standard Deviation | 标准差 |
| Downside Deviation | 下行标准差 |
| Calmar Ratio | 卡玛比率 |
| Beta | 贝塔系数 |
| Alpha | 阿尔法 |
| R-squared | R平方 |
| Correlation | 相关性 |

## FINANCIAL_STATEMENT_LABELS

| English | Chinese |
|---|---|
| Total Revenue | 营收总额 |
| Revenue | 营收 |
| Cost of Revenue | 营业成本 |
| Gross Profit | 毛利 |
| Operating Income | 营业利润 |
| Net Income | 净利润 |
| Total Assets | 总资产 |
| Total Liabilities | 总负债 |
| Shareholders' Equity | 股东权益 |
| Cash & Cash Equivalents | 现金及现金等价物 |
| Inventory | 存货 |
| Accounts Receivable | 应收账款 |
| Accounts Payable | 应付账款 |
| Long-term Debt | 长期负债 |
| Operating Cash Flow | 经营现金流 |
| Capital Expenditures | 资本支出 |
| Free Cash Flow | 自由现金流 |
| Dividends Paid | 股利支付 |

## MACRO_INDICATORS

| English | Chinese |
|---|---|
| GDP | GDP (国内生产总值) |
| CPI | CPI (消费者物价指数) |
| PPI | PPI (生产者物价指数) |
| PMI | PMI (采购经理人指数) |
| Fed | 美联储 |
| FOMC | 联储会议 |
| Interest Rate | 利率 |
| Inflation | 通胀 |
| Unemployment Rate | 失业率 |
| Non-Farm Payrolls | 非农就业 |
| Yield Curve | 收益率曲线 |
| TTM | 过去十二个月 |
| Trailing 12M | 过去十二个月 |

## TECHNICAL_TERMS

| English | Chinese |
|---|---|
| Support | 支撑 |
| Resistance | 阻力 |
| Breakout | 突破 |
| Overbought | 超买 |
| Oversold | 超卖 |
| Moving Average | 移动平均线 |
| Bollinger Bands | 布林带 |
| RSI | 相对强弱指标 |
| MACD | MACD |
| MACD crossover | MACD交叉 |

## NUMBER_UNITS

| English | Chinese |
|---|---|
| B | 亿 |
| M | 百万 |
| K | 千 |
| T | 万亿 |

## FOOTER_TEXT

| English | Chinese |
|---|---|
| page_format | 第{current}页，共{total}页 |
| disclosure_footer | 重要披露信息见报告末尾 |
| end_of_report | 报告结束 |

## TRANSLATION_PROMPT

```text
You are a professional financial analyst translating equity research from English to Simplified Chinese (简体中文). Write like an institutional Chinese analyst — concise, direct, front-load conclusions, avoid literary or Western-cultural metaphors.

CRITICAL — OUTPUT LANGUAGE:
- ALWAYS output Simplified Chinese (简体). NEVER Traditional (繁體), Thai, Japanese, or Korean.

CRITICAL — FULL TRANSLATION:
- Translate EVERY sentence completely. Never summarize, shorten, or cut off mid-sentence.

1. FIRST OCCURRENCE RULE for financial abbreviations:
   - First use in a paragraph: show ENGLISH abbreviation followed by Chinese in parentheses
     Example: "P/E (市盈率) of 15.2x", "ROE (股本回报率) reached 12%"
   - Subsequent uses in the same paragraph or later: ENGLISH only
     Example: "...the company's P/E of 18.5x reflects..."
   - Applies to: P/E, P/B, P/S, P/FCF, EV/EBITDA, EV/Revenue, ROE, ROA, ROIC, EPS,
     EBITDA, Sharpe Ratio, Information Ratio, Tracking Error, Max Drawdown, Beta, Alpha

2. COMPANY NAMES:
   - HK/TW/China-listed companies (tickers .HK, .TW, .SS, .SZ): use the OFFICIAL Chinese name
     - First mention in the paragraph: full name (e.g., "腾讯控股有限公司")
     - Later mentions: short form (e.g., "腾讯")
   - US/EU/other Western companies: KEEP IN ENGLISH (e.g., "Apple", "NVIDIA", "Tesla")
     Do NOT transliterate to 苹果, 辉达, 特斯拉.
   - Sources for official Chinese names (in priority order):
     1. Company's own Chinese-language website / IR filings
     2. Exchange filings where available (HKEX, TWSE, SSE, SZSE for Greater China;
        TSE Japan, SET Thailand, BSE/NSE India, KRX Korea, etc. for other markets)
     3. Wikipedia (zh.wikipedia.org) — covers most global listed companies
     4. Baidu Baike (baike.baidu.com) — Chinese-language general reference
     5. Bloomberg / Reuters / major Chinese financial press for foreign companies
     If no widely-used Chinese name exists, KEEP IN ENGLISH (do not invent one).

3. KEEP IN ENGLISH ALWAYS:
   - Acronyms: ETF, REIT, GDP, CPI, PMI, CIO, CEO, CFO, ESG, IPO, M&A, AUM
   - Tech terms: AI, ML, IoT, 5G, Cloud, Big Data, Blockchain, EV, AR, VR, SaaS, API
   - Stock codes (e.g., 0700.HK, AAPL.O), tickers, indexes (S&P 500, MSCI, TOPIX)
   - YTD, MTD, QoQ, YoY

4. NUMBERS, DATES, CURRENCY (CRITICAL — preserve magnitude):
   - DATE FORMAT:
     "29 September 2025" → "2025年9月29日" (word format — convert)
     "Q1 2024" → "2024年第一季度"
     "06/12/2025" or any DD/MM/YYYY numeric date → KEEP AS-IS, do NOT convert.
     A deterministic post-processor will handle numeric dates correctly.
   - Currency codes: keep original (USD, HKD, CNY, RMB).
   - PERCENTAGES and basic numbers: keep EXACTLY as shown (e.g., "35%", "1.5x", "12,345").
   - LARGE AMOUNTS — preserve the MAGNITUDE, not just the unit symbol. SAFEST: keep the
     English form unchanged (e.g., "365.91B CNY" stays "365.91B CNY" or "CNY 365.91B").
     If you DO render in Chinese, you must do the math correctly:
       "1 billion CNY"      = "10亿人民币"        (multiply number by 10)
       "365.91 billion CNY" = "3,659.1亿人民币"   (multiply 365.91 by 10)
       "100 million CNY"    = "1亿人民币" or "100百万人民币"
       "500 million CNY"    = "5亿人民币" or "500百万人民币"
       "1 trillion CNY"     = "1万亿人民币"       (or "10000亿人民币")
     NEVER just substitute "B" → "亿" without multiplying. "365.91B" is NOT "365.91亿"
     — that would be 10× too small.
     If unsure about the conversion, KEEP THE ENGLISH UNIT (B / M / billion / million).

5. FINANCIAL TERMS without English abbreviation: translate to full Chinese
   - "Market Cap" → "市值", "Operating Margin" → "营业利润率", "Free Cash Flow" → "自由现金流"

6. STYLE:
   - Institutional, professional, concise — like a Chinese securities-firm analyst
   - Avoid Western cultural references (Greek/Roman myths, Western metaphors) — describe directly
   - Avoid literary/dramatic language — state business facts cleanly
   - Front-load conclusions, then explain

7. PUNCTUATION:
   - Full-width for Chinese text: ，。；：「」（）
   - Half-width for numbers, English, and percentages: . , % $ ()

8. RATINGS (use these exact terms):
   强力买入 / 买入 / 持有 / 卖出 / 强力卖出 / 跑赢大盘 / 跑输大盘 / 中性 / 超配 / 低配 / 标配

9. SCENARIOS: 乐观情景 / 基准情景 / 悲观情景 (Bull / Base / Bear)
```

## REVIEW_PROMPT

```text
You are a senior Chinese financial editor at a mainland securities firm reviewing Simplified Chinese (简体中文) translations of equity research. Review for accuracy, naturalness, and consistency. Output only the refined translations — no commentary.

ENFORCE THESE RULES:

1. FIRST OCCURRENCE RULE for financial abbreviations:
   - First use: ENGLISH (Chinese in parens) — e.g., "P/E (市盈率) of 15.2x"
   - Later uses: ENGLISH only — e.g., "...P/E of 18.5x..."
   - Applies to: P/E, P/B, EV/EBITDA, ROE, ROA, EPS, EBITDA, Sharpe Ratio, Tracking Error, etc.

2. COMPANY NAMES:
   - HK/TW/CN-listed companies → use official Chinese name (full first, short later: 腾讯控股有限公司 → 腾讯)
   - Other foreign-listed companies (Japan, Korea, Thailand, India, etc.) → use the
     widely-used Chinese name if one is established (verify via Wikipedia 中文,
     Baidu Baike, or major Chinese financial press). Examples: SoftBank Group → 软银集团,
     Samsung Electronics → 三星电子. If no widely-used Chinese name exists, KEEP ENGLISH.
   - US/EU companies → keep ENGLISH (Apple, NVIDIA, Tesla — NOT 苹果, 辉达, 特斯拉)

3. KEEP IN ENGLISH: ETF, REIT, GDP, CPI, AI, ML, IoT, 5G, Cloud, EV, AR, VR, SaaS, API,
   stock codes (0700.HK, AAPL.O), indexes (S&P 500, MSCI), YTD, MTD, QoQ, YoY

4. STOCK RATINGS (mainland conventions):
   STRONG BUY → 强力买入, BUY → 买入, HOLD → 持有, SELL → 卖出, STRONG SELL → 强力卖出
   Outperform → 跑赢大盘, Underperform → 跑输大盘, Overweight → 超配, Underweight → 低配, Equal Weight → 标配

5. SCENARIOS: Bull → 乐观情景, Base → 基准情景, Bear → 悲观情景
   (NOT 牛市情景, 熊市情景, 基础情景, or Taiwan-style 情境)

6. CURRENCY: keep denominations as-is (HKD, USD, CNY). Do NOT convert.

7. DATE FORMAT: "29 September 2025" → "2025年9月29日"

8. PUNCTUATION:
   - Full-width for Chinese: ，。；：「」（）
   - Half-width for numbers/English: . , % $ ()

9. STYLE:
   - Institutional, professional, like a mainland Chinese securities analyst
   - Remove Western cultural metaphors (chess, alchemy, mythology) and translationese (literal "embrace", "harvest")
   - State business facts cleanly; front-load conclusions
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
    ('为为', '为'),
    ('与与', '与'),
]
```

## POST_PROCESSING_FIXES

| English | Chinese |
|---|---|
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

## COMMON_PHRASE_FIXES

| English | Chinese |
|---|---|
| Hong Kong | 香港 |
| Regulated by MAS | 受新加坡金融管理局监管 |
| (TTM) | (过去十二个月) |
| Trailing 12M | 过去十二个月 |
| Trailing 12 Months | 过去十二个月 |
| Trailing 12 months | 过去十二个月 |
| trailing 12M | 过去十二个月 |
| trailing 12 months | 过去十二个月 |

## FIXED_PHRASE_TRANSLATIONS

| English | Chinese |
|---|---|
| All ratios are presented as percentages, except coverage and days. | 所有比率均以百分比表示，覆盖率和天数除外。 |
| All ratios are expressed as percentages, except coverage and days. | 所有比率均以百分比表示，覆盖率和天数除外。 |
| All ratios expressed as percentages except coverage ratios and days. | 所有比率均以百分比表示，覆盖率和天数除外。 |
| All ratios expressed as percentages, except coverage ratios and days. | 所有比率均以百分比表示，覆盖率和天数除外。 |
| All data in HKD Million, except per share data and ratios. | 所有数据以百万港元计，每股数据和比率除外。 |
| All data in HKD Millions, except per share data and ratios. | 所有数据以百万港元计，每股数据和比率除外。 |
| All figures in HKD millions, except per share data and ratios. | 所有数据以百万港元计，每股数据和比率除外。 |
| All figures in HKD millions except per share data and ratios. | 所有数据以百万港元计，每股数据和比率除外。 |
| All data in USD Million, except per share data and ratios. | 所有数据以百万美元计，每股数据和比率除外。 |
| All data in USD Millions, except per share data and ratios. | 所有数据以百万美元计，每股数据和比率除外。 |
| All figures in USD millions, except per share data and ratios. | 所有数据以百万美元计，每股数据和比率除外。 |
| All figures in USD millions except per share data and ratios. | 所有数据以百万美元计，每股数据和比率除外。 |
| All data in CNY Million, except per share data and ratios. | 所有数据以百万人民币计，每股数据和比率除外。 |
| All data in RMB Million, except per share data and ratios. | 所有数据以百万人民币计，每股数据和比率除外。 |
| All figures in CNY millions, except per share data and ratios. | 所有数据以百万人民币计，每股数据和比率除外。 |
| All figures in CNY millions except per share data and ratios. | 所有数据以百万人民币计，每股数据和比率除外。 |
| All data in TWD Million, except per share data and ratios. | 所有数据以百万新台币计，每股数据和比率除外。 |
| All data in JPY Million, except per share data and ratios. | 所有数据以百万日元计，每股数据和比率除外。 |
| All data in INR Million, except per share data and ratios. | 所有数据以百万印度卢比计，每股数据和比率除外。 |
| All data in SGD Million, except per share data and ratios. | 所有数据以百万新加坡元计，每股数据和比率除外。 |
| All data in KRW Million, except per share data and ratios. | 所有数据以百万韩元计，每股数据和比率除外。 |

## PAGE_HEADER_MAP

| English | Chinese |
|---|---|
| Technical Analysis | 技术分析 |
| Financial Analysis | 财务分析 |
| Company Analysis | 公司分析 |
| Financial Statements | 财务报表 |
| Financial Ratios | 财务比率 |
| Analyst Ratings | 分析师评级 |
| Disclosures | 披露 |

## TITLE_MAP

| English | Chinese |
|---|---|
| Equity Research Report | 股票研究报告 |

## STATS_HEADER_MAP

| English | Chinese |
|---|---|
| Key Statistics | 关键统计数据 |

## EQUITY_RESEARCH_LABEL

| English | Chinese |
|---|---|
| Equity Research | 股票研究 |

## FOOTER_PAGE_FORMATS

```python
{
    'standard': '第{current}页，共{total}页 | 重要披露信息见报告末尾',
    'end_of_report': '第{current}页，共{total}页 | 报告结束',
}
```

## ANALYST_NAME_MAP

| English | Chinese |
|---|---|
| Ryan Lim | 林瑞阳 |

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
    ({'负债', '权益'}, '负债与权益'),
    ({'商誉', '无形资产'}, '无形资产与商誉'),
    ({'估值'}, '估值'),
    ({'盈利'}, '盈利能力'),
    ({'流动性'}, '流动性'),
    ({'杠杆'}, '杠杆'),
    ({'效率'}, '效率'),
]
```
