---
name: parallax-AI-klarman
description: "Applies Seth Klarman's margin-of-safety framework (per 'Margin of Safety', 1991) to a single stock's current financials via Parallax. Four balance-sheet checks: net cash position, debt vs peers, FCF stability, valuation discount. Includes a distinctive 'no position warranted; cash is valid' output when nothing qualifies. Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized."
negative-triggers:
  - Bottom-up factor scoring → use /parallax-AI-buffett
  - Mechanical formula screen → use /parallax-AI-greenblatt
  - Top-down macro analysis → use /parallax-AI-soros
  - Cross-profile consensus → use /parallax-AI-consensus
  - Full due diligence → use /parallax-due-diligence
  - Running backtests → use /backtest
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallback patterns
  - JIT-load _parallax/AI-profiles/profile-schema.md and output-template.md
  - JIT-load _parallax/AI-profiles/profiles/klarman.md for the profile spec
  - Klarman profile is balance-sheet-first — requires get_financials(balance_sheet) AND get_financials(cash_flow) AND get_financials(ratios), 4 periods each
  - 3 statements × 4 periods would be 12 calls, but Parallax returns 4 periods per call → 3 calls + get_peer_snapshot + get_company_info = ~5 tokens
  - Compute net cash from balance sheet (cash - total debt), not from the ratios summary
  - The "no position warranted" output IS valid output — do not treat it as a failure
  - NEVER use first-person impersonation; always "Klarman-style"
  - Disclaimer verbatim per output-template.md, substituting "Seth Klarman" for [Investor]
  - Value threshold is intentionally loose (≥ 4) per Lev-Srivastava 2022 intangibles caveat — do not tighten without re-anchoring
---

# Parallax AI Klarman Profile

Applies Seth Klarman's margin-of-safety framework to a single stock's current balance sheet, cash flow, and peer-relative valuation.

## Usage

```
/parallax-AI-klarman AAPL.O
/parallax-AI-klarman BRKb.N
/parallax-AI-klarman 7203.T
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools.

### Step 0 — JIT-load dependencies

Before the first Parallax tool call:

1. Load `skills/_parallax/parallax-conventions.md`
2. Load `skills/_parallax/AI-profiles/profile-schema.md`
3. Load `skills/_parallax/AI-profiles/output-template.md`
4. Load `skills/_parallax/AI-profiles/profiles/klarman.md`

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas.

### Step 1 — Resolve ticker

Per shared conventions (RIC suffix table in `parallax-conventions.md §1`).

### Step 2 — Fire data calls in parallel

| Tool | Parameters | Purpose |
|---|---|---|
| `get_company_info` | `symbol` | Sector, market cap, for peer group selection |
| `get_peer_snapshot` | `symbol` | Factor sub-scores (Value used as backup check) |
| `get_financials` | `symbol`, `statement=balance_sheet` | Cash, total debt, equity (4 periods default) |
| `get_financials` | `symbol`, `statement=cash_flow` | FCF across 4 periods (default) |
| `get_financials` | `symbol`, `statement=ratios` | D/E, P/E, peer medians where available (4 periods default) |

**IMPORTANT — MCP parameter serialization:** Do NOT pass numeric parameters like `periods=4` as explicit arguments via the `:periods=4` syntax — the MCP transport serializes them as strings, causing "Expected number, received string" validation errors. The server default is 4 periods; rely on it or pass as a properly-typed integer at the individual tool-call site.

### Step 3 — Pre-render cross-validation gate (MANDATORY per spec §6.4)

After `get_peer_snapshot` returns, cross-check its `target_company` field (NOT `name` — that field on individual peer rows refers to each peer, not the target) against `get_company_info`'s `name`. On mismatch, refuse to render and emit:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot target_company: "<name_b>"
Cannot render Klarman-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

### Step 4 — Compute the four Klarman checks

**Check 1: Net cash position**
- Net cash = (cash and equivalents) − (total debt), from most recent balance sheet
- Net cash ratio = net cash / market cap (from get_company_info)
- **PASS** if net cash ratio ≥ 0 (positive net cash)
- **PARTIAL** if ≥ −0.2 (small, manageable net debt)
- **FAIL** if < −0.2 (meaningful net debt)

**Check 2: Debt vs peer median**
- D/E from the ratios call, most recent period
- Compare against peer median D/E from the peer snapshot
- **PASS** if D/E ≤ peer median × 1.1
- **FAIL** otherwise
- If peer median D/E is unavailable, flag "Peer comparison unavailable — check computed on absolute D/E < 1.0 as fallback"

**Check 3: FCF stability**
- Count periods (of 4) where free cash flow was positive
- **PASS** if ≥ 3 of 4
- **PARTIAL** if 2 of 4
- **FAIL** if ≤ 1 of 4

**Check 4: Valuation discount**
- P/E vs peer median P/E (fallback: P/B if negative earnings make P/E meaningless)
- **PASS** if stock P/E ≤ peer median P/E × 0.85 (15%+ discount)
- **PARTIAL** if stock P/E ≤ peer median × 1.0 (at peer)
- **FAIL** if stock P/E > peer median × 1.0

**Backup: Parallax Value sub-score**
- Sanity check, not a primary criterion
- Threshold: ≥ 4 (loose per Lev-Srivastava 2022 intangibles caveat)
- If Value < 4, flag in output: "⚠️ Parallax Value sub-score suggests valuation may not be attractive even if peer-relative metrics pass"

### Step 5 — Compute verdict

Let `N` be the count of PASSing balance-sheet checks (0-4).

- **N ≥ 3 AND Value ≥ 4 → `match`**
- **N ≥ 3 AND Value < 4 → `partial_match`** — balance sheet qualifies but Parallax Value backup fails. Flag in output: "strong balance sheet but absolute Parallax Value below backup threshold — intangibles-era calibration caveat applies."
- **N = 2 → `partial_match`**
- **N ≤ 1 → `no_match`**

If **N = 0** AND Value < 4, append the distinctive footer: *"No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance."* (This is the explicit "do nothing" output from the profile body.)

### Step 6 — Render through output template

```
Klarman-style profile applied to <ticker>

Source: Klarman, S. (1991). Margin of Safety: Risk-Averse Value Investing Strategies for the Thoughtful Investor.

Klarman's framework prioritizes survival over return: balance-sheet strength, downside protection via valuation discount, and willingness to hold cash when nothing qualifies.

| Check                        | Target                    | Actual              | Result  |
|------------------------------|---------------------------|---------------------|---------|
| Net cash position            | Net cash ratio ≥ 0        | <value>             | PASS/PARTIAL/FAIL |
| Debt vs peer median          | D/E ≤ peer median × 1.1   | <value> vs <peer>   | PASS/FAIL |
| FCF stability                | Positive ≥ 3 of 4 periods | <count> of 4        | PASS/PARTIAL/FAIL |
| Valuation discount           | P/E ≤ peer median × 0.85  | <value> vs <peer>   | PASS/PARTIAL/FAIL |

Parallax Value sub-score (backup check): <score> / 10

Profile fit: <match / partial_match / no_match> — <count> of 4 checks passed.

[Optional: "No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance."]

Workflow derived from: Klarman, S. (1991). Margin of Safety.
Last anchor-tested: <date> | Last legal review: <date>
Tool sequence: get_company_info, get_peer_snapshot, get_financials(balance_sheet/cash_flow/ratios, 4 periods)
Token cost: ~5 tokens

---
This output is an AI-inferred interpretation of Seth Klarman's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Seth Klarman or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 7 — Emit

## Graceful fallback

If balance-sheet data is unavailable for 4 periods, compute the checks on whatever is available (minimum 2 periods) and flag the coverage loss. If peer-median data is unavailable, skip the debt-vs-peers check and note "Peer comparison unavailable — absolute thresholds applied." If all four checks fail due to missing data, return `DATA_UNAVAILABLE` rather than a false `no_match`.
