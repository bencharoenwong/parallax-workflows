---
name: parallax-AI-ptj
description: "Applies Paul Tudor Jones's trend-following + macro-overlay framework (per Schwager's 'Market Wizards', 1989) to evaluate single-stock technical setup, macroeconomic regime alignment, and volatility-driven risk/reward asymmetry. Evaluates ticker across three independent conviction channels (Technical, Macro, Volatility). Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized."
negative-triggers:
  - Bottom-up factor scoring → use /parallax-AI-buffett
  - Mechanical formula screen → use /parallax-AI-greenblatt
  - Balance-sheet-first checks → use /parallax-AI-klarman
  - Macro regime screening without ticker focus → use /parallax-macro-outlook
  - Cross-profile consensus → use /parallax-AI-consensus
  - Multiple tickers → use /parallax-AI-consensus
gotchas:
  - JIT-load _parallax/parallax-conventions.md, profile-schema.md, output-template.md, profiles/ptj.md
  - PTJ is single-ticker mode only — reject multiple tickers with redirect to AI-consensus
  - Channels T, M, V are evaluated independently; verdict requires 3 for match, 2 for partial
  - get_technical_analysis is async (~2-5s) — may time out; fallback to score_analysis Momentum proxy per §4
  - macro_analyst requires list_macro_countries first; cap at 3 markets (home + up to 2 exposure markets)
  - NEVER use first-person impersonation ("PTJ would buy"); always frame as "PTJ-style lens identifies" or "Profile flags"
  - Disclaimer verbatim per output-template.md, substituting "Paul Tudor Jones" for [Investor]
  - Cross-validation gate is NON-BYPASSABLE — symbol mismatch between get_company_info and get_peer_snapshot halts rendering
---

# Parallax AI PTJ Profile

Trend-following + macro-overlay framework: technical momentum validation → macro regime check → volatility-based risk/reward asymmetry assessment.

## Usage

```
/parallax-AI-ptj AAPL.O                    # single-ticker mode — tri-channel evaluation
/parallax-AI-ptj JPM.N                     # evaluate ticker for PTJ-style confluence
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools.

### Step 0 — JIT-load dependencies

Before the first Parallax tool call:

1. Load `skills/_parallax/parallax-conventions.md`
2. Load `skills/_parallax/AI-profiles/profile-schema.md`
3. Load `skills/_parallax/AI-profiles/output-template.md`
4. Load `skills/_parallax/AI-profiles/profiles/ptj.md`

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas.

### Step 1 — Parse input

Accept exactly one ticker. Reject multiple tickers: "PTJ profile evaluates single stocks. Use /parallax-AI-consensus for multi-ticker comparison."

Resolve RIC per `parallax-conventions.md §1`.

### Step 2 — Macro workflow setup

1. Call `list_macro_countries` to get covered markets (1 token).
2. Call `get_company_info` on input ticker to identify home market and sector (1 token).
3. From `list_macro_countries` response, identify home market (e.g., "United States" for US-listed, "Japan" for Japan-listed) plus up to 2 relevant exposure markets based on sector (e.g., "China" for semiconductors, "Saudi Arabia" for energy). Cap macro analyst calls at 3 markets.

### Step 3 — Core tri-channel batch (parallel)

Launch all 5 tools in parallel:

1. **`get_technical_analysis` on input ticker** (5 tokens, async ~2-5s)
   - Returns: trend direction (POSITIVE / STRONG_POSITIVE / NEUTRAL / NEGATIVE / etc.), momentum config, volatility regime, support/resistance levels, volume analysis
   - Used for Channel T evaluation

2. **`macro_analyst(component=tactical)` for home market** (5 tokens)
   - E.g., `macro_analyst(market="United States", component="tactical")`
   - Returns: tactical directional view (risk-on / risk-off / neutral), sector positioning, headwinds/tailwinds
   - Used for Channel M evaluation

3. **`get_score_analysis` on input ticker** (1 token)
   - Returns: 52-week factor trends including Momentum sub-trend (↑ / → / ↓)
   - Used for Channel T sub-signal validation (is momentum trending up?)

4. **`get_stock_outlook(aspect=risk_return)` on input ticker** (1 token)
   - Returns: analyst price target, upside %, downside %, risk score
   - Used for Channel V upside magnitude check

5. **`get_peer_snapshot` on input ticker** (1 token)
   - Returns: target_company (for cross-validation), Momentum factor score (0-10)
   - Used for Channel V momentum score check (>= 5 threshold)

**Note:** These are independent calls; batch them all together.

### Step 4 — Cross-validation gate

After `get_peer_snapshot` call completes, cross-check `target_company` (top-level field) against `get_company_info`'s `name` per `profile-schema.md §2 Step 2`.

If mismatch, emit standard error and halt rendering:
```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot returned: "<name_b>"
Cannot render PTJ-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

### Step 5 — Macro regime secondary (depends on Step 3 completion)

After `get_technical_analysis`, `get_score_analysis`, and `get_stock_outlook` complete, call `macro_analyst` for up to 2 additional exposure markets (based on sector). Fire these in parallel if more than one market is needed.

E.g., for semiconductor ticker, add `macro_analyst(market="Taiwan", component="tactical")` and optionally `macro_analyst(market="South Korea", component="tactical")`.

### Step 6 — Tri-channel evaluation

Evaluate all three channels using thresholds from `profiles/ptj.md`:

**Channel T — Technical setup:**
- **FLAGGED:** `get_technical_analysis.trend_direction` in [POSITIVE, STRONG_POSITIVE] AND `get_score_analysis.momentum_trend` is ↑ (upward)
- **PARTIAL:** Exactly one of the two sub-signals is positive (trend positive but momentum trend neutral, or trend neutral but momentum upward)
- **NOT_FLAGGED:** `get_technical_analysis.trend_direction` in [NEGATIVE, STRONG_NEGATIVE] or momentum trend is ↓
- **Fallback (if `get_technical_analysis` times out):** Use `get_peer_snapshot.Momentum` score >= 6 and `get_score_analysis.momentum_trend` = ↑; note "Technical analysis unavailable — Channel T uses factor proxy"

**Channel M — Macro regime:**
- **FLAGGED:** Home market `macro_analyst(tactical)` view is risk-on OR sector/company is explicitly noted in any exposure market's tactical themes (e.g., "financials benefiting from higher rates" and company is a major bank)
- **PARTIAL:** Macro view is neutral (neither risk-on nor risk-off) or mixed (some exposure markets favor, others don't)
- **NOT_FLAGGED:** Home market `macro_analyst` view is risk-off AND no exposure market themes favor the company's sector

**Channel V — Volatility and asymmetry:**
- **FLAGGED:** `get_stock_outlook(risk_return).analyst_upside_to_target` >= 15% AND `get_peer_snapshot.Momentum` factor score >= 5
- **PARTIAL:** Analyst upside in range 8-15% OR Momentum >= 5 but upside < 8%
- **NOT_FLAGGED:** Analyst upside < 8% OR Momentum < 5

### Step 7 — Verdict computation

- **match:** All 3 channels FLAGGED (Setup Grade A)
- **partial_match:** Exactly 2 channels FLAGGED (Setup Grade B) or 2 FLAGGED + 1 PARTIAL (Setup Grade B/C)
- **no_match:** 0-1 channels FLAGGED (Setup Grade C/D)

Assign setup quality:
- **Grade A:** 3 channels FLAGGED
- **Grade B:** 2 channels FLAGGED
- **Grade C:** 1 channel FLAGGED or 2+ PARTIAL
- **Grade D:** 0 channels FLAGGED

### Step 8 — Render through output template

```
PTJ-style profile applied to <ticker>

Source: Schwager, J. D. (1989). Market Wizards: Interviews with Top Traders.

Trend-following + macro-overlay framework: technical momentum validation → macro regime alignment → volatility-based asymmetry assessment.

Ticker exposure check (tri-channel):

  Channel T — Technical setup
    Trend direction: <POSITIVE / NEGATIVE / etc.>
    Momentum trend (52-week): <↑ / → / ↓>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED

  Channel M — Macro regime
    Home market: <market>
    Tactical view: <risk-on / risk-off / neutral>
    Sector alignment: <aligned / partial / misaligned>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED

  Channel V — Volatility and asymmetry
    Analyst upside to target: <X%>
    Momentum factor score: <score/10>
    Status: FLAGGED / PARTIAL / NOT_FLAGGED

Profile fit: <match / partial_match / no_match>
  - match: all three channels flagged (tri-channel alignment; high-conviction setup)
  - partial_match: two channels flagged (two-signal alignment; tactical entry possible)
  - no_match: zero or one channel flagged (insufficient confluence; capital preservation)

Setup quality: <Grade A / B / C / D>

Workflow derived from: Schwager (1989); Covel (2004).
Tool sequence: list_macro_countries, get_company_info, get_technical_analysis, macro_analyst × N (N ≤ 3), get_score_analysis, get_stock_outlook, get_peer_snapshot
Token cost: ~20-25 tokens (3 macro markets) / ~14-16 tokens (1 macro market)

---
This output is an AI-inferred interpretation of Paul Tudor Jones's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Paul Tudor Jones or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 9 — Emit

## Graceful fallback

**If `get_technical_analysis` times out (async tool):**
Evaluate Channel T using `get_peer_snapshot.Momentum` >= 6 AND `get_score_analysis.momentum_trend` = ↑. Note in output: "Channel T: Technical analysis unavailable — using factor proxy (Momentum score + trend direction)." Channel T maximum verdict remains FLAGGED/PARTIAL/NOT_FLAGGED based on proxy data.

**If `macro_analyst` fails for home market:**
Proceed with up to 2 exposure-market macro calls. If ≥1 succeeds, evaluate Channel M based on exposure markets. If all macro calls fail, Channel M is UNAVAILABLE (not NOT_FLAGGED). Maximum verdict becomes partial_match (single-channel + available channels).

**If `get_stock_outlook(risk_return)` fails:**
Channel V cannot be evaluated. Mark as UNAVAILABLE. Verdict maximum is partial_match if other channels succeed.

**If `get_peer_snapshot` fails (cross-validation blocking):**
Cannot complete cross-validation gate. Halt rendering with error message per Step 4.

**If all three channels return UNAVAILABLE:**
Halt rendering: "Insufficient data to evaluate PTJ-style framework. Service temporarily unavailable."
