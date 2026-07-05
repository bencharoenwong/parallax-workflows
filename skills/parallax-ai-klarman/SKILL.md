---
name: parallax-ai-klarman
description: "Applies Seth Klarman's margin-of-safety framework (per 'Margin of Safety', 1991) to a single stock's current financials via Parallax. Four balance-sheet checks: net cash position, debt vs peers, FCF stability, valuation discount. Includes a distinctive 'no position warranted; cash is valid' output when nothing qualifies. Third-person framing, book citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format. NOT for portfolio-level health check (use /parallax-portfolio-checkup). For all five profiles simultaneously use /parallax-ai-consensus."
---

<!-- white-label: integration-pattern.md -->

# Parallax AI Klarman Profile

## When not to use

- Bottom-up factor scoring → use /parallax-ai-buffett
- Mechanical formula screen → use /parallax-ai-greenblatt
- Top-down macro analysis → use /parallax-ai-soros
- Cross-profile consensus → use /parallax-ai-consensus
- Full due diligence → use /parallax-due-diligence
- Running backtests → use /backtest

## Gotchas

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
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (6-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (Provenance) in Output Format.

Applies Seth Klarman's margin-of-safety framework to a single stock's current balance sheet, cash flow, and peer-relative valuation.

## Usage

```
/parallax-ai-klarman AAPL.O
/parallax-ai-klarman BRKb.N
/parallax-ai-klarman 7203.T
```

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools.

### Step 0 — JIT-load dependencies

Before the first Parallax tool call:

1. Load `_parallax/parallax-conventions.md`
2. Load `_parallax/AI-profiles/profile-schema.md`
3. Load `_parallax/AI-profiles/output-template.md`
4. Load `_parallax/AI-profiles/profiles/klarman.md`

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

Verdict sensitivity: the check nearest its cutoff is <check> (<actual> vs <target>); the verdict moves to the adjacent tier if that check crosses its threshold, or if the Parallax Value backup score crosses 4.

[Optional: "No position warranted on this ticker per margin-of-safety principles. Cash is a valid stance."]

Workflow derived from: Klarman, S. (1991). Margin of Safety.
Last anchor-tested: 2026-04-07 (BRKb.N, NVDA.O) | Last legal review: pending
Tool sequence: get_company_info, get_peer_snapshot, get_financials(balance_sheet/cash_flow/ratios, 4 periods)
Token cost: ~5 tokens

---
This output is an AI-inferred interpretation of Seth Klarman's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Seth Klarman or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

### Step 7 — Emit


## Output additions (white-label branding + §9.2 disclosure)

These additions apply to the rendered output ABOVE in addition to the persona-specific disclaimer shown in the output example. They are required regardless of view state.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (Provenance) when composing the Output Format.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top of the rendered output: `**<client_name>** Klarman-style profile`. Logo handling per integration-pattern.md §5.
- **Provenance** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second Provenance line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. The persona-specific disclaimer in the output example characterizes the source of the framing; the §9.2 banner characterizes the LLM-generated synthesis itself.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Graceful fallback

If balance-sheet data is unavailable for 4 periods, compute the checks on whatever is available (minimum 2 periods) and flag the coverage loss. If peer-median data is unavailable, skip the debt-vs-peers check and note "Peer comparison unavailable — absolute thresholds applied." If all four checks fail due to missing data, return `DATA_UNAVAILABLE` rather than a false `no_match`.
