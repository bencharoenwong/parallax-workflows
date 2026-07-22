# Phase 1 — Decompose the thesis into assumptions

Loaded when Phase 1 fires, after the thesis text has been extracted (inline text parsed directly;
document/URL input extracted locally first — the source file never leaves the session, only the
extracted argument text does).

## The five layers

Read the thesis and pull out every discrete, falsifiable claim it depends on — including the ones
the author never wrote down. Sort each into exactly one layer:

1. **Macro / asset-class** — rates, regime, growth, liquidity, FX, commodity direction.
2. **Sector / theme** — demand trajectory, pricing power, capex cycle, regulation, competitive
   dynamics.
3. **Position-level** — earnings path, margin trajectory, re-rate case, catalyst timing, for each
   named ticker.
4. **Implicit / structural (market)** — unstated preconditions the argument silently needs:
   "financing stays cheap," "correlation holds," "liquidity doesn't dry up," "the multiple the
   market pays for this doesn't compress." These are almost never written in the thesis text —
   find them by asking "what would have to stay true, that the author never said, for step N to
   follow from step N-1?"
5. **Holder-dependent** — preconditions about *the investor*, not the market: can hold through a
   deep or long drawdown without forced selling; does not need this capital for income within the
   stated horizon; the resulting concentration is tolerable; tax/legacy constraints don't force an
   exit. **Populate this layer on every run, profile or not.** If no `client_profile` was
   supplied, every layer-5 assumption still gets a row, with `testability: needs-client-profile`
   and no status — Phase 5 is what actually tests it, and only runs if a profile shows up.

Layers 1–4 are tested in Pass 1 (Phase 2–3) and are true or false about the world, independent of
who's asking. Layer 5 is tested in Pass 2 (Phase 5) and is true or false about a specific person.
Never let a layer-5 read influence a layer 1–4 classification — that's the Pass-1/Pass-2 boundary
this whole skill is built around (see SKILL.md Gotchas).

## Per-assumption record

For every assumption, record:

| Field | Values | Notes |
|---|---|---|
| `id` | short slug, e.g. `macro-1`, `holder-2` | Stable within the run — Phase 4/5 reference these ids |
| `layer` | 1–5 | Per the taxonomy above |
| `claim` | one falsifiable sentence | If you can't state it as something that could be wrong, it isn't an assumption yet — decompose further |
| `criticality` | high / med / low | How much of the thesis's conclusion collapses if this one claim is false |
| `testability` | direct / partial / out-of-scope / needs-client-profile | `out-of-scope` = outside Parallax's coverage even at the country-macro level — don't guess, mark it. **A rates/curve/duration or FX leg is `partial`, NOT `out-of-scope`**: it's readable as a country-level regime via `macro_analyst` `fixed_income`/`currency` (the instrument itself isn't scored, but the regime is). Crypto/options/futures/private assets are `out-of-scope` as instruments — testable only through their equity expressions as layer-3 positions. See `market-stress-test.md` "Known Limitations — asset-class coverage & routing" |
| `client_relative` | yes / no | Does the answer to "is this true" depend on who holds the position? Layer 5 is always `yes`. Layer 1–4 is usually `no` — flag `yes` only if a layer 1–4 claim is genuinely ambiguous without knowing the holder (rare; when in doubt, `no` and let Phase 5's severity re-weighting do the client-specific work instead) |

**These `testability` values roll up into the early Coverage Notice.** Aggregate them across the map
— all `direct`/`partial` on covered markets → **full**; any leg readable only as a country-level
regime (rates/FX) → **partial**; any leg `out-of-scope` as an instrument (crypto/options/futures/
commodities/private) → call it out — and render that one-line summary **up front, right under Thesis
Restatement** (SKILL.md Output Format), so the reader learns the resolution limit before the deep
analysis rather than inferring it from Unconfirmed rows at the end. The full/partial/out-of-scope
taxonomy itself lives in `market-stress-test.md` "Known Limitations".

## Worked example

Thesis: *"I like long-duration growth equities here because the rate-cutting cycle is starting,
lower discount rates re-rate long-duration cash flows, growth outperforms value in the first 6–12
months after the first cut, and inflation has been trending down for three straight quarters. This
is a style rotation, not a single-name pick."* (no tickers, no profile)

The decomposition — note that `implicit-1` is never stated in the thesis, and the holder row is
populated even though no profile was supplied:

| `id` | `layer` | `claim` | `criticality` | `testability` | `client_relative` |
|---|---|---|---|---|---|
| `macro-1` | 1 | The Fed is starting a rate-cutting cycle (policy rate falls from here). | high | direct | no |
| `macro-2` | 1 | Inflation is decelerating — three consecutive quarters of falling readings. | high | direct | no |
| `theme-1` | 2 | Growth outperforms value in the first 6–12 months after the first cut. | high | partial | no |
| `implicit-1` | 4 | The discount-rate mechanism transmits — lower rates actually re-rate long-duration multiples (not offset by falling growth expectations or rising risk premia). | high | partial | no |
| `holder-1` | 5 | The holder can sit through the 6–12 month window without forced selling if the rotation is early. | — | needs-client-profile | yes |

What the decomposition is doing: `macro-1`/`macro-2` are the directly testable market claims (Phase
2 fires `macro_analyst macro_indicators` for the CPI/rate-path facts). `theme-1` is a historical
regularity, not a live signal — `partial`, because Parallax reads the current factor/style leadership
but not the "after the first cut" conditional. `implicit-1` is the load-bearing unstated step: the
whole thesis collapses if lower rates *don't* re-rate multiples, yet the author never wrote it down —
it surfaced by asking "what has to stay true for 'lower discount rates' to reach 'growth
outperforms'?" `holder-1` gets a row with no status because Pass 1 can't test it; if a profile
arrives, Phase 5 tests it and re-weights the others' severity — it never reclassifies `macro-1`–`implicit-1`.

## Bias & conviction (hype) scan

Alongside the layered decomposition, read the thesis text once more for **how it argues**, not just
what it claims — this produces the report's **Bias & Conviction Check** ("hype meter"). It is a
language read, not a data call: it scores how much the argument rests on **conviction / hype
language** versus falsifiable, hedged, evidenced claims. Signals that push the reading hotter:

- **Superlatives / absolutes** — "world-class", "guaranteed", "can't lose", "massive", "obvious",
  "everyone knows", "no-brainer".
- **Certainty with no break condition** — claims stated as fact that the author never made
  falsifiable. A thesis whose high-criticality layer-4 preconditions are all unstated reads hotter.
- **Narrative / authority substituting for evidence** — "smart money is doing X", "the story is",
  guru appeals, momentum-as-proof ("it keeps going up, so it will keep going up").
- **One-sidedness** — no acknowledged bear case, no disconfirming evidence entertained.

The mapping reuses the traffic-light grammar (and, like every light in this skill, is a severity cue,
never a trade signal):

| Reading | Glyph | What it means |
|---|---|---|
| **Low** | 🟢 | Evidence-led and hedged: claims are falsifiable, a bear case is acknowledged, few superlatives. |
| **Elevated** | 🟡 | Some unhedged conviction or narrative reliance, but a testable core remains. |
| **High** | 🔴 | Heavy hype / superlatives, few falsifiable conditions, no bear case — conviction is doing the work evidence should. |

**Name the bias, don't just rate it.** The reading is not only a colour — it names *which* cognitive
bias the language most exhibits, in a word or two, with a one-clause why. Map the signals above to the
specific bias:

| Bias | Tell in the thesis language |
|---|---|
| **Confirmation bias** | only supporting evidence cited; no bear case or disconfirming data entertained |
| **Narrative fallacy** | a compelling story ("major macro shift", "the start of X") carries the case in place of a falsifiable step |
| **Overconfidence** | absolutes and certainty — "guaranteed", "can't lose", "obvious" — with no stated break condition |
| **Recency bias** | a recent move extrapolated forward ("it keeps going up", "the last three prints") as if it must continue |
| **Herding / authority bias** | "smart money", a named guru, or "everyone's buying" standing in for the analysis |
| **Anchoring** | fixation on one number or level (an entry price, a prior high) framing the whole case |
| **Loss aversion / sunk cost** | holding or doubling the thesis because of what's already committed, not the forward case |

State the one or two biases that dominate, with a brief why, e.g. "🟡 Elevated — *narrative fallacy*:
the 'macro shift' story does the work a falsifiable step should." If the language is clean, say so
("🟢 Low — no dominant bias; claims are hedged and falsifiable"). Keep it to the label + the bias
name(s) + one clause — name the bias, give the why, don't lecture.

**Hard framing — this rates the argument's *language*, not its correctness.** A 🔴 reading does
**not** mean the thesis is wrong (a hyped thesis can still be right) and 🟢 does not mean it is right.
It surfaces the author's own behavioral bias — confirmation bias, narrative fallacy, overconfidence —
so the reader can see how much of the case is conviction versus data. It is **never** a trade signal,
never gates the report, and is a **separate axis from Assumption Strength** (which rates the
*evidence* behind the claims; this rates the *rhetoric* around them — a thesis can be 🔴 hype and 🟢
Strong at once, or the reverse). Most relevant to the personal / holder framing: it is the reader's
own bias made visible. Keep it to one line plus a sentence of why; do not moralize.

## Extraction quality gate

Before moving to Phase 2, **play the Assumption Map back to the user** as a table (id, layer,
claim, criticality) and let them correct a mis-read before any tool calls burn tokens on the wrong
argument. This is the single highest-leverage error-catching step in the whole skill — a
mis-extracted assumption produces a confidently wrong verdict five phases later. Don't skip this
for the sake of a faster run.

**No-blocking-gate runs — distinguish two cases; do not conflate them.**

- **Headless / single-shot** (e.g. `claude -p`): there is genuinely no turn for the user to respond
  in. Render the Assumption Map, state you are proceeding without a correction turn, and record
  **extraction unverified** in Confidence & Caveats — a mis-read is a permanent known risk here, so
  flag it as one rather than silently locking it in.
- **Auto / autonomous mode in an interactive session**: the operator wants you to keep moving without
  pausing, but a correction turn *is* still available — they can redirect on their next message.
  Render the Assumption Map, proceed without blocking, and explicitly **invite correction** (e.g.
  "proceeding on this reading — tell me if any row is mis-extracted"). This is softer than the
  headless case: do **not** permanently stamp the verdict *extraction unverified*, but make the map
  prominent so a mis-read is easy to catch on the very next turn.

Never treat the absence of a *blocking* gate as implicit approval in either case — the map must
always be shown before Phase 2/3 tool calls fire.

## Degenerate inputs (handle before decomposing)

- **Tickers but no argument** ("is NVDA good") — there's nothing to decompose. Ask for the *why*.
- **Argument but no tickers** ("rates are heading down, growth wins") — decompose and run Phases
  2 and 4 normally; skip Phase 3 entirely and say so in the output rather than inventing a ticker.
- **`client_profile` present but missing `horizon` or `income_reliance`** — these two fields drive
  the highest-impact parts of Phase 5's severity re-weighting (time-to-play-out comparison and
  sequence-of-returns risk, respectively). Ask for them before running Phase 5 rather than
  conditioning on an incomplete profile; running Pass 1 alone in the meantime is fine.
