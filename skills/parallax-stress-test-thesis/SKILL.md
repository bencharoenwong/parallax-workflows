---
name: parallax-stress-test-thesis
description: "Pressure-tests a written investment thesis: decomposes it into falsifiable assumptions (macro, sector/theme, position-level, implicit market preconditions, holder preconditions), tests market assumptions against current Parallax signals, evaluates named positions, and surfaces which assumptions the argument depends on and where it most likely breaks. Optional client_profile (horizon, risk capacity, income reliance, position size, age) re-weights break-condition severity per investor. Triggers: 'stress test my thesis', 'poke holes in this argument', 'what am I assuming'. Needs thesis text or a doc/URL; tickers unlock the position read. NOT a news/shock reaction (/parallax-scenario-analysis), NOT a health check with no argument (/parallax-portfolio-checkup), NOT a stock dive with no thesis (/parallax-deep-dive), NOT a stress test of the house view itself (/parallax-stress-house-view). Read-only, not advice; the client-conditioned pass is a risk observation, not suitability."
---

# Stress-Test Thesis

## When not to use

- Reacting to a specific news event or market shock against a portfolio → use /parallax-scenario-analysis (that skill also answers to "stress test"/"stress book" vocabulary for event-driven exposure — this skill tests the *reasoning* behind a stated argument)
- Stress-testing the active house view for internal contradictions → use /parallax-stress-house-view
- Portfolio health check with no accompanying investment argument → use /parallax-portfolio-checkup (book mode here aggregates *arguments*, one stated thesis per position)
- Single-stock deep dive with no stated thesis → use /parallax-deep-dive or /parallax-should-i-buy
- A formal suitability or compliance determination → not offered by this or any skill in this repo; Pass 2 is heuristic risk observation, and a qualified professional must make the actual determination

## Gotchas

- Expected Parallax spend: scales with markets × components and named tickers; the optional `get_assessment` cross-check adds 10.
- JIT-load `_parallax/parallax-conventions.md` for §0.0 pre-flight, §1 RIC resolution, §2 identity cross-check, §3 parallel execution, §4 fallbacks, §6 macro market selection, §9.1/§9.2 disclosures, §14 host primitives.
- References, loaded when their step fires: `references/assumption-decomposition.md` (Step 1 taxonomy, records, degenerate inputs, hype scan), `references/market-stress-test.md` (Step 2/3 layers 1–4: market selection, batch calls, Supported/Contradicted/Unconfirmed, magnitude + time-to-play-out), `references/position-evaluation.md` (layer 3 position read), `references/world-verdict.md` (Step 4 synthesis and the async fallback), `references/client-conditioning.md` (Pass 2, only with a `client_profile`), `references/house-view-check.md` (only if an active view exists), `references/portfolio-aggregation.md` (book mode only), `references/output-modes.md` (depth, JSON, decay-compare, role, single-layer, export).
- **Step 0 hard-stop is two distinct failure modes** — not-connected (no Parallax tools discovered) vs. connected-but-unentitled (tools discovered, the `check_api_health` probe errors). A slow or timed-out probe alone is not a hard stop.
- `get_stock_outlook` takes exactly one `aspect` per call; `get_news_synthesis` is symbol-only (theme news is `macro_analyst(component: "news")`); `get_telemetry` (~15–30 s) and `get_assessment` (~3 min) are async — fire early, never block instant tools on them.
- **Core invariant: Pass 2 never rewrites a Pass-1 Supported/Contradicted/Unconfirmed status** — it re-weights severity only.
- House-view cross-check is optional, read-only and flag-only; it writes no §6 consume-audit row by default (`--house-view-audit` opts in — see the reference). No active view → render nothing.
- Book mode (>1 thesis) is pure synthesis over per-thesis records — no new tool calls, no writes, no sizing call, never rewrites a per-thesis status.
- No persisted state, no writes: `client_profile` lives in-session only.

## Usage

```
/parallax-stress-test-thesis "I like NVDA because AI capex keeps compounding and rate cuts extend the duration trade for growth names"
/parallax-stress-test-thesis path/to/memo.pdf
/parallax-stress-test-thesis "Rotate into crypto-adjacent equities now that the halving cycle plus ETF inflows are re-rating the space" client_profile={"age":27,"horizon":"20+ years","risk_capacity":"high","income_reliance":"accumulating","position_size_pct_networth":0.05,"risk_tolerance":"high"}
/parallax-stress-test-thesis "…thesis…" --house-view-audit        # opt in to logging house-view consumption (off by default)
/parallax-stress-test-thesis book.md        # a file (or several inline theses) → per-thesis reports + cross-thesis concentration roll-up
/parallax-stress-test-thesis "…thesis…" --json                    # structured output for embedding (no prose required)
/parallax-stress-test-thesis "…thesis…" compare=<prior-run JSON>  # decay-compare: what changed vs. last run (reads today live)
/parallax-stress-test-thesis "…thesis…" role=rm client_profile={…}  # tailor which outputs lead to the operator's role
```

The input is an inline argument or a path/URL to a memo (extracted locally — the source never leaves the session). An optional `client_profile` (JSON object or key:value block) turns on Pass 2. **Multiple theses → book mode:** several delimited theses, or multiple `<thesis_input>…</thesis_input>` tags, run each thesis's full Pass 1/2 and then aggregate; one supplied `client_profile` conditions the whole book; unknown tags are ignored.

## Modes — depth, scope, export

→ Load `references/output-modes.md` when any of these apply. **All are presentation/selection
controls, never safety switches**: none may skip Phase 0, report a status without a live read, or
drop the disclaimer.

- **Depth** — `quick` / `standard` (default) / `deep` sets verbosity and whether the optional
  `get_assessment` cross-check fires. `quick` still runs every mandatory live read — it shortens the
  prose, it does not skip facts. When interactive and no level was given, ask once via `ask-operator` (Quick note / Standard / Deep dive; a structured question on hosts that offer one) — fold it into the `client_profile`
  questionnaire if one is being collected.
- **Detail toggle** — after the report, offer `expand` (full per-assumption reasoning) / `collapse`
  (TL;DR + fragile points). Re-renders from the same records; never re-runs tools or re-derives a
  status. Collapsing never hides a Contradicted/Unconfirmed status or the disclaimer.
- **Structured (JSON) output** — on `--json` / "machine-readable", emit a fenced `json` block
  mirroring the records (assumption map, statuses, verdict) for embedding. **No `action`/`rating`/`weight`
  key ever**; carries `disclaimer_variant` + `not_a_recommendation: true`; no new derivation; still
  read-only (rendered in-chat, writes nothing). → `references/output-modes.md` §7
- **Decay-compare** — "what changed since last time?": the caller pastes a prior run's JSON (or names
  the prior statuses) as a **session input** — the skill re-reads today's data live, diffs Assumption
  Strength / status flips into a **What Changed** section, and writes nothing. This is the
  no-persistence monitoring loop (state lives with the caller). → `references/output-modes.md` §8
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
  Doc / **Client-facing plain-language**), asked via `ask-operator`. The disclaimer +
  no-recommendation framing travel with every variant; purpose tailors format and length only. →
  `references/output-modes.md` §6

## Where artifacts live

None. This skill is read-only and persists nothing — no files, no cache. `client_profile` is a session-only input.

## Workflow

Every host interaction below is a host primitive from `parallax-conventions.md` §14 (bindings §14.2, fail-open §14.3). Parallax callables are whatever `discover-tools` returns this session (§0.1). Phases keep their reference-file names inside the steps.

### Step 0 — Pre-flight

1. Resolve every `_parallax/...` and `references/...` path named in this file to the canonical copy (conventions §0.0 item 1).
2. `discover-tools`: bind every logical tool named in the references (Steps 2–4) to the exact callable and schema exposed now; then `call-tool` `check_api_health` once as the liveness/auth probe.
   <!-- host-note -->
   Claude Code: `ToolSearch` with query `"+Parallax"` before the first Parallax call.
   <!-- /host-note -->
   - **No Parallax capability discovered** → hard-stop: tell the operator a Parallax account (Chicago Global Capital) and the connector are required. Do not proceed.
   - **Discovered, but the probe (or the first data call) returns an auth/entitlement error** → hard-stop with that specific explanation. Do not proceed.
   - A slow or timed-out probe alone is not a hard stop; proceed per conventions §4.
3. Parse args: thesis text or path/URL; `client_profile`; `--house-view-audit`; `--json`; `compare=`; `role=`; depth; single-layer scope.
4. `read-config`: if `~/.parallax/active-house-view/view.yaml` exists, `load-reference` `references/house-view-check.md` for Step 4 (flag-only). No view → nothing.

### Step 1 — Resolve inputs (Phase 1 — decompose)

`load-reference` `references/assumption-decomposition.md`. Extract the thesis locally (the source never leaves the session) and parse it into the Assumption Map across the five layers with the per-assumption record; produce the **Coverage Notice** and the **Bias & Conviction** read here, before any spend. **Degenerate inputs:** tickers with no argument → ask for the *why*; argument with no tickers → run Steps 2 and 4, skip the position read and say so; no `client_profile` → Pass 1 only, stated; profile missing `horizon` or `income_reliance` → `ask-operator` for horizon + income + risk capacity in one question (a structured question where the host offers one; see the client-conditioning reference) before Pass 2. **Play the Assumption Map back before any Step 2/3 tool calls fire** (headless run → render it, proceed, note *extraction unverified* in Confidence & Caveats; autonomous interactive run → render, proceed, invite correction next turn).

### Step 2 — Fetch (parallel batches) (Phases 2–3 reads)

`load-reference` `references/market-stress-test.md` and, when tickers were named, `references/position-evaluation.md`. `call-tool` the layer 1–4 market reads (market selection per conventions §6; instant tools first, `get_telemetry` alongside) and the per-symbol position reads together; fire the optional `get_assessment` cross-check early only at `deep` depth or on request.

### Step 3 — Verify (Phase 2 classification)

Classify each layer 1–4 assumption Supported / Contradicted / Unconfirmed strictly from live reads (never a guess — Unconfirmed or out-of-scope instead), and state its break condition, magnitude, and time-to-play-out. Identity cross-check per conventions §2 for every position read.

### Step 4 — Compute (Phases 4–6)

- **World Verdict** (`references/world-verdict.md`): synthesize from the Phase-2/3 records by default; if the optional `get_assessment` fired, hand the records over as fixed inputs, stay client-invariant, ask exactly the three holder-independent questions, and never paste its output raw; on error or timeout use the records-based synthesis. Assumption Strength per the precedence cascade in Output Format.
- **House-view cross-check** (only with an active view): flag disagreements; never apply tilts, never rewrite a status.
- **Pass 2** (only with a `client_profile`; `references/client-conditioning.md`): holder-dependent layer, severity re-weighting, re-ranked vulnerabilities, suitability-relevant flags; Pass-1 statuses unchanged.
- **Book mode** (only with >1 thesis; `references/portfolio-aggregation.md`): cross-thesis concentration synthesis, no new calls.

### Step 5 — Compose

Fill **Output Format** below per the selected depth/role/mode (`references/output-modes.md`); `parallax-conventions.md §9.2` disclosure; the profile-appropriate disclaimer variant.

### Step 6 — Render (deterministic gate, mandatory)

`run-shell` the shared gate per conventions §10.3 with this skill's key:

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/thesis.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill stress-test-thesis < "$DRAFT"; rm -f "$DRAFT"
```

The entire final message is that command's stdout (`--json` output is a fenced block inside it). The stderr `[render-gate] WARN:` line is diagnostics: never include it. If `run-shell` is absent, apply conventions §14.3 (render-gate row). No Step 7.


## Output Format

**Begin the response immediately with the rendered report — no preamble.** The first expected line is the `~N min read` marker, then `**TL;DR**`.

Depth (§Modes) sets which of these render in full vs. collapsed; the **bold-starred** items below
survive at every depth — they are never collapsed away. → `references/output-modes.md`.

**The default render is the full layered analysis.** The **Assumption Map** and the
**Assumption-by-Assumption** table — the per-layer reasoning a sophisticated reader (fund manager /
analyst) is here for — are **standard render: always shown, never reduced to a summary in a default
run.** Condensing or plain-languaging them for a lay audience is an *opt-in* presentation mode
(role/export), never the default — so the taxonomy-stripped view is only ever produced on explicit
request, and the base skill always exposes the full layered view.

- **`~N min read`** *(top marker)* — estimated read time of the rendered report (~200 wpm, rounded up); labeled as an estimate
- **TL;DR** — 3–5 bullets compressing the body (Assumption Strength **with a 🔴/🟡/🟢 traffic-light indicator** — `🔴 Weak` / `🟡 Mixed` / `🟢 Strong`, a glyph for how well-supported the argument is and explicitly **not** a trade signal; top vulnerability + status; most-likely break + horizon; top client flag if any), closing with "rates the argument, not the security." Introduces nothing not in the body below. → `references/output-modes.md` §2
- **Thesis Restatement** (1–2 sentences confirming what was understood, per the Phase 1 playback)
- **Coverage Notice** *(render early, right under Thesis Restatement — before the deep analysis, not buried at the end)* — state Parallax's coverage of each thesis leg up front: **full** (public equity / broad equity-country ETF / country-level macro), **partial** (a rates or FX leg readable only as a country-level regime, not the instrument itself), or **out-of-scope** (crypto / options / futures / spot commodities / private — reachable only via their equity expressions). If the thesis is largely partial or out-of-scope, say so here so the reader knows the resolution limit before reading on — never discovered at the bottom. **For any leg marked out-of-scope, name where the reader can verify it externally** (the spot instrument, ETF-flow data, an official print) so an out-of-scope leg is a directed next step, not a dead end. → `references/market-stress-test.md` "Known Limitations"
- **Client Profile Summary** *(only if `client_profile` supplied)* — the fields as given, and which high-impact fields (if any) were missing and asked for
- **Assumption Map** (table: `id`, `layer`, `claim`, `criticality`, `testability`)
- **Pass 1 — Load-Bearing Vulnerabilities** (the headline: 2–4 assumptions the thesis most depends on, by criticality × Supported/Contradicted status)
- **Assumption-by-Assumption** (table: `id`, `status`, `break_condition`, `magnitude`, `time_to_play_out`)
- **Position-Level Read** *(omit entirely if no tickers — say so under Thesis Restatement instead)* — direction alignment, peer-relative factor check, macro alignment, news + staleness caveat, per symbol
- **World Verdict** (Phase 4 records synthesis; `get_assessment` optional cross-check — what has to be true, where it most likely fails). Lead it with an **Assumption Strength** label — `Weak` / `Mixed` / `Strong` — rating how well the load-bearing assumptions are supported by the current reads, as a precedence cascade (Weak = ≥1 high-criticality assumption Contradicted/Unconfirmed — cracked at the foundation; Mixed = all high-criticality Supported but ≥1 medium-criticality Contradicted/Unconfirmed — foundation holds, cracks higher up; Strong = all high-criticality Supported and no medium-criticality Contradicted/Unconfirmed). **This rates the argument's evidential support, not the security — it is explicitly NOT a buy/sell/hold call, a PASS/FAIL grade, or a suitability verdict, and it is a heuristic read, not an outcome-calibrated score.** The TL;DR shows this label with a 🔴/🟡/🟢 traffic-light glyph (🔴 Weak / 🟡 Mixed / 🟢 Strong) — a visual severity cue for *argument strength*, **not** a buy/sell signal and **not** a control-flow gate: 🟢 never means "buy", 🔴 never means "sell", and every section still renders regardless of the light. Optionally annotate each Load-Bearing Vulnerability with the same Weak/Mixed/Strong tag for its own assumption.
- **Bias & Conviction Check** *(the "hype meter"; client-invariant — a Pass-1 read, placed here directly under the World Verdict)* — a 🔴/🟡/🟢 read of how much the thesis leans on **conviction/hype language** (superlatives, certainty with no break condition, "world-class / guaranteed / obvious / no-brainer", narrative-or-authority-as-proof, no bear case) versus falsifiable, hedged, evidenced claims: 🟢 Low = evidence-led and hedged, 🟡 Elevated = some unhedged conviction, 🔴 High = heavy hype / few falsifiable conditions. It rates the argument's *language* and **names the specific behavioral bias most present** (confirmation, narrative fallacy, overconfidence, recency, herding/authority, anchoring, loss-aversion) with a one-clause why. **It is the *rhetoric* axis paired with the World Verdict's *evidence* axis** — the two use the same 🔴/🟡/🟢 glyphs but measure different things (how the case is argued vs. how well the reads back it), so they can diverge (a 🔴-hype thesis can still be 🟢 Strong, or vice-versa); label each explicitly and never conflate them. **Not** a trade signal, **not** a comment on whether the thesis is right. → `references/assumption-decomposition.md` "Bias & conviction (hype) scan"
- **House-View Alignment** *(only if an active house view exists at `~/.parallax/active-house-view/`; omit entirely otherwise)* — the required active-view banner plus a single blanket note (via the shared `render_view_conflict` helper) flagging where the thesis's macro/sector/factor claims agree or disagree with the firm's positioning. **Flag only: the view never changes an assumption's Pass-1 status, criticality, or rank** — it is a positioning conflict to resolve at decision time, orthogonal to the evidential read. Client-invariant. → `references/house-view-check.md`
- **Pass 2 — Holder-Dependent Assumptions** *(only if profile supplied)* — the layer-5 rows, Supported/Contradicted for this person
- **Pass 2 — Client-Conditioned Vulnerabilities** *(only if profile supplied)* — re-ranked using `client_severity`; state what moved vs. the Pass-1 ranking and why
- **Suitability-Relevant Flags** *(only if profile supplied)* — risk observations only — **never a call and never a suitability determination**; each flag is phrased descriptively and **must** close with the qualified-professional reminder (mandatory, not optional). The client-conditioning pass is heuristic reasoning over a partial profile and is **pending compliance sign-off before production reliance** — see `COMPLIANCE.md`. Where it makes a flag concrete, you may add **illustrative arithmetic** (e.g., a drawdown as a share of net worth given the position size) explicitly marked *illustrative, not a prediction* — never a forecast of magnitude or likelihood. **If none fired, render a one-line "No suitability flags fired" rather than omitting the section**, so the reader can see the check ran and nothing escalated (a legitimate, common outcome for a long-horizon/accumulating holder)
- **Client-Conditioned Verdict** *(only if profile supplied)* — what this means for this investor specifically
- **What to Watch** — open with a single **"This works only if …"** line: the minimal condition set that would validate the thesis, stated plainly (the falsification, put positively) so a reader has one crisp thing to track. Then 2–3 signals that would confirm or invalidate it; if a profile was supplied, note any that are specifically holder-relevant
- **What Changed** *(decay-compare only — a prior-run JSON/statuses were supplied)* — per assumption `prior_status → current_status`, break conditions newly fired/cleared, and the net Assumption Strength move; reads today's data live, reports the drift, recommends nothing. → `references/output-modes.md` §8
- **Confidence & Caveats** (extraction quality, Unconfirmed/out-of-scope assumptions, data staleness) — **and always a standing note that the 🔴/🟡/🟢 Assumption-Strength and Bias & Conviction lights are heuristic reads of argument quality, not outcome-calibrated scores** (a decision aid, not a screen) In single-layer mode, add the prominent "layers not tested" warning.
- **Detail toggle** *(footer line)* — offer `expand` (full per-assumption reasoning at `deep` verbosity) / `collapse` (TL;DR + fragile points only). Re-renders from the same records — never re-runs tools or re-derives statuses. Collapsing never hides a Contradicted/Unconfirmed status or the disclaimer
- **Follow-up Q&A** *(footer offer)* — invite the reader to ask follow-up questions on the conclusion in-chat ("why is that the load-bearing one?", "what would flip it to Strong?"). Answer from the **same session's records** — don't re-run tools or re-derive a status unless the question genuinely needs data this run didn't fetch (a new ticker/market), and say so when you do. Every invariant travels into the answer: a "so should I buy?" follow-up gets the same no-recommendation framing, and nothing persists between sessions. → `references/output-modes.md` §10
- **Copy-ready export** *(offered after the report; on request)* — ask purpose via `ask-operator` (Email / Quick note / Talking points / Doc), then render one fenced block tailored to it. **Every variant carries the disclaimer + no-recommendation framing and any material staleness/Unconfirmed caveat; purpose tailors format and length only, never substance.** Rendered as a copy-out-of-chat block — there is no OS-clipboard write. → `references/output-modes.md` §6
- **Run Provenance** *(footer; render at `deep` depth or on request — omit at `quick`/`standard` to avoid bloat)* — a compact, machine-facing inventory that makes the run self-documenting: (a) thesis fingerprint; (b) markets queried and the `macro_analyst` components fired per market; (c) each read's `report_date` and its staleness vs. today; (d) whether the `get_assessment` cross-check fired or the records-based synthesis was used. It **echoes fixed inputs and reads only — it never re-derives a status** and adds no new finding; it is a provenance manifest, not analysis

**Book mode (>1 thesis) — additional roll-up after the per-thesis reports** *(omit entirely for a single thesis)* — render each thesis's report first (collapsed to TL;DR + Load-Bearing Vulnerabilities at `quick`/`standard`, expandable), then: **Book Overview** (thesis count + per-thesis Assumption Strength roster); **Shared / Concentrated Assumptions** (table: `canonical_assumption`, `layer`, `# theses`, `max_criticality`, `status`, `member_ids` — concentrated Contradicted/Unconfirmed rows are the headline); **Correlated Break Conditions** (table: `trigger`, `theses_broken`, `common_horizon`, `simultaneous?` — the book's single points of failure); **Book-Level Verdict** (where the book concentrates argument risk, holder-independent, no sizing/recommendation); and **Client-Conditioned Book View** *(profile only)*. The disclaimer + AI-interaction disclosure render **once, at the end of the whole run**, not per thesis. → `references/portfolio-aggregation.md`

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


## Failure modes

See `COMPLIANCE.md` for the compliance/review map — where each invariant is enforced, the heuristic-not-calibrated posture, and the Pass-2 sign-off note.

- **Step 0 hard-stops** (not-connected vs. not-entitled) block all output — there is no partial-data path before Parallax connectivity is confirmed.
- **Pass-1 corruption:** if Pass 2 output ever appears to change a Supported/Contradicted/Unconfirmed status rather than its severity, that is a bug.
- **Not a suitability engine:** Pass 2 flags are illustrative risk observations from an incomplete profile, never a buy/sell/hold call.
- Optional `get_assessment` errors or times out: records-based synthesis, stated in Run Provenance.
- Host lacks a primitive: conventions §14.3, per primitive (`ask-operator` absent → render the profile questions and stop before Pass 2).

## Done when

- The Assumption Map was played back before any Step 2/3 spend, and the report opens with the `~N min read` marker and TL;DR.
- No layer-1–4 status was reported without a live Parallax read behind it (Unconfirmed/out-of-scope otherwise).
- Every Supported/Contradicted assumption carries a break condition's magnitude and time-to-play-out.
- With a profile: the client-conditioned ranking visibly differs from Pass 1 where horizon/income-reliance bite, with Pass-1 statuses unchanged; without one: Pass 2 stated as skipped.
- The render gate ran and the reply is its stdout; `parallax-conventions.md §9.2` disclosure and the profile-appropriate disclaimer variant are present.
