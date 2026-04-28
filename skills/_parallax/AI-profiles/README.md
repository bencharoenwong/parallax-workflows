# Parallax AI Investor Profiles

Shared core for the `parallax-AI-*` skill family. Each profile is a markdown spec under `profiles/` that declares a workflow over Parallax MCP tools, anchored to a published academic paper or book, and consumed by a thin dispatcher skill at `skills/AI-<name>/SKILL.md`.

## What a profile is

A profile is **not** a celebrity impersonator. It is a **workflow specification** derived from a public source (academic paper, investor's own book, or equivalent) that applies that source's documented methodology to current Parallax data. The output is always framed in third person ("Buffett-style") and cites the source on every render.

## Inclusion criteria (hard gate)

A profile can ship ONLY if:

1. **Public anchor:** Peer-reviewed academic paper, the investor's own published book, or an equivalently concrete public document. NOT: interview clips, tweets, third-party profiles, or "commonly known style."
2. **Workflow specificity:** The anchor documents a concrete workflow (e.g., factor exposures, screening rules, decision process) that can be mechanically applied to Parallax data.
3. **Parallax tool coverage:** The workflow's data requirements can be satisfied by Parallax's public tools (no `get_assessment`, no `score_total`, no `get_stock_report`).
4. **Defensibility test:** If the named investor saw this profile, could they reasonably object that it misrepresents their approach? If yes, the profile is not ready. If the anchor is the investor's own book, this test is automatically passed.

## In-scope profiles (v1 — SHIPPED)

| Profile | Status | Anchor | Workflow shape |
|---|---|---|---|
| `buffett` | **SHIPPED** | Frazzini, Kabiller, Pedersen, "Buffett's Alpha", *FAJ* 2018; reconciled for 21st-century intangibles via Lev & Srivastava (2022) | Bottom-up single-stock; +Quality +Value −Momentum +Defensive |
| `greenblatt` | **SHIPPED** | Greenblatt, *The Little Book That Beats the Market* (2006); Gray & Carlisle, *Quantitative Value* (2012) | Mechanical screen: ROC + earnings yield → top-decile basket |
| `klarman` | **SHIPPED** | Klarman, *Margin of Safety* (1991) | Bottom-up special situations: balance sheet + cash rationality |
| `soros` | **SHIPPED** | Soros, *The Alchemy of Finance* (1987); Drobny, *Inside the House of Money* (2006) | Top-down macro → regime themes → dual-channel ticker exposure |
| `AI-consensus` | **SHIPPED** | Meta-skill | Runs all 4 profiles in parallel; surfaces super-majority signal + factor-level agreement |

## v1 token cost summary

| Skill | Typical cost per invocation |
|---|---|
| `parallax-AI-buffett` | ~4 tokens |
| `parallax-AI-greenblatt` (ticker-check) | ~10-15 tokens |
| `parallax-AI-greenblatt` (universe mode) | ~15-30 tokens |
| `parallax-AI-klarman` | ~5-7 tokens |
| `parallax-AI-soros` (single-ticker) | ~25-30 tokens |
| `parallax-AI-soros` (basket mode) | ~30-40 tokens |
| `parallax-AI-consensus` (single ticker) | ~45-55 tokens |
| `parallax-AI-consensus` (basket of 5) | ~150-200 tokens |

## In-scope v2 candidates (not implemented in v1)

- `munger` — anchor: *Poor Charlie's Almanack* (2005). Workflow: quality-first screen with higher moat threshold than Buffett.
- `lynch` — anchor: *One Up on Wall Street* (1989). Workflow: GARP screen using PEG ratio, sector rotation bias.

## Out of scope (insufficient public anchor)

- `druckenmiller` — no published factor decomposition or workflow document with comparable specificity to Soros's *Alchemy*. Revisit if such a source emerges.
- `burry` — concentrated distressed-value discretionary judgment. SEC filings show holdings but not a replicable workflow.
- `soros_specific_trades` — individual trade calls are not a systematic profile.
- `wood`, `ackman`, `dalio`, `marks`, `howard`, generic "hedge fund manager X" profiles — none meet the public-anchor test at the level of specificity required for mechanical replication.

Re-litigating any of the above requires a new public anchor that meets the inclusion criteria.

## How to add a new profile

1. Identify a public anchor meeting the inclusion criteria above.
2. Create `profiles/<name>.md` conforming to `profile-schema.md`.
3. Run the profile manually against the namesake's known holdings (anchor test). If the namesake's own holdings don't return `match`, the rubric is wrong — fix before proceeding.
4. Create `skills/AI-<name>/SKILL.md` as a thin dispatcher following the pattern in `skills/AI-buffett/SKILL.md`.
5. Commit profile + dispatcher together.
6. Update the "In-scope profiles" table in this README.

## Legal posture

Profiles are not gated on legal review before invocation. The disclaimer language in `output-template.md` does the legal work at runtime: "not financial advice," "AI-inferred from publicly available information," "consult a qualified financial advisor." Every profile output carries this disclaimer. Counsel review is a continuous quality process that may tighten wording but does not block the skills from running. See design spec §6.1 for rationale.

## Related files

- `profile-schema.md` — the YAML frontmatter contract every profile must conform to
- `output-template.md` — the required output structure, disclaimer, and citation format
- `consensus-config.md` — thresholds and applicable-count floor for the `parallax-AI-consensus` meta-skill
