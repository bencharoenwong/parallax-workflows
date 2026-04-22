# Parallax Skill Conventions

Shared patterns for all `parallax-*` skills. JIT-load from any skill that calls Parallax MCP tools.

---

## 0. Loader path selection (V1 vs V2)

**Authoritative rule:** V2 is MANDATORY whenever an active house view is loaded, regardless of env-var state. V2 is the DEFAULT whenever the user query names ≥2 sectors/themes OR the workflow renders per-holding factor scores. V1 is the legacy path, permitted only for single-sector queries on no-view sessions.

**Selection logic a skill MUST follow** (in order):
1. If an active house view loads successfully → **V2**. Do not check any env var.
2. Else, if the query/tilt names ≥2 sectors/themes → **V2** (prevents Q-A universe collapse).
3. Else, if the workflow renders per-holding factor scores (morning-brief, client-review, portfolio-checkup, etc.) → **V2** (prevents Q-B symbol mis-mapping).
4. Else → V1 permitted.

**Env-var `PARALLAX_LOADER_V2`** (override, optional):
- Unset (default): follow the authoritative rule above.
- `=1`: force V2 unconditionally.
- `=0`: force V1. **If an active view is loaded AND `PARALLAX_LOADER_V2=0` is exported, skills MUST refuse to proceed** with: "Cannot run view-driven workflow with PARALLAX_LOADER_V2=0 — V2 is mandatory when a view is active. Unset the variable or export PARALLAX_LOADER_V2=1."

**V2 behaviors** (applied whenever rule 1, 2, or 3 fires):
- **Universe Construction**: N parallel per-tilt `build_stock_universe` calls + client-side merge/dedupe (per loader.md §3a V2 application).
- **Portfolio Scoring**: Per-holding `get_peer_snapshot` aggregation + mandatory `get_company_info` cross-validation (per loader.md §3b V2 application).

**Universal rules (apply regardless of path):**
- **Ground-truth panel** (loader.md §5 rule 3) and **divergence assertion** (rule 4) apply to all skills, all paths, view or no view.
- **Minimum coverage floor**: if fewer than 50% of holdings by weight produce trusted (non-MISMATCH, non-failure) scores, do NOT render a portfolio-level factor profile. Render per-holding scores only, with a portfolio-level note: "Insufficient coverage for aggregate profile."

---

## 0.1 MCP Tool Loading

Parallax tools (`mcp__claude_ai_Parallax__*`) are deferred MCP tools. Before the first Parallax tool call in any session, call `ToolSearch` with query `"+Parallax"` to load the tool schemas. Without this step, tool calls will fail with "tool not found."

---

## 0.2 Tool Parameter Reference

Parameter names that commonly trip up skill authors (and LLMs guessing from prose). Use the exact names below when calling these tools:

| Tool | Parameter | Type | Notes |
|---|---|---|---|
| `macro_analyst` | `market` (not `country`) | string | e.g., `"United States"`, `"Japan"`. Matches names returned by `list_macro_countries`. |
| `macro_analyst` | `component` | string | e.g., `"tactical"`, `"sectors"`, `"factors"`. See `list_macro_countries` next_steps for others. |
| `build_stock_universe` | `query` (not `description`) | string | Free-text sector-scoped query, e.g., `"US large-cap technology software"`. Broad/abstract queries time out. |
| `get_financials` | `statement` | string | `"summary"`, `"balance_sheet"`, `"cash_flow"`, `"ratios"`. Defaults to `"summary"`. |
| `get_financials` | `periods` | integer | Defaults to 4. **Do NOT pass as string via `:periods=4` syntax** — MCP serializes it as a string and fails validation. Rely on server default or pass as typed integer at call site. |
| `get_score_analysis` | `weeks` | integer | Defaults to 52. Same serialization caveat as `periods`. |
| `get_stock_outlook` | `limit` | integer | Defaults to 20 (applies to `dividends` aspect, range 1-100). Same serialization caveat as `periods`. |
| `export_price_series` | `days` | integer | Defaults to 100 (range 1-365). Same serialization caveat as `periods`. |
| `get_peer_snapshot` | N/A | — | Symbol only; company-identity field in response is `target_company` (top-level), NOT `name` (which refers to individual peer rows). |

Any skill calling `macro_analyst` or `build_stock_universe` with `country=` or `description=` will fail with an MCP parameter validation error. Skills should always use the names in this table.

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

**For portfolio workflows on V2 path (per §0 selection logic):** Use per-holding `get_peer_snapshot` aggregation in parallel with `get_company_info` cross-validation. This is the **primary robust path**. Do NOT rely on `quick_portfolio_scores` for portfolio factor profiling when a house view is active.

**For portfolio workflows (Legacy/V1):** Cross-check company names for each holding in the `quick_portfolio_scores` response. If any holding maps to the wrong company, re-score that holding individually via `get_peer_snapshot` and note the discrepancy.

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

### Fast-response tools
`get_company_info`, `get_peer_snapshot`, `get_score_analysis`, `get_financials`, `get_stock_outlook`, `explain_methodology`, `list_macro_countries`, `macro_analyst`

→ Retry once on failure. If second attempt fails, mark section as **"Data unavailable"** and continue.

Note: "fast-response" refers to latency, not token cost. Token costs vary per tool — see `token-costs.md` for the full table. In particular, `macro_analyst` returns quickly but costs 5 tokens per call.

### Async tools
`get_news_synthesis` (~30-90s), `get_assessment` (~30-90s), `get_technical_analysis`, `get_financial_analysis` (~2-5min), `get_stock_report` (~1-2min)

→ Do not retry immediately. If they fail or time out, note **"Analysis pending — service temporarily unavailable"** and continue.

### Stock outlook coverage
`get_stock_outlook` has 4 aspects: `analyst_targets`, `recommendations`, `risk_return`, `dividends`.
- **2+ aspects return data** → Proceed normally, note missing aspects.
- **0-1 aspects return data** → Flag: "Insight card may be materially incomplete for this security."

### Portfolio scoring coverage
If `quick_portfolio_scores` (Legacy/V1) covers **<50% of holdings by weight**, execute mixed-exchange fallback:
1. Split holdings by exchange suffix.
2. Score each exchange group separately.
3. Merge into portfolio-weighted result.
4. Note: "Scoring used split-and-merge due to partial coverage."

**For V2 path (per §0 selection logic — preferred):** Always use parallel per-holding `get_peer_snapshot` aggregation. If a specific holding returns "No scores available," retry once. If it still fails, skip the holding's contribution to the weighted average and report degraded coverage.

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
