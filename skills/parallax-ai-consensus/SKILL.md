---
name: parallax-ai-consensus
description: "Runs all installed Parallax AI Investor Profiles (Buffett, Greenblatt, Klarman, Soros, PTJ) against a single ticker or short basket (cap 5). Returns the per-profile verdict matrix, the super-majority consensus signal per consensus-config.md, and a factor-level agreement detail showing which factors/criteria were flagged by multiple profiles. Cross-profile agreement is the strongest-agreement signal. Third-person framing throughout, AI-inferred from public information. NOT financial advice. NOT personalized. NOT for a single investor profile only (use /parallax-ai-buffett, /parallax-ai-greenblatt, /parallax-ai-klarman, /parallax-ai-soros, or /parallax-ai-ptj). NOT for portfolio-level health check (use /parallax-portfolio-checkup)."
---

<!-- white-label: integration-pattern.md -->

# Parallax AI Investor Profiles — Consensus Meta-Skill

## When not to use

- Single profile only → use /parallax-ai-buffett, /parallax-ai-greenblatt, /parallax-ai-klarman, /parallax-ai-soros, or /parallax-ai-ptj
- Broader macro outlook → use /parallax-macro-outlook
- Portfolio analysis → use /parallax-morning-brief or /parallax-portfolio-checkup
- Full due diligence → use /parallax-due-diligence
- Running backtests → use /backtest

## Gotchas

- Expected Parallax spend: ~60–70 tokens single ticker, ~180–240 for a basket of 5 (`_parallax/token-costs.md`).
- JIT-load `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/consensus-config.md`, and ALL profile specs under `_parallax/AI-profiles/profiles/` — Step 0.
- Do NOT re-implement profile logic — run each dispatcher's workflow as documented in `skills/parallax-ai-<name>/SKILL.md`. Cap basket input at 5 tickers.
- Super-majority uses ceiling rounding per consensus-config.md — `required = ceil(0.75 × applicable)`; partial matches do NOT count toward the signal but DO count toward factor-level agreement. Factor-level agreement is the highest-value section — never skip it.
- A profile that fails (cross-validation, timeout, missing data) is `skipped`; `INSUFFICIENT_PROFILES` when applicable < 3.
- Disclaimer verbatim with the umbrella phrasing "Parallax AI Investor Profiles framework".
- Apply `_parallax/white-label/integration-pattern.md` §2 (load), §5 (Branding Header), §7 (About This Report).

Runs all installed AI Investor Profiles in parallel against a ticker (or short basket), aggregates the verdicts, computes the super-majority consensus signal, and surfaces factor-level agreement detail.

## Usage

```
/parallax-ai-consensus AAPL.O                         # single ticker — all 5 profiles run
/parallax-ai-consensus BRKb.N,KO.N,AXP.N              # basket mode — cap 5 tickers
/parallax-ai-consensus --only buffett,greenblatt AAPL # subset (rare; min 3 still required)
```

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). This meta-skill runs each profile's dispatcher workflow; it never re-implements profile logic.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `load-reference` `_parallax/parallax-conventions.md`, `_parallax/AI-profiles/profile-schema.md`, `_parallax/AI-profiles/output-template.md`, `_parallax/AI-profiles/consensus-config.md`, ALL profile specs under `_parallax/AI-profiles/profiles/` (buffett, greenblatt, klarman, soros, ptj), and each dispatcher `skills/parallax-ai-<name>/SKILL.md` for workflow reference.
3. `discover-tools`: bind every tool in every profile's `tool_sequence` to the exact callable and schema exposed now.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
4. `load-reference` `_parallax/white-label/integration-pattern.md`; run §2 and record `white_label_active` + `client_name`.

### Step 1 — Resolve inputs

Single ticker → **single-ticker mode** (5 profiles applicable); 2–5 comma-separated → **basket mode**; > 5 → reject: "Consensus skill takes at most 5 tickers per call. Please split your request." `--only <profiles>` restricts the set (minimum 3). Resolve RICs per conventions §1; an unresolvable ticker exits with the §1 error and runs no profile.

### Step 2 — Fetch (parallel batches)

Run every applicable profile's dispatcher workflow in parallel where tool sequences do not share dependencies (never sequentialize): Buffett (info + snapshot + summary financials + score analysis, 4 thresholds); Greenblatt (info + sector-scoped universe + ratios for top 30 + rank); Klarman (info + snapshot + balance_sheet + cash_flow + ratios, 4 checks); Soros (macro countries + tactical × N + telemetry + info + universe per theme, dual channel; telemetry may be `UNAVAILABLE`); PTJ (macro countries + tactical × N + info + score analysis + technicals + risk_return outlook + snapshot, tri-channel). Rely on server defaults for `weeks`/`periods` or typed integers (conventions §0.2). Each returns `verdict` (`match` | `partial_match` | `no_match` | `skipped`), `verdict_detail`, `factor_flags` (factor → `FLAGGED` | `NOT_FLAGGED` | `NOT_APPLICABLE`), `fallback_notes`.

### Step 3 — Verify

Each profile runs its own cross-validation gate per `profile-schema.md §2 Step 2` (`get_peer_snapshot.target_company` vs `get_company_info.name`). A refusing profile is `skipped` and the meta-skill emits:

```
Warning: Profile <name> refused to render for <ticker> due to cross-validation failure. This profile is marked as `skipped` for this ticker. Proceeding with remaining applicable profiles.
```

No profile renders → `INSUFFICIENT_PROFILES`, no consensus.

### Step 4 — Compute

Per `consensus-config.md`: `A` = applicable (non-`skipped`) profiles; `M` = full `match` count; `required_matches = ceil(0.75 × A)`; signal `INSUFFICIENT_PROFILES` if `A < 3`, `YES` if `M ≥ required_matches`, else `NO`. Factor-level agreement: for each unique factor/criterion, count matching + partial profiles where it is `FLAGGED`, sort descending; buckets: **Shared signals** (≥ 2), **Single-profile signals** (1), **Absence signals** (flagged by none — the collective blind spot).

### Step 5 — Compose (render through the output template)


```
Parallax AI Investor Profiles — Consensus for <ticker>

Profiles run: <N> of <total installed>
<any skipped profiles and why>

## Per-profile verdict matrix

| Profile               | Verdict       | Detail                                    |
|-----------------------|---------------|-------------------------------------------|
| AI-buffett            | <verdict>     | <N of 4 factor criteria met>              |
| AI-greenblatt         | <verdict>     | <top X% of peer universe / no match>      |
| AI-klarman            | <verdict>     | <N of 4 balance-sheet checks passed>      |
| AI-soros              | <verdict>     | <dual-channel: A=<status> B=<status>>     |
| AI-ptj                | <verdict>     | <tri-channel: T=<status> M=<status> V=<status>> |

## Super-majority consensus signal

Applicable profiles (A): <count>
Full matches (M):        <count>
Super-majority threshold: 75%
Required matches:        ceil(0.75 × <A>) = <required>
Consensus signal:        YES / NO / INSUFFICIENT_PROFILES
Verdict sensitivity:     If signal is NO, M is <M> vs required <required>; <required − M> more applicable profile(s) reaching full match would move the signal to YES. If signal is YES, M is <M> vs required <required>; <M − required + 1> full match(es) falling away would move the signal to NO.

## Shared factor signal (factors/criteria flagged across profiles)

Informational per conventions §12 — a ranked agreement count, not a ranked trade instruction.

Factors flagged by ≥ 2 matching profiles:
  - <Factor>: flagged by <N> of <M> (<profile names>)
  - <Factor>: flagged by <N> of <M> (<profile names>)

Single-profile signals:
  - <Factor>: flagged by 1 profile (<profile name>)

NOT flagged by any matching profile (collective blind spot):
  - <Factor>: no profile currently flags this dimension

Interpretation: <2-3 sentence plain-language summary — where profiles
converge, where they diverge, what dimensions are collectively absent.>

## Methodology footer

Profiles executed: <list with token costs>
Total token cost: <sum>
Cross-validation gate: PASSED for all rendered profiles
Consensus config: 75% super-majority, minimum 3 applicable profiles, ceiling rounding

---
This output is an AI-inferred synthesis produced by the Parallax AI Investor Profiles framework. Each individual profile is derived solely from publicly available information — peer-reviewed academic sources or the investors' own published books, as cited per profile. It is not financial advice, not personalized, not endorsed by any of the named investors or their representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

**Basket mode output:** same structure per ticker, with the per-profile matrix, super-majority signal, and factor-level agreement computed per-ticker. Output is organized ticker-by-ticker.

### Step 6 — Render — Emit

**Steps 1–6 are silent.** Perform the profile runs, cross-validation, consensus computation, and factor-level agreement internally — none of that working appears in your reply. Your **entire visible response consists only of the rendered Step 6 template plus every required Output addition below**. The analytical template begins at the Header line `Parallax AI Investor Profiles — Consensus for <ticker>`; in basket mode, that Header begins each ticker block. Before the first analytical Header, render only the leading white-label elements required by `integration-pattern.md` §5, in its prescribed order, including a URL logo and the conditional Branding Header when applicable. If no leading white-label element applies, the analytical Header is the absolute first output. The About This Report footer, AI-interaction disclosure, and standard disclaimer remain required parts of the visible response in the positions specified below. In both modes, do NOT add `**Step N**` labels, "Cross-validation passed", "All data verified", a "Let me…" preamble, or any other workflow narration.


## Output additions (white-label branding + §9.2 disclosure)

These additions apply to the rendered output ABOVE in addition to the persona-specific disclaimer shown in the output example. They are required regardless of view state.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top of the rendered output: `**<client_name>** AI investor consensus`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): one line stating branding state per integration-pattern.md §7. If a logo was skipped, append `Logo on file: <basename>` as a second About This Report line.

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below. The persona-specific disclaimer in the output example characterizes the source of the framing; the §9.2 banner characterizes the LLM-generated synthesis itself.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.

## Failure modes


- 3 of 5 profiles run successfully → consensus proceeds with `A=3` (effectively requiring unanimity per ceiling rule)
- 2 of 5 profiles run successfully → return `INSUFFICIENT_PROFILES` (do NOT compute a 2-profile signal)
- Any single profile's tool calls fail after retry → that profile is `skipped` (with fallback note) and consensus continues
- Input ticker not resolvable → emit standard conventions §1 error and exit, do not run profiles

Token costs per profile and for the basket: `_parallax/token-costs.md` → "AI investor profile workflows" (single source). The `--only buffett,klarman,greenblatt` subset is the cheap ensemble (A = 3 → all three must match for `YES`); label its output a reduced-ensemble read.

## Why this meta-skill exists

The consensus is the product's value proposition, not a convenience feature. Individual profiles are interesting but noisy — each reflects a single investor's framework and may flag for reasons unrelated to the investor's actual behavior today. Cross-profile consensus is informative precisely because the profiles are structurally different: Buffett is factor-tilted, Greenblatt is mechanical, Klarman is balance-sheet, Soros is top-down, PTJ is trend-and-regime. When four or five agree, the agreement is unlikely coincidental.

The factor-level agreement section is pedagogically load-bearing. It tells users:
- **Where the profiles converge** (the strongest-agreement shared signal)
- **Where they diverge** (informative tension)
- **What dimensions are collectively absent** (the profiles' shared blind spots)

This gives users a framework for building their own views using Parallax data — the stated product goal.


## Done when

- The reply begins at the analytical Header (or the white-label header when active) and contains only the rendered template plus the Output additions; no workflow narration.
- The cross-validation gate passed, or the exact refusal message was emitted and nothing else rendered.
- The verdict line, the citation, the methodology footer with tool sequence and token cost, the persona disclaimer verbatim, `parallax-conventions.md §9.2` disclosure and the §9.1 disclaimer are present.
- Expected spend stated (Gotchas).
