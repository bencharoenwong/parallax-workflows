---
name: parallax-AI-buffett
description: "Applies the Buffett-style factor profile (per Frazzini-Kabiller-Pedersen 2018, 'Buffett's Alpha', FAJ), reconciled for 21st-century intangibles-heavy valuations per Lev-Srivastava 2022, to a single stock's current Parallax factor scores. Returns a match/partial/no-match verdict based on Quality, Value, Momentum, and Defensive factor criteria. Third-person framing, academic citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format."
negative-triggers:
  - Portfolio-level analysis → use /parallax-morning-brief or /parallax-portfolio-checkup
  - Full due diligence → use /parallax-due-diligence
  - Quick stock evaluation without a specific investor lens → use /parallax-should-i-buy
  - Peer comparison → use /parallax-peer-comparison
  - Running backtests → use /backtest
  - Other investor profiles → use /parallax-AI-soros, /parallax-AI-greenblatt, /parallax-AI-klarman
  - Cross-profile consensus → use /parallax-AI-consensus
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallbacks, and HK ambiguity protocol
  - JIT-load _parallax/AI-profiles/profile-schema.md for the dispatcher workflow and cross-validation gate
  - JIT-load _parallax/AI-profiles/output-template.md for the required output structure and disclaimer
  - JIT-load _parallax/AI-profiles/profiles/buffett.md for the profile spec (frontmatter + narrative)
  - Cross-validation gate (spec §6.4) is NON-BYPASSABLE — refuse to render on name mismatch
  - Disclaimer language is verbatim — do NOT paraphrase "not financial advice," "AI-inferred," or "consult a qualified financial advisor"
  - NEVER use first-person impersonation of Buffett — always frame as "Buffett-style" or "the BKP 2018 factor profile"
  - Profile is derived from public academic sources only (BKP 2018 + Lev-Srivastava 2022) — no private data, no get_assessment
  - Thresholds are calibrated for 21st-century intangibles-heavy valuations — KO/AXP return match, BRK parent and AAPL return partial (documented)
---

# Parallax AI Buffett Profile

Applies the Buffett-style factor profile documented in Frazzini, Kabiller, and Pedersen's 2018 *Financial Analysts Journal* paper "Buffett's Alpha" to a single stock's current Parallax factor scores.

## Usage

```
/parallax-AI-buffett AAPL
/parallax-AI-buffett BRK.B
/parallax-AI-buffett 005930.KS
```

Accepts plain tickers (auto-resolved to RIC via `get_company_info`) or RIC format directly.

## Workflow

Execute using `mcp__claude_ai_Parallax__*` tools. This dispatcher is generic — all differentiation for the Buffett profile lives in `skills/_parallax/AI-profiles/profiles/buffett.md`.

### Step 0 — JIT-load dependencies

Before the first Parallax tool call in the session:

1. Load `skills/_parallax/parallax-conventions.md` — RIC resolution, parallel execution, fallback patterns, HK ambiguity.
2. Load `skills/_parallax/AI-profiles/profile-schema.md` — dispatcher workflow + cross-validation gate.
3. Load `skills/_parallax/AI-profiles/output-template.md` — required output structure and disclaimer.
4. Load `skills/_parallax/AI-profiles/profiles/buffett.md` — Buffett profile spec.

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

### Step 1 — Resolve ticker

Use `get_company_info` with the input ticker. If empty, retry with exchange suffixes per shared conventions. For `.HK`/numeric codes, apply the HK ambiguity cross-check from conventions §2.

### Step 2 — Fire data calls in parallel

Once the RIC is confirmed, call all of the following simultaneously (per conventions §3):

| Tool | Parameters | Purpose |
|---|---|---|
| `get_peer_snapshot` | `symbol` | Factor sub-scores: quality, value, momentum, defensive |
| `get_financials` | `symbol`, `statement="summary"` | Revenue/income narrative for context |
| `get_score_analysis` | `symbol`, `weeks=52` | 52-week factor trend direction |

### Step 3 — Pre-render cross-validation gate (MANDATORY per spec §6.4)

After `get_peer_snapshot` returns, cross-check the `name` field returned by `get_peer_snapshot` against the `name` field returned by `get_company_info` for the same symbol.

**If names diverge:** refuse to render and emit exactly:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot returned:   "<name_b>"
Cannot render Buffett-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

Do not proceed to Step 4 on mismatch. This check is non-bypassable.

### Step 4 — Apply Buffett thresholds

From the profile spec `buffett.md` frontmatter, the thresholds are:

- Quality ≥ 7
- Value ≥ 6
- Momentum ≤ 6
- Defensive ≥ 6

For each factor, compare the score returned by `get_peer_snapshot` against the threshold. Record pass/fail per factor.

For any factor score in the threshold zone (≥7 or ≤3 — notably strong or weak), call `explain_methodology` for that factor to include the Parallax definition in the output. This is the pedagogy hook from spec §7 row 3.

### Step 5 — Compute verdict

Count passed factors (out of 4):
- **4 of 4 → `match`**
- **1-3 of 4 → `partial_match`** (specify the count, e.g., "2 of 4")
- **0 of 4 → `no_match`**

### Step 6 — Render through output template

Format the output per `skills/_parallax/AI-profiles/output-template.md`. The template requires, in order:

1. Header: `Buffett-style profile applied to <ticker>`
2. Citation block (full BKP 2018 citation + DOI)
3. Profile characterization statement (one sentence from the profile spec body)
4. Data table: Factor | Target | Score | 52-wk trend | Match
5. Verdict: "Profile fit: <match/partial/no> — N of 4 factor criteria met"
6. Methodology footer (workflow derivation, anchor-test date, legal-review date, tool sequence, token cost)
7. Standard disclaimer (VERBATIM — substitute `[Investor]` with `Warren Buffett` and nothing else)

### Step 7 — Emit

Output the rendered template. No additional commentary.

## Output example

```
Buffett-style profile applied to BRK.B

Source: Frazzini, A., Kabiller, D., Pedersen, L. H. (2018). Buffett's Alpha. Financial Analysts Journal, 74(4), 35-55.
(https://doi.org/10.2469/faj.v74.n4.3)

Frazzini, Kabiller, Pedersen (2018) decompose Berkshire Hathaway's 1976-2017 returns into factor exposures: strong Quality, strong Value, slight negative Momentum, positive Defensive (low-beta), with ~1.6x leverage overlay at portfolio level.

| Factor    | Target    | BRK.B score | 52-wk trend | Match |
|-----------|-----------|-------------|-------------|-------|
| Quality   | ≥ 7       | 8.1         | ↑ stable    | YES   |
| Value     | ≥ 6       | 6.8         | → stable    | YES   |
| Momentum  | ≤ 6       | 5.4         | → stable    | YES   |
| Defensive | ≥ 6       | 7.9         | ↑ stable    | YES   |

Profile fit: match — 4 of 4 factor criteria met.

Workflow derived from: Frazzini, Kabiller, Pedersen (2018), "Buffett's Alpha", FAJ 74(4):35-55.
Last anchor-tested: 2026-04-06 | Last legal review: PENDING
Tool sequence: get_company_info, get_peer_snapshot, get_financials(summary), get_score_analysis(52w), explain_methodology
Token cost: 4 tokens

---
This output is an AI-inferred interpretation of Warren Buffett's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Warren Buffett or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

Note: the 52-week trend column uses arrows (↑ up, ↓ down, → stable). The scores shown are illustrative — actual BRK.B scores will come from live Parallax data.

## Graceful fallback

Apply the graceful fallback patterns from `parallax-conventions.md §4`. If any required tool call fails after retry, mark the relevant section as "Data unavailable" and compute the verdict using available factors only. A verdict computed on <4 factors must be flagged as "partial data — N of M factor criteria available" and CANNOT be rendered as `match` even if all available factors pass. Consumers downstream (e.g., the Phase 3 consensus meta-skill) should treat such outputs as `partial_match` at best.
