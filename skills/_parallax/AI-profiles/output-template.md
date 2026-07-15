# Parallax AI Investor Profile — Output Template

This file is JIT-loaded by every `skills/parallax-ai-<name>/SKILL.md` dispatcher. It defines the REQUIRED structure of any profile's output. No profile may deviate from this structure. No profile may remove or soften the disclaimer language.

Scope note: This profile family is skill-prose orchestration for interactive assistant sessions only; it has no structured/API output contract (see `parallax-conventions.md` §7, multi-stock table). Do not represent profile output as an embeddable API surface.

## Required output structure

Every profile rendering MUST include, in order:

### 1. Header

```
<display_name> profile applied to <ticker>
```

Example: `Buffett-style profile applied to AAPL.O`

### 2. Citation block

```
Source: <citation>
(<doi_or_url>)
```

Full citation from the profile's `public_anchor.citation` frontmatter field. URL on second line if available.

### 3. Profile characterization statement

One sentence stating what the cited source documents. Example:

> Frazzini, Kabiller, Pedersen (2018) decompose Berkshire Hathaway's 1976-2017 returns into factor exposures: strong Quality, strong Value, and positive Defensive (low-beta), with ~1.6x leverage overlay at portfolio level (momentum is not a meaningful part of the profile).

### 4. Data table (for factor-driven profiles)

Markdown table with columns: Factor | Profile target | Actual score | Trend | Match.

For profiles with non-factor logic (Greenblatt, Klarman, Soros), substitute the relevant data structure (rank table for Greenblatt; balance-sheet checklist for Klarman; theme-exposure table for Soros).

### 5. Verdict

Exactly one of:
- `Profile fit: match` — with count, e.g., "4 of 4 factor criteria met"
- `Profile fit: partial match` — with count, e.g., "2 of 4 factor criteria met"
- `Profile fit: no match` — with explanation

**FORBIDDEN verdict language:** "buy", "sell", "recommend", "would buy", "endorses", "rates", "likes", "hates", any first-person impersonation. See spec §5.

### 6. Synthesis (REQUIRED where the profile spec specifies it)

One to two sentences naming which legs of the profile the stock fits and which it misses, ending with a one-line takeaway. Required for every verdict — including `match`, which is not self-explanatory: state *why* the cluster fits (e.g., "cheap, high-quality, low-beta — the cluster the anchor attributes the investor's alpha to") rather than leaving a bare data table. This is the one interpretive sentence the dispatcher is permitted to write; it must restate the table and verdict, not introduce new claims, opinions, or recommendation language. Profiles whose `SKILL.md` does not call for a Synthesis section omit it.

### 6.5. Verdict sensitivity (conditionally REQUIRED — gate below)

Directly below the Synthesis section (or below the Verdict, for profiles that omit Synthesis), render one line labeled **"Verdict sensitivity"** stating, in third person and grounded purely in arithmetic, which 1-2 factor inputs sit nearest their published threshold and what would flip the verdict. The full principle, qualification gate, distance-0 rule, and forbidden-language list live in `parallax-conventions.md` §11 — render by reference; do not inline that prose here.

**Gate — which profiles render this line:**

| Profile | Renders? | Why |
|---|---|---|
| `parallax-ai-buffett` | YES | Four fixed numeric cutoffs (Quality ≥ 5, Value ≥ 4, Momentum ≤ 6, Defensive ≥ 7) — clean arithmetic distance per factor. |
| `parallax-ai-greenblatt` | YES | Verdict is a percentile-rank cutoff (top 10% / top 25%) on the combined ROC + earnings-yield rank — a published numeric boundary. |
| `parallax-ai-klarman` | YES | Verdict is a pass-count threshold (N ≥ 3 of 4 checks, Value ≥ 4 backup) over four numerically-defined checks — clean arithmetic distance. |
| `parallax-ai-soros` | NO — omit | Dual-channel FLAGGED / NOT_FLAGGED / UNAVAILABLE (industry membership + telemetry basket). Neither channel has a numeric cutoff to measure distance from — forcing one would violate §11.2. If a sensitivity-style line is wanted, state the discrete criterion that would flip it (e.g., "Channel B would need to surface a basket match for `<ticker>`") — never a fabricated number. |
| `parallax-ai-ptj` | NO — omit | Channel status (T/M/V) is a compound discrete evaluation (trend-direction category AND momentum-trend direction, or a risk-on/risk-off categorical macro read), even though individual sub-signals carry numeric cutoffs. Do not cherry-pick one sub-signal to represent the whole channel's status. |
| `parallax-ai-consensus` | YES — meta-level only | The consensus signal itself is a clean numeric threshold: `required_matches = ceil(0.75 × A)` compared against `M`. Render Verdict sensitivity on the super-majority signal (e.g., "M is 3 vs required 4 for A = 5 — one more applicable profile reaching full match would move the signal to YES"; if already YES, state how many full matches could fall away before the signal drops to NO), never on the underlying Soros / PTJ rows inside the per-profile matrix — the omit rule above still applies to those two rows. |

**Non-negotiable:** never fabricate a flip threshold for a profile or channel that has no published numeric cutoff. Omitting the line for Soros and PTJ is the compliant behavior, not a gap to fill.

### 7. Methodology footer

```
Workflow derived from: <citation>
Last anchor-tested: <last_anchor_test>
Tool sequence: <tool_sequence from profile frontmatter>
Token cost: <N> tokens
```

Render rule: append ` | Last legal review: <date>` to the `Last anchor-tested` line ONLY when the profile's `last_legal_review` frontmatter value is a completed date. `PENDING` is an internal tracking state — the `profiles/*.md` frontmatter field stays REQUIRED and unchanged, but `PENDING` is never rendered in output; omit the field entirely rather than printing "pending".

### 8. Standard disclaimer (REQUIRED, VERBATIM)

Every profile output MUST end with this exact disclaimer. Substitute `[Investor]` with the named investor (e.g., "Warren Buffett"). No other substitutions are permitted. The phrases "AI-inferred," "solely from publicly available information," "not financial advice," and "consult a qualified financial advisor" are load-bearing and MUST NOT be removed, softened, or replaced:

```
---
This output is an AI-inferred interpretation of [Investor]'s approach, derived solely from publicly available information — the cited source, Parallax factor data, and Parallax's public methodology. It is produced by the Parallax AI Investor Profiles framework. It is not financial advice, not personalized, not endorsed by [Investor] or their representatives, and not a recommendation to buy or sell any security. For illustrative and educational use only. Past characterization does not guarantee future relevance. Please consult a qualified financial advisor before making investment decisions.
```

## Rendering rules

1. **Cross-validation gate first.** Before rendering anything, the dispatcher must have passed the pre-render cross-validation check from `profile-schema.md §2 Step 2`. The output template never receives an unverified payload.
2. **No freelancing.** The dispatcher fills in data; it does not add opinions, extra context, or "helpful clarifications" beyond what the profile spec specifies. The §6 Synthesis sentence is the sole exception, and only where the profile's `SKILL.md` requires it — it must restate the table and verdict, never introduce a new claim or recommendation.
3. **Citation mandatory.** A profile without a valid `public_anchor.citation` cannot render. This is checked at dispatcher load time.
4. **Disclaimer is verbatim.** The dispatcher substitutes `[Investor]` and nothing else. The rest of the disclaimer is copy-pasted verbatim.
5. **Third person only.** Nothing in the output may paraphrase, quote, or speak as the investor. "Buffett-style" is allowed. "Buffett would say" is not.
6. **Legal-review render gate.** The footer's `Last legal review` field renders only when `last_legal_review` in the profile frontmatter is a completed date; `PENDING` renders nothing. See `methodology-faq.md` for the compliance-facing rationale on named-investor framing and review status.

### Audience render mode (conventions §13 by reference)

Apply audience render mode per `parallax-conventions.md` §13. Under `client_safe`, the §4 data table's factor rows carry the §13.3 plain-language gloss; the §6.5 Verdict-sensitivity line is omitted, while the §6.5 gate table itself is unchanged because qualification logic is not a render decision. The §7 methodology footer renders only `Workflow derived from: <citation>` and `Last anchor-tested: <date>` plus the legal-review date when completed; `Tool sequence` and `Token cost` lines are omitted.

The §2 citation block, §5 verdict, and §8 verbatim disclaimer render identically in both modes. The disclaimer is never suppressible.

## Why this template is centralized

Per spec §4 and §6.1: the disclaimer is the legal mitigation. Centralizing it means counsel reviews the language once (not N times per profile) and every profile inherits any future tightening automatically. A profile cannot accidentally drift from the approved language because the profile does not control the template.
