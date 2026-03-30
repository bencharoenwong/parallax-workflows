# Parallax Skill Conventions

Shared patterns for all `parallax-*` skills. JIT-load from any skill that calls Parallax MCP tools.

---

## 0. MCP Tool Loading

Parallax tools (`mcp__claude_ai_Parallax__*`) are deferred MCP tools. Before the first Parallax tool call in any session, call `ToolSearch` with query `"+Parallax"` to load the tool schemas. Without this step, tool calls will fail with "tool not found."

---

## 1. RIC Resolution

Parallax tools require Reuters Instrument Codes (RICs). When the user provides a plain ticker:

1. Call `get_company_info` with the plain ticker first — it often resolves automatically.
2. If empty result, retry with the most likely exchange suffix from this table:

| Exchange | Suffix | Example | Clues |
|---|---|---|---|
| NASDAQ | `.O` | `AAPL.O` | US tech, biotech |
| NYSE | `.N` | `JPM.N` | US financials, industrials |
| London | `.L` | `SHEL.L` | UK companies |
| Frankfurt / Xetra | `.DE` | `SAP.DE` | German companies |
| Paris | `.PA` | `MC.PA` | French companies |
| Tokyo | `.T` | `7203.T` | Numeric codes (4 digits) |
| Hong Kong | `.HK` | `0700.HK` | Numeric codes (4 digits, context: China/HK) |
| Taiwan | `.TW` | `2330.TW` | Numeric codes (4 digits, context: Taiwan) |
| Sydney | `.AX` | `BHP.AX` | Australian companies |
| Oslo | `.OL` | `YAR.OL` | Norwegian companies |
| Korea | `.KS` | `005930.KS` | 6-digit numeric codes |

**Resolution order for ambiguous plain tickers:** Try `.O` → `.N` first (US most common). For numeric tickers, use digit count + context: 4 digits → `.T` or `.HK` or `.TW` depending on context; 6 digits → `.KS`.

Only escalate to the user if resolution fails after 2 attempts with the most likely suffixes.

**Peer symbol RIC resolution:** Peer symbols from `get_peer_snapshot` may lack exchange suffixes (e.g., `GM` instead of `GM.N`). Resolve them using the exchange suffix table above before passing to downstream tools.

---

## 2. Symbol Cross-Validation

Scoring tools (`get_peer_snapshot`, `get_score_analysis`, `quick_portfolio_scores`) may occasionally return data for a different company than intended — especially for numeric codes (`.HK`, `.T`, `.TW`, `.KS`) but also for alphabetic tickers on any exchange.

**After any scoring call:**

1. Cross-check the `name` field returned by the scoring tool against the `get_company_info` result for the same symbol.
2. If names diverge, warn the user clearly and treat `get_company_info` as the source of truth.
3. Do not present scores from a mismatched company as belonging to the intended security.

**For portfolio workflows (`quick_portfolio_scores`):** Cross-check company names for each holding in the response. If any holding maps to the wrong company, re-score that holding individually via `get_peer_snapshot` and note the discrepancy.

**Hong Kong / numeric codes require extra caution:** HK uses numeric codes that can collide across H-shares, red chips, and local listings. Always cross-validate `.HK`, `.T`, `.TW`, `.KS` symbols.

---

## 3. Parallel Execution

Default execution mode is **parallel where dependencies allow**. Claude Code supports concurrent MCP tool calls within a single response turn.

**Batch your calls:**
- **Independent calls** fire simultaneously: `get_company_info`, `get_peer_snapshot`, `get_financials`, `get_score_analysis`, `get_stock_outlook` (all aspects), `get_news_synthesis`, `check_portfolio_redundancy`, `quick_portfolio_scores`
- **Dependent calls** wait for prior results: `get_assessment` (needs all findings), `macro_analyst` (needs `list_macro_countries` result + company info for market reasoning), `build_stock_universe` (needs analysis of what to replace)

**Example single-stock batch:**
```
Batch A (parallel): get_company_info + get_peer_snapshot + get_financials + get_score_analysis + get_stock_outlook (×4 aspects) + get_news_synthesis
Batch B (after A):  list_macro_countries → macro_analyst per relevant market
Batch C (after B):  get_assessment (synthesis prompt with all data)
```

---

## 4. Graceful Fallback Patterns

### Instant tools
`get_company_info`, `get_peer_snapshot`, `get_score_analysis`, `get_financials`, `get_stock_outlook`, `explain_methodology`, `list_macro_countries`, `macro_analyst`

→ Retry once on failure. If second attempt fails, mark section as **"Data unavailable"** and continue.

### Async tools
`get_news_synthesis` (~30-90s), `get_assessment` (~30-90s), `get_technical_analysis`, `get_financial_analysis` (~2-5min), `get_stock_report` (~1-2min)

→ Do not retry immediately. If they fail or time out, note **"Analysis pending — service temporarily unavailable"** and continue.

### Stock outlook coverage
`get_stock_outlook` has 4 aspects: `analyst_targets`, `recommendations`, `risk_return`, `dividends`.
- **2+ aspects return data** → Proceed normally, note missing aspects.
- **0-1 aspects return data** → Flag: "Insight card may be materially incomplete for this security."

### Portfolio scoring coverage
If `quick_portfolio_scores` covers **<50% of holdings by weight**, execute mixed-exchange fallback:
1. Split holdings by exchange suffix.
2. Score each exchange group separately.
3. Merge into portfolio-weighted result.
4. Note: "Scoring used split-and-merge due to partial coverage."

If `quick_portfolio_scores` returns **"Could not score any holdings"** for ALL positions (not just partial coverage), fall back to individual `get_peer_snapshot` calls per holding to get current factor scores. Report degraded coverage — trend data will be unavailable.

If `check_portfolio_redundancy` covers **<60% of holdings**, flag redundancy results as **"Low confidence — limited coverage."**

### Concentration flag caveat
For portfolios with fewer than 7 holdings, concentration flags (>15% single, >45% top-3) are structural and reflect portfolio size, not poor diversification. Note them but don't alarm.

### Empty-output handling
If any tool returns successfully but with no output content (not an error, just empty), treat as a failure and apply standard retry logic. Do not treat empty-but-successful as valid data.

---

## 5. News Async Handling

`get_news_synthesis` takes 30-90s and should never block output assembly.

- Fire it in parallel with other data calls.
- Begin assembling output from instant-response tools immediately.
- Insert news section when it resolves.
- If still pending when output is ready, include `"news": "pending"` placeholder.

---

## 6. Macro Context Reasoning

When analyzing a single stock or portfolio, determine relevant macro markets:

1. **Home market** — Derive from RIC suffix (`.O`/`.N` → US, `.T` → Japan, `.HK` → China/HK, etc.)
2. **Revenue geographies** — If `get_company_info` mentions major revenue from other regions, include those.
3. **Commodity exposures** — Energy/materials companies: add commodity-relevant markets.
4. **Supply chain** — Known dependencies (e.g., semiconductors → Taiwan, China).

**Procedure:**
1. Call `list_macro_countries` to get covered markets.
2. Identify which covered markets are relevant (reasoning, not just mechanical mapping).
3. Call `macro_analyst` with `component: "tactical"` for each relevant market.
4. Cap at **3 markets** for single-stock, **3 unique markets** for portfolios (to manage latency).

If no covered markets are relevant, return `"macro": "unavailable"` — don't force irrelevant context.

**Macro fallback from RIC suffixes:** If `list_macro_countries` fails, derive home market(s) from RIC suffixes: `.O`/`.N`/`.K` = United States, `.T` = Japan, `.HK` = Hong Kong, `.L` = United Kingdom, `.SI` = Singapore, `.DE` = Germany. Use the exchange suffix table in Section 1.

---

## 7. Disclaimer

Every workflow output must end with a disclaimer. Use the exact wording from the skill's Output Format section if one is specified, otherwise use:

*"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*
