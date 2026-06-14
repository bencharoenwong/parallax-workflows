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

## 0.0 Pre-flight (before any data gathering)

Run this once at the top of any should-i-buy / two-lens / house-view / portfolio workflow, **before the first data call** — not as a mid-run recovery:

1. **Resolve paths.** Resolve every `_parallax/...` conventions and house-view path to the canonical `parallax-workflows` copy (see `skill-structure-conventions.md` → "Canonical source & path resolution"). Do not assume the installed skill directory contains them.
2. **Confirm MCP readiness.** Call `ToolSearch` with `"+Parallax"` and confirm the `mcp__claude_ai_Parallax__*` schemas have registered before the first tool call (§0.1). Treat an empty/interrupted first batch as a schema-registration race, not "no data" — re-fire the full batch once (§0.1).
3. **Abort cleanly on a gap.** If a required convention/house-view file cannot be resolved, or the Parallax tools have still not registered after the §0.1 re-fire, **stop and tell the operator exactly what is missing.** Do not silently proceed on partial inputs or fall through to fabricated data.

Most should-i-buy failures trace to one of two causes this pre-flight removes — missing convention/house-view files, and MCP calls racing schema registration. Converting those mid-run recoveries into one up-front check is what prevents sessions that burn the turn budget before producing output. This is the open-side complement to §0.3 (validation before reporting done).

---

## 0.1 MCP Tool Loading


Parallax tools (`mcp__claude_ai_Parallax__*`) are deferred MCP tools. Before the first Parallax tool call in any session, call `ToolSearch` with query `"+Parallax"` to load the tool schemas. Without this step, tool calls will fail with "tool not found."

**Empty or cancelled first batch ≠ "no data."** If the first batch of Parallax calls after `ToolSearch` comes back empty, or is interrupted by an unrelated error (a stray `ls`, a 502, a cancelled sibling call), re-fire the entire batch once before concluding the data is unavailable — schemas may not have finished registering when the first calls fired. Only after a clean re-fire still returns empty do the §4 fallback patterns apply. This is distinct from §4's per-tool empty-output retry, which applies after initialization is confirmed — this rule is batch-level and first-call-only.

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

## 0.3 Validation before reporting done

Before reporting any Parallax workflow complete:

1. **Data integrity** — confirm the MCP batch returned real data, not an init race (per §0.1: an empty or interrupted first batch is re-fired in full before "no data" is concluded). Empty ≠ done.
2. **House-view integrity** — when a house view is active, confirm the `view_status` banner was actually rendered in the output and not silently dropped. The `malformed` / `expired` / `critical` states MUST surface to the operator verbatim (loader.md §2 "Load-time validation", item 6) — never swallow an integrity failure to make a workflow look clean.

Integrity failures are flagged explicitly in the output, not omitted. This is the Parallax-domain instance of the completion-claim discipline in `CLAUDE.verification.md` ("a passing metric is necessary, not sufficient"; verify, don't eyeball).

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

## 3.1 Concurrent Annotation Pattern

When a skill produces a ranked output (e.g., Top Picks) and also needs to attach annotations derived from already-known rank inputs (e.g., macro tags, regime classification), the annotation step **must run concurrently with downstream consumers of the rank, never gate them**.

**Reference implementation:** `thematic-screen/SKILL.md` Phase C1.5.

**Rule:** annotation steps that derive from data already available at the moment rank is established MUST NOT block subsequent steps that consume rank order. In thematic-screen the pattern is:
- C1 establishes rank (composite scoring + ground-truth check)
- C1.5 annotates with macro_tag — runs concurrently with C2 and C3
- C2 calls `export_peer_comparison` on the highest-scored trusted row
- C3 calls `get_financials` on top-3 trusted picks

C1.5 does NOT gate C2 or C3 because C2 and C3 only need the rank C1 produced — they do not need C1.5's annotations.

**Non-negotiable constraints when copying this pattern:**

1. Annotations MUST NOT change rank order. Rank stays composite-driven from the upstream scoring step to preserve auditability.
2. Annotations MUST NOT alter membership (do not drop, filter, or re-select rows based on annotation values).
3. Downstream consumers (chained skills, exporters, dashboards) MUST also preserve all annotated rows in their output — annotation tags are read-only, NEVER a filter predicate.
4. The downstream-row-preservation contract is a parallel obligation to the section-header parsing contract; both must be honored by any consumer of an annotated output.

**Anti-pattern:** introducing a sort or filter step driven by annotation values. Re-ranking by annotation breaks auditability and inverts the purpose of separating rank from annotation in the first place.

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
| Multi-investor consensus across factor-profile lenses | `/parallax-ai-consensus` skill | Orchestrates Buffett / Klarman / Greenblatt / Soros / PTJ profile skills. **Skill-only by design** — multi-profile orchestration with judgment fusion does NOT translate to a REST contract without freezing the ensemble. |
| Single-investor profile factor scoring | `/parallax-ai-buffett`, `-ai-soros`, `-ai-greenblatt`, `-ai-klarman`, `-ai-ptj` | Each is a standalone profile skill. Profiles ARE proprietary — see `_parallax/AI-profiles/`. |
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

**Consumer skill reference pattern:** Skills using the standard wording MUST render it by reference, not by inlining the text. Example Output Format directive: `Render the standard disclaimer verbatim from parallax-conventions.md §9.1.` Inlining creates drift risk — the wording above is the single source of truth, and a future edit propagates to all consumer skills automatically. Skills with bespoke disclaimers (e.g., scenario-analysis's scenario-based wording, pair-finder's liquidity caveat, concierge's router wording) keep their full wording inline in their own Output Format section per the first paragraph of this section — the skill, not this file, owns bespoke wording. House-view consumers substitute the view-aware disclaimer per `house-view/loader.md` §5 rule 5 when an active view is loaded.

### §9.2 AI-interaction disclosure

Every workflow output that contains AI-generated narrative, synthesis, or recommendations MUST render the following banner immediately above the §9.1 disclaimer (or immediately above the view-aware disclaimer when an active house view is loaded — see house-view/loader.md §5 rule 6). This applies whether or not a white-label client view is active, and whether or not a house view is loaded. The wording is a working banner pending counsel sign-off:

> *AI-assisted output. Quantitative data — factor scores, financials, peer mappings, technicals, price series — is from Parallax's deterministic pipelines. Qualitative content — news synthesis, macro commentary, AI assessments, narrative framing, and recommendations — is LLM-generated, either by Parallax's MCP services (news, macro, assessment) or by the orchestrating model (narrative and recommendations). See the Provenance footer for per-source attribution and version, and the trace ID for end-to-end output attribution. Verify any specific statement before acting.*

<!-- COUNSEL-TBD — final wording subject to counsel sign-off. The current text is the working banner: it accurately distinguishes deterministic quantitative pipelines from LLM-generated qualitative content (covering both Parallax MCP services like news/macro/assessment and the orchestrating model), references the Provenance footer and trace ID for attribution, and avoids a methodology URL. Do not add a URL until counsel has signed off. The trace ID surface exists today; an end-to-end attribution API endpoint is in progress — when it lands, append a one-line "Resolve a trace ID at <url>" pointer here and the change propagates to all consumer skills via this single source of truth. -->

**Why §9.2 is mandatory:**

- **EU AI Act Art 50(1)** (effective 2 August 2026) — providers of AI systems generating synthetic content must mark outputs as artificially generated; the trace ID + Provenance footer satisfy this marking obligation.
- **EU AI Act Art 50(2)** — deployers of AI systems intended to interact directly with natural persons must inform users they are interacting with an AI; the "AI-assisted output" label satisfies this.
- **HKMA GenAI Circular (19 August 2024)** + **HKMA Consumer Protection circular on GenAI (7 November 2024)** — authorised institutions must disclose the purposes and limitations of GenAI in customer-facing applications, monitor outputs, and let customers opt out / request human intervention.
- **SFC Circular on Use of Generative AI Language Models (12 November 2024)** — for high-risk use cases (investment recommendations, advice, or research), licensed corporations must provide PROMINENT and CONTINUOUS disclosure that users are interacting with AI and that output may not be accurate. Parallax consumer-skill outputs fall in this high-risk category.
- **FCA Consumer Duty (PS22/9)** + **April 2025 FCA AI Update** + **PRIN 7** — the UK has no AI-specific rules; AI-generated client communications must satisfy the existing "clear, fair, and not misleading" obligation and Consumer Duty's consumer understanding outcome.
- **MAS FEAT principles** (2018, reaffirmed 2022) + **MAS AI Risk Management Guidelines** (consultation 13 November 2025 – 31 January 2026; final issuance expected 2026 with a 12-month transition period; AI Risk Management Toolkit published March 2026 under Project MindForge phase 2) — transparency required for customer-facing AI in financial advice and regulated activities.
- **SR 11-7** (US Fed model risk guidance) — conceptual-soundness implication: a client must be able to distinguish deterministic model output (CG scoring pipeline) from the LLM synthesis layer.

**§9.2 scope:** The §9.2 banner is **content-level** disclosure. **Firm-level UI obligations** — opt-out / human-intervention option (HKMA), prominent UI placement and continuous-disclosure cadence (SFC), accessibility considerations — remain the responsibility of the deploying institution and are NOT preempted by rendering §9.2 in skill output.

**Exemption:** Skills that produce configuration artifacts rather than direct client-facing analysis (currently `parallax-white-label-onboard` and `parallax-make-house-view`) are exempt from rendering §9.2. The rationale is narrow: such skills must (a) emit YAML/audit artifacts rather than a finished client deliverable, AND (b) gate any LLM-generated content behind an explicit operator confirmation step before that content can flow to downstream consumer skills. `parallax-white-label-onboard` qualifies because its Step 1.5 voice extraction is LLM-driven, but the resulting voice profile is reviewed and confirmed by the operator at Step 3 before being written to `~/.parallax/client-branding/` for downstream skills to consume — at which point the downstream skill renders §9.2 in its own output. `parallax-make-house-view` qualifies because it emits `view.yaml` + `prose.md` configuration artifacts whose LLM-synthesized content is gated by the shared Step 7 confirmation gate (`gate_present.py` — no save path bypasses it) before any downstream consumer can load the view — and every downstream consumer renders §9.2 in its own output per loader.md §5 rule 6. A future skill that emits LLM-generated content without an equivalent operator gate does NOT qualify for exemption, even if it produces "config" — the gate, not the artifact format, is the load-bearing condition. In particular, `parallax-judge-house-view` does NOT qualify: it emits an LLM-as-judge analysis report (not a config artifact) read directly by a natural person, so its report renders §9.2. Adding a skill to `_NINE_TWO_EXEMPT_SKILLS` in the test gate requires updating this exemption text in the same PR; entries are full skill directory names (`parallax-*`).

**Consumer skill reference pattern:** Skills MUST render the §9.2 banner by reference, not by inlining the text. Example Output Format directive: `Render AI-interaction disclosure per parallax-conventions.md §9.2 immediately above the disclaimer.` Inlining the banner text creates drift risk — when counsel finalizes the wording (or when the attribution API lands), the canonical §9.2 entry is edited once and all consumer skills propagate automatically.
