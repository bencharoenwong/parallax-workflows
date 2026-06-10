# Parallax AI Investor Profile — Output Template

This file is JIT-loaded by every `skills/parallax-ai-<name>/SKILL.md` dispatcher. It defines the REQUIRED structure of any profile's output. No profile may deviate from this structure. No profile may remove or soften the disclaimer language.

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

### 7. Methodology footer

```
Workflow derived from: <citation>
Last anchor-tested: <last_anchor_test> | Last legal review: <last_legal_review>
Tool sequence: <tool_sequence from profile frontmatter>
Token cost: <N> tokens
```

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

## Why this template is centralized

Per spec §4 and §6.1: the disclaimer is the legal mitigation. Centralizing it means counsel reviews the language once (not N times per profile) and every profile inherits any future tightening automatically. A profile cannot accidentally drift from the approved language because the profile does not control the template.
