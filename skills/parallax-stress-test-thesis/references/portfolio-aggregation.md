# Phase 6 — Cross-thesis (book-level) aggregation

Loaded **only when more than one thesis was supplied** in the same run (a book of arguments). Single
thesis → this phase never runs and no book-level section renders.

## What this is (and is not)

This is **thesis-book aggregation**, not portfolio health or construction:

- NOT `/parallax-portfolio-checkup` — that reads the *health of holdings*. This reads the *argument
  risk of a book of theses*.
- NOT `/parallax-portfolio-builder` — that *constructs* weights. This never sizes, weights, or
  recommends anything.

The single differentiated question it answers: **where does a book of separate theses secretly
concentrate its argument risk?** Five independent-looking theses that all quietly depend on the same
macro assumption (e.g. "the Fed keeps cutting") are one bet wearing five hats — a concentration the
per-thesis view structurally cannot see. Phase 6 surfaces exactly that.

## Preconditions and invariants

- Runs **after** every thesis has completed its own Pass 1 (Phases 1–4, and 4.5 if a view is active).
  It is a **pure synthesis over the per-thesis records already produced** — it fires **no new tool
  calls** and reads no new data.
- **Never rewrites a per-thesis Pass-1 status.** Like Phase 5, aggregation *adds* a layer; it never
  changes any individual assumption's Supported/Contradicted/Unconfirmed call. A Contradicted
  assumption that recurs across three theses is still Contradicted in each.
- **No writes, no recommendation.** It emits a concentration read, never a buy/sell/hold/trim/size
  call and never a "reduce thesis X" directive — it names where the risk clusters and lets the reader
  act.
- Client-invariant by default; the client-conditioned book view (below) runs only if a
  `client_profile` was supplied, and re-weights severity only — never a per-thesis status.

## Step 1 — Canonicalize assumptions across theses

Assumptions from different theses that make the **same underlying claim** must be recognized as one.
Match by `(layer, normalized claim direction + subject)`, not by verbatim text:

- "Fed cutting" (thesis A, macro-1) ≡ "rate cuts continue through year-end" (thesis B, macro-1) →
  one canonical assumption `CA-rates-cut`.
- "long growth over value" (factor lean, thesis A) ≡ "growth outperforms" (thesis C) → one canonical
  factor assumption.

Matching is judgment-based — **state each merge explicitly** in the output (which per-thesis ids
folded into each canonical assumption) so the reader can audit the grouping. When two claims are
*close but not the same* (e.g. "Fed cuts 2×" vs. "Fed cuts 4×"), keep them separate and note the
adjacency rather than force-merging.

## Step 2 — Concentration metric

For each canonical assumption, compute:

- **breadth** — how many theses depend on it;
- **criticality** — the max criticality it carries in any thesis it appears in;
- **status** — its (identical, by invariant) Pass-1 status.

A canonical assumption is **concentrated** when `breadth >= 2` AND it is high-criticality in at least
one thesis. A concentrated assumption that is **Contradicted or Unconfirmed** is the headline risk:
multiple theses rest on a premise the current reads do not support.

## Step 3 — Correlated break conditions

Group per-thesis break conditions by **shared trigger + overlapping `time_to_play_out`**. When one
adverse condition (e.g. "Fed holds instead of cutting") is the break condition for several theses at
once, that single event is a **book-level single point of failure** — the theses do not diversify each
other against it. Report:

- the trigger, the theses it breaks, and the common horizon;
- whether the correlated breaks cluster in time (all multi-quarter, or a mix of weeks-and-quarters —
  the former is a simultaneous drawdown, the latter a staggered one).

## Step 4 — Diversification read & book-level Assumption Strength

- **Independence check** — are the theses' load-bearing sets genuinely distinct (real
  diversification) or do they collapse onto a few shared canonical assumptions (hidden
  concentration)? State which.
- **Book-level Assumption Strength** — the distribution of per-thesis Weak/Mixed/Strong labels
  (client-invariant, carried over unchanged from each Phase 4), **plus** whether the Weak theses
  share a root cause. Three Weak theses that all fail on `CA-rates-cut` is a *different* problem than
  three Weak theses that fail on three unrelated premises — say which. This label rates the book's
  evidential support, not the portfolio; it is **not** a buy/sell/hold, PASS/FAIL, or allocation call.

## Step 5 — Client-conditioned book view *(only if a `client_profile` was supplied)*

Re-weight the **concentrated** canonical assumptions and **correlated** break conditions for the
holder, using the same Phase 5 levers (horizon vs. time-to-play-out, risk capacity vs. magnitude,
income reliance / sequence-of-returns, position size). The book angle adds one lever the single-thesis
pass lacks: **a correlated break that hits several theses simultaneously is a bigger drawdown event
for this holder than any one thesis's break** — surface that where the holder's horizon or income
reliance makes a simultaneous hit material. Never rewrites a per-thesis status; re-weights severity
only.

## Output — book-level sections (render after the per-thesis reports)

Render each per-thesis report in full (collapsed to its TL;DR + Load-Bearing Vulnerabilities at
`quick`/`standard`; expandable), then the book roll-up:

- **Book Overview** — thesis count and a one-line-per-thesis Assumption Strength roster.
- **Shared / Concentrated Assumptions** (table: `canonical_assumption`, `layer`, `# theses`,
  `max_criticality`, `status`, `member_ids`) — concentrated Contradicted/Unconfirmed rows flagged as
  the headline.
- **Correlated Break Conditions** (table: `trigger`, `theses_broken`, `common_horizon`,
  `simultaneous?`) — the book's single points of failure.
- **Book-Level Verdict** — where the book concentrates its argument risk and the one or two triggers
  that would do the most damage across theses; holder-independent. No sizing, no recommendation.
- **Client-Conditioned Book View** *(profile only)* — the concentrated/correlated risks re-weighted
  for this holder, with the simultaneous-drawdown lever called out where it bites.

The standard disclaimer variant (profile-appropriate) and the AI-interaction disclosure render once,
at the end of the whole run — not per thesis.
