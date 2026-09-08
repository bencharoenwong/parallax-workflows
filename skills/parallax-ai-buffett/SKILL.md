---
name: parallax-ai-buffett
description: "Applies the Buffett-style factor profile (per Frazzini-Kabiller-Pedersen 2018, 'Buffett's Alpha', FAJ), reconciled for 21st-century intangibles-heavy valuations per Lev-Srivastava 2022, to a single stock's current Parallax factor scores. Returns a match/partial/no-match verdict based on Quality, Value, Momentum, and Defensive factor criteria. Third-person framing, academic citation, AI-inferred from public information. NOT financial advice. NOT personalized. Accepts plain tickers or RIC format. NOT for portfolio-level health check (use /parallax-portfolio-checkup). Other lenses: /parallax-ai-greenblatt, /parallax-ai-klarman, /parallax-ai-soros, /parallax-ai-ptj. For all five profiles simultaneously use /parallax-ai-consensus."
---

<!-- white-label: integration-pattern.md -->

# Parallax AI Buffett Profile

## When not to use

- Portfolio-level analysis → use /parallax-morning-brief or /parallax-portfolio-checkup
- Full due diligence → use /parallax-due-diligence
- Quick stock evaluation without a specific investor lens → use /parallax-should-i-buy
- Peer comparison → use /parallax-peer-comparison
- Running backtests → use /backtest
- Other investor profiles → use /parallax-ai-greenblatt, /parallax-ai-klarman, /parallax-ai-soros, /parallax-ai-ptj
- Cross-profile consensus → use /parallax-ai-consensus

## Gotchas

- Expected Parallax spend: ~4 tokens (`_parallax/token-costs.md`).
- JIT-load `_parallax/parallax-conventions.md` (§0.0, §0.2 typed integers, §1, §2, §3, §4, §14), `_parallax/AI-profiles/profile-schema.md` (dispatcher contract + cross-validation gate), `_parallax/AI-profiles/output-template.md` (output structure + verbatim disclaimer), `_parallax/AI-profiles/profiles/buffett.md` (profile spec) — Step 0.
- Cross-validation gate (spec §6.4) is NON-BYPASSABLE — refuse to render on name mismatch.
- Disclaimer language is verbatim — do NOT paraphrase "not financial advice," "AI-inferred," or "consult a qualified financial advisor".
- NEVER use first-person impersonation of Buffett — always "Buffett-style" or "the BKP 2018 factor profile".
- Profile is derived from public academic sources only (BKP 2018 + Lev-Srivastava 2022) — no private data, no `get_assessment`.
- Thresholds are calibrated for 21st-century intangibles-heavy valuations — KO/AXP return match, BRK parent and AAPL return partial (documented); do not tighten without re-anchoring.
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Applies the Buffett-style factor profile documented in Frazzini, Kabiller, and Pedersen's 2018 *Financial Analysts Journal* paper "Buffett's Alpha" to a single stock's current Parallax factor scores.

## Usage

```
/parallax-ai-buffett AAPL
/parallax-ai-buffett BRKb.N
/parallax-ai-buffett 005930.KS
```

Accepts plain tickers (auto-resolved to RIC via `get_company_info`) or RIC format directly.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This dispatcher is generic — all differentiation lives in the profile spec; the contract is `_parallax/AI-profiles/profile-schema.md` §2.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/profiles/buffett.md`.
3. `discover-tools`: bind every tool in the profile's `tool_sequence` to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

`call-tool` `get_company_info` with the input ticker. If empty, retry with exchange suffixes per conventions §1; for `.HK`/numeric codes apply the §2 ambiguity cross-check.

### Step 2 — Fetch (parallel batches)

Once the RIC is confirmed, `call-tool` together (conventions §3):

| Tool | Parameters | Purpose |
|---|---|---|
| `get_peer_snapshot` | `symbol` | Factor sub-scores: quality, value, momentum, defensive |
| `get_financials` | `symbol` (statement defaults to "summary") | Revenue/income narrative for context |
| `get_score_analysis` | `symbol` (weeks defaults to 52) | 52-week factor trend direction |

Rely on server defaults for `weeks`/`periods`, or pass a typed integer at the call site (conventions §0.2) — a string-serialized number fails validation.

### Step 3 — Verify

**Cross-validation gate (MANDATORY per spec §6.4).** Cross-check `get_peer_snapshot.target_company` (top level; the response has no `name` field — each peer's name is `comparison[].company`) against `get_company_info.name`, normalized per conventions §2 step 2. On divergence refuse to render and emit exactly:

```
Error: Symbol cross-validation failed for <ticker>.
  get_company_info returned: "<name_a>"
  get_peer_snapshot target_company: "<name_b>"
Cannot render Buffett-style profile — possible wrong-company mapping (see parallax-conventions.md §2).
```

Do not proceed on mismatch. Any tool that fails after the §0.1 retry: mark its section "Data unavailable" (§4).

### Step 4 — Compute

Thresholds from `buffett.md` frontmatter (tuned 2026-04-06 from the anchor test): Quality ≥ 5; Value ≥ 4; Momentum ≤ 6; Defensive ≥ 7. Compare each `get_peer_snapshot` score, record pass/fail. For any score ≥ 7 or ≤ 3, `call-tool` `explain_methodology` for that factor (the pedagogy hook, spec §7 row 3). Verdict: 4 of 4 → `match`; 1–3 of 4 → `partial_match` (state the count); 0 of 4 → `no_match`. A verdict computed on fewer than 4 available factors is flagged "partial data — N of M factor criteria available" and can never be `match`.

### Step 5 — Compose (render through the output template)


Format the output per `_parallax/AI-profiles/output-template.md`. The template requires, in order:

1. Header: `Buffett-style profile applied to <ticker>`
2. Citation block (full BKP 2018 citation + DOI)
3. Profile characterization statement (one sentence from the profile spec body)
4. Data table: Factor | Target | Score | 52-wk trend | Match
5. Verdict: "Profile fit: <match/partial/no> — N of 4 factor criteria met"
6. **Synthesis (REQUIRED for every verdict, including `match`)** — 1-2 sentences naming which legs of the BKP-2018 Buffett profile the stock fits and which it misses, with the one-line takeaway. A `match` is not self-explanatory: state *why* (e.g. "cheap, high-quality, low-beta — the cluster BKP attribute Berkshire's alpha to"). Do not leave a `match` as a bare table.
7. Methodology footer (workflow derivation, anchor-test date, legal-review date — renders only once completed, tool sequence, token cost)
8. Standard disclaimer (VERBATIM — substitute `[Investor]` with `Warren Buffett` and nothing else)

### Step 6 — Render — Emit

**Steps 1–6 are silent.** Perform the ticker resolution, cross-validation, scoring, threshold logic, and verdict computation internally — none of that working appears in your reply. Your **entire visible response consists only of the rendered Step 6 template plus every required Output addition below**. The analytical template begins at the Header line `Buffett-style profile applied to <ticker>`. Before it, render only the leading white-label elements required by `integration-pattern.md` §5, in its prescribed order, including a URL logo and the conditional Branding Header when applicable. If no leading white-label element applies, the analytical Header is the absolute first output. The About This Report footer, AI-interaction disclosure, and standard disclaimer remain required parts of the visible response in the positions specified below. Do NOT add `**Step N**` labels, "Cross-validation passed", "All data verified", a "Let me…" preamble, or any other workflow narration.

## Output example

```
Buffett-style profile applied to KO.N

Source: Frazzini, A., Kabiller, D., Pedersen, L. H. (2018). Buffett's Alpha. Financial Analysts Journal, 74(4), 35-55.
(https://doi.org/10.2469/faj.v74.n4.3)

Frazzini, Kabiller, Pedersen (2018) decompose Berkshire Hathaway's 1976-2017 returns into factor exposures: strong Quality, strong Value, and positive Defensive (low-beta), with ~1.6x leverage overlay at portfolio level (momentum is not a meaningful part of the profile).

| Factor    | Target    | KO.N score | 52-wk trend | Match |
|-----------|-----------|------------|-------------|-------|
| Quality   | ≥ 5       | 8          | ↑ stable    | YES   |
| Value     | ≥ 4       | 4          | → stable    | YES   |
| Momentum  | ≤ 6       | 4.83       | → stable    | YES   |
| Defensive | ≥ 7       | 10         | ↑ stable    | YES   |

Profile fit: match — 4 of 4 factor criteria met.

**Synthesis:** KO fits all four legs of the BKP-2018 profile — high-quality (Quality 8), reasonably priced (Value 4), low-momentum (4.83), and strongly low-beta (Defensive 10) — the cheap-safe-quality cluster the paper attributes Berkshire's alpha to. It sits at the quality-and-safety end of that style rather than deep value.

Verdict sensitivity: Value 4 is at the ≥ 4 boundary; the verdict drops from match to partial (3 of 4) if Value falls below 4. The next-nearest input, Momentum 4.83 against the ≤ 6 ceiling, has 1.17 points of headroom.

Workflow derived from: Frazzini, Kabiller, Pedersen (2018), "Buffett's Alpha", FAJ 74(4):35-55.
Last anchor-tested: 2026-04-06 (KO.N, AXP.N)
Tool sequence: get_company_info, get_peer_snapshot, get_financials(summary), get_score_analysis(52w), explain_methodology
Token cost: 4 tokens

---
This output is an AI-inferred interpretation of Warren Buffett's approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by Warren Buffett or his representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

Note: the 52-week trend column uses arrows (↑ up, ↓ down, → stable). The scores shown above are from the KO.N anchor test (2026-04-06); actual scores at invocation time come from live Parallax data. The Synthesis and Verdict sensitivity sentences illustrate required content and length only — write fresh wording keyed to the actual verdict and scores at invocation time, not a paraphrase of this example.


## Output additions (white-label branding + §9.2 disclosure)

These additions apply to the rendered output ABOVE in addition to the persona-specific disclaimer shown in the output example. They are required regardless of view state.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top of the rendered output: `**<client_name>** Buffett-style profile`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. The persona-specific disclaimer in the output example characterizes the source of the framing; the §9.2 banner characterizes the LLM-generated synthesis itself.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Failure modes


Apply the graceful fallback patterns from `parallax-conventions.md §4`. If any required tool call fails after retry, mark the relevant section as "Data unavailable" and compute the verdict using available factors only. A verdict computed on <4 factors must be flagged as "partial data — N of M factor criteria available" and CANNOT be rendered as `match` even if all available factors pass. Consumers downstream (e.g., the /parallax-ai-consensus meta-skill) should treat such outputs as `partial_match` at best.


## Done when

- The reply begins at the analytical Header (or the white-label header when active) and contains only the rendered template plus the Output additions; no workflow narration.
- The cross-validation gate passed, or the exact refusal message was emitted and nothing else rendered.
- The verdict line, the citation, the methodology footer with tool sequence and token cost, the persona disclaimer verbatim, `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
