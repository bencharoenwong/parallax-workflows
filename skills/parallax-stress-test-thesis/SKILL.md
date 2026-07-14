---
name: parallax-stress-test-thesis
description: "Pressure-tests a written investment thesis: decomposes it into falsifiable assumptions (macro, sector/theme, position-level, implicit market preconditions, holder preconditions), tests market assumptions against current Parallax signals, evaluates named positions, and surfaces which assumptions the argument depends on and where it most likely breaks. Optional client_profile (horizon, risk capacity, income reliance, position size, age) re-weights break-condition severity per investor — same thesis, different verdict by holder. Triggers: 'stress test my thesis', 'poke holes in this argument', 'what am I assuming', 'good idea for a retiree / someone drawing income'. Needs thesis text or a doc/URL; tickers unlock the position read. NOT a news/shock reaction (/parallax-scenario-analysis), NOT a health check with no argument (/parallax-portfolio-checkup), NOT a stock dive with no thesis (/parallax-deep-dive). Read-only, not advice; the client-conditioned pass is a risk observation, not suitability."
---

# Stress-Test Thesis

## When not to use

- Reacting to a specific news event or market shock against a portfolio → use /parallax-scenario-analysis (that skill also answers to "stress test"/"stress book" vocabulary for event-driven exposure — this skill is for testing the *reasoning* behind a stated argument, not portfolio exposure to an event)
- Portfolio health check with no accompanying investment argument → use /parallax-portfolio-checkup (this skill needs a stated thesis to decompose; a bare list of holdings with no reasoning is a checkup, not an argument)
- Single-stock deep dive with no stated thesis → use /parallax-deep-dive or /parallax-should-i-buy
- A formal suitability or compliance determination → not offered by this or any skill in this repo; Pass 2 here is heuristic risk observation, and a qualified professional must make the actual determination

## Gotchas

- JIT-load `_parallax/parallax-conventions.md` for RIC resolution (§1), symbol cross-validation (§2), parallel execution (§3), fallback patterns (§4), macro market selection (§6), and disclaimers (§9.1/§9.2).
- **Phase 0 hard-stop is two distinct failure modes** — don't conflate them in the message to the operator: not-connected (no tools loaded) vs. connected-but-unauthenticated/unentitled (tools loaded, health calls error). A slow/timed-out health call alone is not a hard stop.
- JIT-load `references/assumption-decomposition.md` for the Phase 1 five-layer taxonomy and per-assumption record fields.
- JIT-load `references/market-stress-test.md` for Phase 2 (layers 1–4: market selection, batch calls, Supported/Contradicted/Unconfirmed classification, and the stress step — magnitude + time-to-play-out, both mandatory for Phase 5).
- JIT-load `references/position-evaluation.md` for Phase 3 (layer 3 position read, including the peer-relative factor check).
- JIT-load `references/world-verdict.md` for Phase 4 (the `get_assessment` synthesis: hand the per-assumption records over as fixed inputs, stay client-invariant, the three questions, and the fallback if the async call times out).
- JIT-load `references/client-conditioning.md` for Phase 5 (Pass 2) — **only if a `client_profile` was supplied**.
- `get_stock_outlook` takes exactly one `aspect` per call — fire `analyst_targets` and `risk_return` as two separate calls, never combined.
- `get_news_synthesis` is symbol-only; theme/sector-level news goes through `macro_analyst(component: "news")`, not this tool.
- `get_telemetry` is async (~15-30s); `get_assessment` is async (~3min) — fire early, don't block instant-response tool assembly on either.
- **The core invariant: Pass 2 never rewrites a Pass-1 Supported/Contradicted/Unconfirmed status.** It evaluates the holder-dependent layer and re-weights severity only. See `references/client-conditioning.md` for the mechanical reason this holds.
- No persisted state, no writes — `client_profile` lives in-session only; this skill writes nothing and reads no prior-run state.

## Usage

```
/parallax-stress-test-thesis "I like NVDA because AI capex keeps compounding and rate cuts extend the duration trade for growth names"
/parallax-stress-test-thesis path/to/memo.pdf
/parallax-stress-test-thesis "Rotate into crypto-adjacent equities now that the halving cycle plus ETF inflows are re-rating the space" client_profile={"age":27,"horizon":"20+ years","risk_capacity":"high","income_reliance":"accumulating","position_size_pct_networth":0.05,"risk_tolerance":"high"}
/parallax-stress-test-thesis "…thesis…" role=rm client_profile={…}  # tailor which outputs lead to the operator's role (RM → client-facing plain-language)
```

The input is either an inline argument or a path/URL to a memo (extracted locally — the source never
leaves the session). An optional `client_profile` (JSON object or key:value block) turns on Pass 2.

**Degenerate inputs** (handle before Phase 1 — see `references/assumption-decomposition.md` for detail): tickers with no argument → ask for the *why*; argument with no tickers → run Phases 2 and 4, skip Phase 3 and say so; no `client_profile` → run Pass 1 only, state Pass 2 was skipped for lack of a profile; `client_profile` missing `horizon` or `income_reliance` → ask for those before running Phase 5 **via a clickable `AskUserQuestion`** (role + horizon + income + risk-capacity in one call — see `references/client-conditioning.md` "Collecting the profile interactively"), never a free-text prompt.

## Modes — depth, scope, export

→ Load `references/output-modes.md` when any of these apply. **All are presentation/selection
controls, never safety switches**: none may skip Phase 0, report a status without a live read, or
drop the disclaimer.

- **Depth** — `quick` / `standard` (default) / `deep` sets verbosity and whether the optional
  `get_assessment` cross-check fires. `quick` still runs every mandatory live read — it shortens the
  prose, it does not skip facts. When interactive and no level was given, ask once with a clickable
  `AskUserQuestion` (Quick note / Standard / Deep dive) — fold it into the `client_profile`
  questionnaire if one is being collected.
- **Detail toggle** — after the report, offer `expand` (full per-assumption reasoning) / `collapse`
  (TL;DR + fragile points). Re-renders from the same records; never re-runs tools or re-derives a
  status. Collapsing never hides a Contradicted/Unconfirmed status or the disclaimer.
- **Role-tailored presentation** — an optional `role` (individual / rm / wealth_advisor /
  fund_manager / research_analyst / engineering) makes the skill *default* to the outputs that role
  most needs. It tailors which optional features lead **and the language register** — plain-English
  for individuals/RMs, full factor/criticality detail for fund managers/analysts — **never** a
  status, the disclaimer, or the analysis, and role ≠ `client_profile` (an RM's holder is their
  client). Absent → standard defaults. → `references/output-modes.md` §9
- **Single-layer scope** — if the user asks for one layer only ("just macro", "personal angle
  only"), test only that layer but still render the full five-layer Assumption Map with the rest
  marked *not tested*, scope the World Verdict/Assumption Strength to the tested layer, and warn that
  fragility may live in an un-analyzed layer. → `references/output-modes.md` §5
- **Copy-ready export** — a purpose-tailored fenced block (Email / Quick note / Talking points /
  Doc / **Client-facing plain-language**), asked via `AskUserQuestion`. The disclaimer +
  no-recommendation framing travel with every variant; purpose tailors format and length only. →
  `references/output-modes.md` §6

## Where artifacts live

None. This skill is read-only and persists nothing — no files, no cache. `client_profile` is a session-only input.

## Workflow

### Phase 0 — Preflight

Before any data call: call `ToolSearch` with query `"+Parallax"`.

- **No `mcp__*Parallax*` tools load** → the connector isn't installed/enabled. Hard-stop: tell the operator they need a Parallax account (Chicago Global Capital) and must add the connector. Do not proceed to Phase 1.
- **Tools load, but `check_api_health` and/or `check_macro_health` return an auth/entitlement error** (not merely slow) → the account isn't signed in or lacks access. Hard-stop with that specific explanation. Do not proceed to Phase 1.
- A slow response or timeout on the health call alone is not a hard stop — proceed per the standard fallback patterns in `_parallax/parallax-conventions.md` §4.

### Phase 1 — Decompose into assumptions

Parse the thesis (inline text, or extract from a document/URL locally first — the source never
leaves the session) into the Assumption Map across the five layers. → Load
`references/assumption-decomposition.md` for the taxonomy, per-assumption record, extraction
quality gate, and degenerate-input handling. Phase 1 also yields two early, client-invariant reads
from what it just parsed: the **Coverage Notice** (roll each assumption's `testability` up into
full/partial/out-of-scope and render it up front) and the **Bias & Conviction** (hype) read of the
thesis's own language — both are produced here, before any Phase 2/3 spend. **Play the Assumption
Map back to the user before any Phase 2/3 tool calls fire.** (Headless/single-shot run → render the map, proceed without a
correction turn, and note *extraction unverified* in Confidence & Caveats. Auto/autonomous mode in
an interactive session → render the map, proceed without blocking, but invite correction on the
next turn rather than stamping it unverified. See the reference's "No-blocking-gate runs" note.)

### PASS 1 — Client-invariant (what is true about the world)

Everything in Phases 2–4 is identical regardless of who is asking.

#### Phase 2 — Stress-test market assumptions (layers 1–4, parallel)

→ Load `references/market-stress-test.md`. Classify each layer-1–4 assumption
Supported/Contradicted/Unconfirmed and state its break condition, magnitude, and
time-to-play-out.

#### Phase 3 — Evaluate position-level ideas (layer 3, parallel per symbol; skip if no tickers)

→ Load `references/position-evaluation.md`. Direction alignment, peer-relative factor check,
macro alignment vs. Phase 2, news check with staleness caveat.

#### Phase 4 — World verdict

→ Load `references/world-verdict.md`. **Synthesize the World Verdict from the structured Phase-2/3
records by default** — that is the primary path and needs no async call. `get_assessment` is an
*optional* deep-research cross-check (async ~3min): fire it only when an external pass is wanted, and
if you do, hand the records over as **fixed inputs**, stay client-invariant (never mention a
`client_profile` here — that is Phase 5's job), ask exactly three questions (which assumptions the
thesis most depends on, which are least supported, where it most likely fails first and over what
horizon — holder-independent), and **never paste its output raw** — the word bound is a hint the
model ignores, so extract the three answers and compress them yourself. If it is skipped, errors, or
times out, use the records-based synthesis rather than gating the report.

### PASS 2 — Client conditioning (what it means for this investor)

Runs **only if a `client_profile` was supplied**.

#### Phase 5 — Condition on the client

→ Load `references/client-conditioning.md`. Evaluate the holder-dependent layer, re-weight each
Pass-1 break condition's severity (horizon vs. time-to-play-out, risk capacity vs. magnitude,
income reliance/sequence-of-returns, position size), re-rank Load-Bearing Vulnerabilities, and
emit suitability-relevant flags. Never rewrites a Pass-1 status.

## Output Format

Depth (§Modes) sets which of these render in full vs. collapsed; the **bold-starred** items below
survive at every depth — they are never collapsed away. → `references/output-modes.md`.

- **`~N min read`** *(top marker)* — estimated read time of the rendered report (~200 wpm, rounded up); labeled as an estimate
- **TL;DR** — 3–5 bullets compressing the body (Assumption Strength **with a 🔴/🟡/🟢 traffic-light indicator** — `🔴 Weak` / `🟡 Mixed` / `🟢 Strong`, a glyph for how well-supported the argument is and explicitly **not** a trade signal; top vulnerability + status; most-likely break + horizon; top client flag if any), closing with "rates the argument, not the security." Introduces nothing not in the body below. → `references/output-modes.md` §2
- **Thesis Restatement** (1–2 sentences confirming what was understood, per the Phase 1 playback)
- **Coverage Notice** *(render early, right under Thesis Restatement — before the deep analysis, not buried at the end)* — state Parallax's coverage of each thesis leg up front: **full** (public equity / broad equity-country ETF / country-level macro), **partial** (a rates or FX leg readable only as a country-level regime, not the instrument itself), or **out-of-scope** (crypto / options / futures / spot commodities / private — reachable only via their equity expressions). If the thesis is largely partial or out-of-scope, say so here so the reader knows the resolution limit before reading on — never discovered at the bottom. → `references/market-stress-test.md` "Known Limitations"
- **Client Profile Summary** *(only if `client_profile` supplied)* — the fields as given, and which high-impact fields (if any) were missing and asked for
- **Assumption Map** (table: `id`, `layer`, `claim`, `criticality`, `testability`)
- **Pass 1 — Load-Bearing Vulnerabilities** (the headline: 2–4 assumptions the thesis most depends on, by criticality × Supported/Contradicted status)
- **Assumption-by-Assumption** (table: `id`, `status`, `break_condition`, `magnitude`, `time_to_play_out`)
- **Position-Level Read** *(omit entirely if no tickers — say so under Thesis Restatement instead)* — direction alignment, peer-relative factor check, macro alignment, news + staleness caveat, per symbol
- **World Verdict** (Phase 4 records synthesis; `get_assessment` optional cross-check — what has to be true, where it most likely fails). Lead it with an **Assumption Strength** label — `Weak` / `Mixed` / `Strong` — rating how well the load-bearing assumptions are supported by the current reads (Weak = a high-criticality assumption is Contradicted or Unconfirmed; Strong = the load-bearing set is Supported). **This rates the argument's evidential support, not the security — it is explicitly NOT a buy/sell/hold call, a PASS/FAIL grade, or a suitability verdict.** The TL;DR shows this label with a 🔴/🟡/🟢 traffic-light glyph (🔴 Weak / 🟡 Mixed / 🟢 Strong) — a visual severity cue for *argument strength*, **not** a buy/sell signal and **not** a control-flow gate: 🟢 never means "buy", 🔴 never means "sell", and every section still renders regardless of the light. Optionally annotate each Load-Bearing Vulnerability with the same Weak/Mixed/Strong tag for its own assumption.
- **Bias & Conviction Check** *(the "hype meter"; client-invariant — a Pass-1 read, placed here directly under the World Verdict)* — a 🔴/🟡/🟢 read of how much the thesis leans on **conviction/hype language** (superlatives, certainty with no break condition, "world-class / guaranteed / obvious / no-brainer", narrative-or-authority-as-proof, no bear case) versus falsifiable, hedged, evidenced claims: 🟢 Low = evidence-led and hedged, 🟡 Elevated = some unhedged conviction, 🔴 High = heavy hype / few falsifiable conditions. It rates the argument's *language* and **names the specific behavioral bias most present** (confirmation, narrative fallacy, overconfidence, recency, herding/authority, anchoring, loss-aversion) with a one-clause why. **It is the *rhetoric* axis paired with the World Verdict's *evidence* axis** — the two use the same 🔴/🟡/🟢 glyphs but measure different things (how the case is argued vs. how well the reads back it), so they can diverge (a 🔴-hype thesis can still be 🟢 Strong, or vice-versa); label each explicitly and never conflate them. **Not** a trade signal, **not** a comment on whether the thesis is right. → `references/assumption-decomposition.md` "Bias & conviction (hype) scan"
- **Pass 2 — Holder-Dependent Assumptions** *(only if profile supplied)* — the layer-5 rows, Supported/Contradicted for this person
- **Pass 2 — Client-Conditioned Vulnerabilities** *(only if profile supplied)* — re-ranked using `client_severity`; state what moved vs. the Pass-1 ranking and why
- **Suitability-Relevant Flags** *(only if profile supplied)* — risk observations only, never a call; each closes with the qualified-professional reminder. **If none fired, render a one-line "No suitability flags fired" rather than omitting the section**, so the reader can see the check ran and nothing escalated (a legitimate, common outcome for a long-horizon/accumulating holder)
- **Client-Conditioned Verdict** *(only if profile supplied)* — what this means for this investor specifically
- **What to Watch** (2–3 signals that would confirm or invalidate the thesis; if a profile was supplied, note any that are specifically holder-relevant)
- **Confidence & Caveats** (extraction quality, Unconfirmed/out-of-scope assumptions, data staleness; in single-layer mode, the prominent "layers not tested" warning)
- **Detail toggle** *(footer line)* — offer `expand` (full per-assumption reasoning at `deep` verbosity) / `collapse` (TL;DR + fragile points only). Re-renders from the same records — never re-runs tools or re-derives statuses. Collapsing never hides a Contradicted/Unconfirmed status or the disclaimer
- **Follow-up Q&A** *(footer offer)* — invite the reader to ask follow-up questions on the conclusion in-chat ("why is that the load-bearing one?", "what would flip it to Strong?"). Answer from the **same session's records** — don't re-run tools or re-derive a status unless the question genuinely needs data this run didn't fetch (a new ticker/market), and say so when you do. Every invariant travels into the answer: a "so should I buy?" follow-up gets the same no-recommendation framing, and nothing persists between sessions. → `references/output-modes.md` §10
- **Copy-ready export** *(offered after the report; on request)* — ask purpose via `AskUserQuestion` (Email / Quick note / Talking points / Doc), then render one fenced block tailored to it. **Every variant carries the disclaimer + no-recommendation framing and any material staleness/Unconfirmed caveat; purpose tailors format and length only, never substance.** Rendered as a copy-out-of-chat block — there is no OS-clipboard write. → `references/output-modes.md` §6
- **Run Provenance** *(footer; render at `deep` depth or on request — omit at `quick`/`standard` to avoid bloat)* — a compact, machine-facing inventory that makes the run self-documenting: (a) thesis fingerprint; (b) markets queried and the `macro_analyst` components fired per market; (c) each read's `report_date` and its staleness vs. today; (d) whether the `get_assessment` cross-check fired or the records-based synthesis was used. It **echoes fixed inputs and reads only — it never re-derives a status** and adds no new finding; it is a provenance manifest, not analysis

**AI-interaction disclosure (always):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

**If no `client_profile` was supplied:** render the standard disclaimer verbatim from
`parallax-conventions.md` §9.1, plus: *"This maps risk in an argument; it does not make a
recommendation."*

**If a `client_profile` was supplied**, render this stronger variant instead (bespoke — do not
substitute §9.1):

*"This report includes risk observations conditioned on the client profile supplied in this
session. It is not investment advice and not a recommendation to buy, sell, or hold any security.
The client-conditioned pass is heuristic reasoning over a partial profile, not a calibrated
suitability model — it does not constitute a formal suitability determination. A suitability
assessment must be made by a qualified professional based on the individual's complete financial
circumstances, which this profile does not fully capture. All outputs should be reviewed by
qualified professionals before any investment decisions."*

## Success criteria

A complete run: (1) plays back a corrected Assumption Map before spending Phase 2/3 tokens, (2)
never reports a layer-1–4 status without a live Parallax read behind it (Unconfirmed/out-of-scope
instead of a guess), (3) states a break condition's magnitude and time-to-play-out for every
Supported/Contradicted assumption, (4) if a profile was supplied, shows a client-conditioned
ranking that visibly differs from the Pass-1 ranking where the profile's horizon/income-reliance
actually bite, with the Pass-1 statuses unchanged, and (5) ends with the profile-appropriate
disclaimer variant.

## Failure modes the operator must know without loading anything else

- **Phase 0 hard-stops** (not-connected vs. not-entitled) block all output — there is no partial-data path before Parallax connectivity is confirmed.
- **Pass-1 corruption**: if Pass 2 output ever appears to change a Supported/Contradicted/Unconfirmed status rather than its severity, that is a bug — the client's situation must never rewrite what is true about the world.
- **Not a suitability engine**: Pass 2 flags are illustrative risk observations from an incomplete profile, not a compliance-grade determination. Never render them as a buy/sell/hold call.
</content>
