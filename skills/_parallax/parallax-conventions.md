# Parallax Skill Conventions

Shared patterns for all `parallax-*` skills. JIT-load from any skill that calls Parallax MCP tools.

---

## 0. Feature Flags

Gemini CLI uses feature flags to roll out architectural changes. These can be set via environment variables or documented at the session start.

- **`PARALLAX_LOADER_V2=1`** (Phase 0 rewrite):
  - **Universe Construction**: Replaces single-shot tilt-prepended `build_stock_universe` calls with N parallel per-tilt calls + client-side merge/dedupe. Required for multi-sector/multi-theme views to prevent universe collapse (Q-A).
  - **Portfolio Scoring**: Replaces batch `quick_portfolio_scores` with per-holding `get_peer_snapshot` aggregation + `get_company_info` cross-validation. Required to bypass upstream symbol-mapping bugs (Q-B).
  - **Active House View**: When a house view is active, V2 patterns are MANDATORY to ensure tilt integrity.

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

**For portfolio workflows (`PARALLAX_LOADER_V2=1`):** Use per-holding `get_peer_snapshot` aggregation in parallel with `get_company_info` cross-validation. This is the **primary robust path**. Do NOT rely on `quick_portfolio_scores` for portfolio factor profiling when a house view is active.

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

**For `PARALLAX_LOADER_V2=1` (Preferred path):** Always use parallel per-holding `get_peer_snapshot` aggregation. If a specific holding returns "No scores available," retry once. If it still fails, skip the holding's contribution to the weighted average and report degraded coverage.

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

## 7. Capability Index — "I want to do X, which skill/tool?"

External integrators and skill authors frequently ask for capabilities that already exist under a different name. Check this index before proposing a new skill or REST endpoint.

### Portfolio analytics

| User-phrased need | Use this | Notes |
|---|---|---|
| Stress book / scenario analysis | `/parallax-scenario-analysis` skill | Forward-looking event analysis (rate shock, USD shock, oil shock, regime replays). Skill orchestrates `get_assessment` + macro + news. NOT a REST primitive — talk track lives in skill layer. |
| Drawdown attribution ("why am I down X%?") | `/parallax-explain-portfolio` skill | Decomposes drawdown into market-regime / factor / stock-specific components via score-vs-price divergence. ~60 tokens. |
| Per-holding return contribution | `analyze_portfolio` → `company_contribution` field | Returns `total_pl`, `contribution_pct`, `return_pct`, `avg_weight` per holding. **NOTE:** This is RETURN contribution, NOT risk contribution (no marginal vol / component VaR). For risk decomposition, no current capability — flag as gap. |
| Portfolio drawdown statistics | `analyze_portfolio` → `drawdown_analysis` field | Includes `current_drawdown`, `max_drawdown`, underwater periods, durations, recovery days, and a per-day timeseries. See `response-schemas.md` for nested structure. |
| Rolling metrics (Sharpe, vol, beta, correlation) | `analyze_portfolio` → `rolling_metrics` field | Three windows: `window_30d` / `window_60d` / `window_90d`, each with daily timeseries. See `response-schemas.md`. |
| Concentration / effective N / HHI | `analyze_portfolio` → `concentration_metrics` field | `effective_positions` is weight-based (1/HHI on weights). Risk-weighted Effective N is not currently exposed. |
| Score time series (per symbol) | `get_score_analysis` with `weeks` parameter | Returns weeks-windowed factor history. Default 52 weeks. **Portfolio-level score history is not currently exposed** — must aggregate per-holding client-side. |
| Sector/market overlap, redundancy | `check_portfolio_redundancy` | Pairwise overlap + clustering at the portfolio level. |
| Build/tilt a stock universe | `build_stock_universe` (V2: per-tilt parallel calls per §0) | Free-text query, sector-scoped. |

### Multi-stock / consensus

| User-phrased need | Use this | Notes |
|---|---|---|
| Multi-investor consensus across factor-profile lenses | `/parallax-AI-consensus` skill | Orchestrates Buffett / Klarman / Greenblatt / Soros / PTJ profile skills. **Skill-only by design** — multi-profile orchestration with judgment fusion does NOT translate to a REST contract without freezing the ensemble. |
| Single-investor profile factor scoring | `/parallax-AI-buffett`, `-AI-soros`, `-AI-greenblatt`, `-AI-klarman`, `-AI-ptj` | Each is a standalone profile skill. Profiles ARE proprietary — see `_parallax/AI-profiles/`. |
| Peer comparison table | `get_peer_snapshot` | Symbol → `target_company` (top-level) + peer rows (`name` field). |

### Symbol resolution & search

| User-phrased need | Use this | Notes |
|---|---|---|
| Plain ticker → RIC | Pass through any tool — most resolve automatically; otherwise apply §1 suffix table | `analyze_portfolio` already routes through `bulk_resolve_symbols` server-side. If a symbol comes back in `data_quality.missing_rics`, it's missing from the IDENTIFIERS table (see §1 escalation). |
| Fuzzy / typo-tolerant search ("apple" / "semiconductor") | `search_stocks` MCP tool | Whoosh-backed; supports market/sector filters. |
| Validate a single symbol | `validate_symbol` MCP tool (if exposed) — otherwise `get_company_info` | Returns resolved RIC. |

### Reports & analysis

| User-phrased need | Use this | Notes |
|---|---|---|
| Full Parallax research report (PDF-shaped) | `get_stock_report` (async, ~1-2min) | Use `check_job_status` to poll. |
| Forensic earnings-quality screen | `/parallax-earnings-quality` skill | Accruals, revenue recognition, manipulation risk. |
| Full Palepu-framework due diligence | `/parallax-due-diligence` skill | Financials + ratios + macro context + Parallax research report. |
| Long/short pair construction | `/parallax-pair-finder` skill | Given one leg, suggests counter-leg from peers; given both, reports residual exposure. |

### Reverse-lookup: "I have a Parallax response field, what is it?"

If you see a field in a response and don't know what it means, check `response-schemas.md` (nested structure of `rolling_metrics`, `drawdown_analysis`, `concentration_metrics`, `company_contribution`, `portfolio_scores`, `data_quality`). That file is authoritative until upstream OpenAPI publishes example responses.

---

## 8. Marketing & Competitive Integrity

For all marketing artifacts (vs-pages, alternative guides, feature comparisons), the **Autoreason Adversarial Loop** is the mandatory quality gate.

1. **Evidence-First**: Every claim about a competitor must be cross-referenced against the `competitor-intelligence` schema.
2. **Adversarial Audit**: High-stakes content must be filtered through a **Strawman** persona to detect and remove "marketing slop" (hyperbolic adjectives) and unsubstantiated claims.
3. **Objective Nuance**: Every comparison must include a "Who should choose [Competitor]" section to maintain institutional credibility.
4. **Staleness Check**: Competitive claims are dated. If the teardown data is >180 days old, a fresh verification is required before publishing.

---

## 9. Disclaimer

### §9.1 Standard disclaimer

Every workflow output must end with a disclaimer. Use the exact wording from the skill's Output Format section if one is specified, otherwise use:

*"This is informational analysis based on Parallax factor scores, not investment advice. All outputs should be reviewed by qualified professionals before any investment decisions."*

### §9.2 AI-interaction disclosure

Every workflow output that contains AI-generated narrative, synthesis, or recommendations MUST render the following banner immediately above the §9.1 disclaimer (or immediately above the view-aware disclaimer when an active house view is loaded — see house-view/loader.md §5 rule 6). This applies whether or not a white-label client view is active, and whether or not a house view is loaded. The wording is a working banner pending counsel sign-off:

> *AI-assisted output. Quantitative data — factor scores, financials, peer mappings, technicals, price series — is from Parallax's deterministic pipelines. Qualitative content — news synthesis, macro commentary, AI assessments, narrative framing, and recommendations — is LLM-generated, either by Parallax's MCP services (news, macro, assessment) or by the orchestrating model (narrative and recommendations). See the Provenance footer for per-source attribution and version, and the trace ID for end-to-end output attribution. Verify any specific statement before acting.*

<!-- COUNSEL-TBD — final wording subject to counsel sign-off. The current text is the working banner: it accurately distinguishes deterministic quantitative pipelines from LLM-generated qualitative content (covering both Parallax MCP services like news/macro/assessment and the orchestrating model), references the Provenance footer and trace ID for attribution, and avoids a methodology URL. Do not add a URL until counsel has signed off. The trace ID surface exists today; an end-to-end attribution API endpoint is in progress — when it lands, append a one-line "Resolve a trace ID at <url>" pointer here and the change propagates to all consumer skills via this single source of truth. -->

**Why §9.2 is mandatory:**

- **EU AI Act Art 13 / Art 50** — transparency-by-design and AI-interaction disclosure for outputs produced by an LLM-assisted pipeline.
- **HKMA GenAI Circular (Nov 2024)** and **SFC GenAI guidance** — disclosure of GenAI involvement in licensed-corp customer-facing material.
- **MAS FEAT** — transparency principle for AI-augmented decision support.
- **SR 11-7** conceptual-soundness implication: a client must be able to distinguish the deterministic model output (CG scoring pipeline) from the LLM synthesis layer.

**Exemption:** Skills that produce configuration artifacts rather than direct client-facing analysis (currently `parallax-white-label-onboard`) are exempt from rendering §9.2. The rationale is narrow: such skills must (a) emit YAML/audit artifacts rather than a finished client deliverable, AND (b) gate any LLM-generated content behind an explicit operator confirmation step before that content can flow to downstream consumer skills. `white-label-onboard` qualifies because its Step 1.5 voice extraction is LLM-driven, but the resulting voice profile is reviewed and confirmed by the operator at Step 3 before being written to `~/.parallax/client-branding/` for downstream skills to consume — at which point the downstream skill renders §9.2 in its own output. A future skill that emits LLM-generated content without an equivalent operator gate does NOT qualify for exemption, even if it produces "config" — the gate, not the artifact format, is the load-bearing condition. Adding a skill to `_NINE_TWO_EXEMPT_SKILLS` in the test gate requires updating this exemption text in the same PR.

**Consumer skill reference pattern:** Skills MUST render the §9.2 banner by reference, not by inlining the text. Example Output Format directive: `Render AI-interaction disclosure per parallax-conventions.md §9.2 immediately above the disclaimer.` Inlining the banner text creates drift risk — when counsel finalizes the wording (or when the attribution API lands), the canonical §9.2 entry is edited once and all consumer skills propagate automatically.
