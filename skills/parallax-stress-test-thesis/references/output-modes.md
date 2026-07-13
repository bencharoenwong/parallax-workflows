# Output modes — read-time, TL;DR, depth, and the detail toggle

Loaded when the run needs any of: an estimated read time, a TL;DR, a depth/verbosity choice
(`quick` / `standard` / `deep`), or the expand/collapse detail toggle.

**Standard-render vs. mode-gated — do not conflate.** The **read-time marker (§1) and the TL;DR
(§2) are standard render** — they lead *every* report at every depth (they are bold-starred in
`SKILL.md` Output Format), not opt-in features that only appear when this file is loaded. Depth and
the expand/collapse toggle (§3–§4) are the genuinely mode-gated behaviours. Loading this file is
about picking up the detailed rules for all of them; it is not a signal that TL;DR/read-time were
optional.

**The one rule that overrides every mode below:** depth and the detail toggle are *presentation*
controls. Neither may (a) skip Phase 0 preflight, (b) let a layer-1–4 status be reported without a
live Parallax read behind it, (c) drop the AI-interaction disclosure or the disclaimer variant, or
(d) rewrite the Pass-1/Pass-2 boundary. When a mode would trade away any of those, the mode loses.
They are never safety switches.

## 1. Estimated read time

Render a `~N min read` marker at the very top of the report, next to (or just under) the title.
Heuristic: word count of the *rendered* report ÷ 200 wpm, rounded up, floor of `~1 min`. It is an
estimate — label it as such, don't imply precision. For a concise/`quick` render, compute it on the
concise body actually shown, not the full expanded version.

## 2. TL;DR section

Render a **TL;DR** as the first content section, immediately under the read-time marker and above
the Thesis Restatement. Three to five bullets, each a compression of something already in the body —
**the TL;DR never introduces a claim, status, or number that does not appear in the fuller report
below it.** Include, in order:

- the **Assumption Strength** label with a **traffic-light indicator** — `🔴 Weak` / `🟡 Mixed` /
  `🟢 Strong` — and one clause of why. The light rates **how well the argument's load-bearing
  assumptions are supported by the current reads**, and nothing else: 🔴 = a high-criticality
  assumption is Contradicted/Unconfirmed, 🟢 = the load-bearing set is Supported. It is **not a trade
  signal** — 🟢 means "the reasoning holds up", never "buy"; 🔴 means "the reasoning is fragile",
  never "sell" — and it never gates or halts the report (every section still renders below it);
- the single most load-bearing vulnerability, with its Pass-1 status;
- where the thesis most likely breaks first, and over what horizon;
- *(only if a `client_profile` was supplied)* the top client-conditioned flag, if any fired;
- a closing one-liner: *"Rates the argument, not the security — not a buy/sell/hold call."*

The TL;DR is a summary, not a verdict shortcut: it does not replace the disclaimer, and it never
reads as a recommendation.

## 3. Depth / verbosity — `quick` / `standard` / `deep`

Depth sets the **default verbosity** and whether the *optional* `get_assessment` cross-check fires.
It does **not** change which mandatory live reads run — `quick` still fires every Phase 2/3 read
that grounds a reported status, because "never report a status without a live read" is not
negotiable at any depth. `quick` means *shorter prose*, not *fewer facts checked*.

| Level | Default render | `get_assessment` (Phase 4/5, async ~3min) | Typical use |
|---|---|---|---|
| `quick` | TL;DR + Load-Bearing Vulnerabilities + Assumption Strength + disclaimer. Tables collapsed to the headline rows. | Skipped by default. | A fast note; the reader wants the fragile points and the bottom line. |
| `standard` (default) | Full Output Format, concise prose. | Skipped unless asked. | The normal run. |
| `deep` | Full Output Format, expanded reasoning, method notes, per-assumption rationale. | Invited (fire it, don't block; records-based synthesis still leads). | A memo-grade pass. |

**Asking for the level (interactive, level not already given).** When running interactively and no
inline level was supplied, ask once via a clickable `AskUserQuestion` before Phase 2 tool calls fire
— options **Quick note**, **Standard**, **Deep dive**. If a `client_profile` questionnaire is also
being collected one-by-one, fold this in as one of those questions rather than asking twice.
Headless/single-shot or auto mode with no answer available → default to `standard` and note it.

## 4. Progressive detail toggle (`expand` / `collapse`)

There is no GUI accordion in a text run — the toggle is a **next-turn** control, and it is honest
to describe it that way. Render the depth-appropriate default (§3), then close the report with a one
line offer:

> *Reply `expand` for the full per-assumption reasoning, position-level detail, and method notes —
> or `collapse` for just the TL;DR + fragile points.*

On `expand`, re-render at `deep` verbosity from the **same** Phase 2–5 records already produced —
do **not** re-run tools or re-derive statuses (that would risk drift against the numbers already
shown). On `collapse`, render at `quick` verbosity. **Collapsing never hides a Contradicted or
Unconfirmed status, the disclaimer, or the AI disclosure** — those survive at every verbosity; only
narrative depth changes.

## 5. Single-layer scoping

If the user asks to analyze only one layer ("just the macro view", "only the personal/holder
angle", "sector layer only"), map the request and scope the *testing* — never the safety scaffold.

| Phrase | Layer | Tested in |
|---|---|---|
| macro / rates / regime / asset-class | 1 | Phase 2 |
| sector / theme / industry | 2 | Phase 2 |
| position / stock / company / name | 3 | Phase 3 |
| structural / implicit / market preconditions | 4 | Phase 2 |
| personal / holder / suitability / "for me" | 5 | Phase 5 |

Rules that hold in every single-layer run:

- **Phase 0 still runs; the disclaimer + AI disclosure still render.** Always.
- **Still render the FULL Assumption Map, all five layers.** Mark the un-requested layers
  `not tested (single-layer mode)` rather than deleting them — the reader must be able to see that
  the argument's real fragility might live in a layer this run deliberately did not test. Put that
  warning in **Confidence & Caveats** prominently, not as fine print.
- The **World Verdict and Assumption Strength are explicitly scoped** — e.g. "Weak *within the macro
  layer as tested*; layers 2–5 not evaluated this run." Never present a single-layer strength label
  as if it covered the whole thesis.
- **Layers 1–4 scope cleanly.** Run Phase 1 (full map) + the one layer's Phase 2/3 tests.
- **Layer 5 cannot stand fully alone.** Phase 5's severity re-weighting *consumes* Pass-1
  `base_severity` / `magnitude` / `time_to_play_out`. A bare "personal-only" run has nothing to
  re-weight. So in holder-only mode: (i) require a `client_profile` (else there is nothing to test —
  ask for it), and (ii) run a lightweight Pass 1 on just the load-bearing assumptions to anchor the
  re-weighting, and say so. Do not emit client-severity numbers with no Pass-1 base behind them.

## 6. Copy-ready export — purpose-tailored

There is no OS-clipboard write from a skill; "copy to clipboard" is rendered as a **fenced
copy-ready block** the reader copies out of the chat. Say that plainly rather than implying a button.

**Flow.** After the report, offer the export. If the user takes it (or asked for a copy up front),
ask the **purpose** once via clickable `AskUserQuestion` — options below — then render one fenced
block tailored to that purpose:

| Purpose | Shape of the copy block |
|---|---|
| **Email** (to a colleague / client) | Short prose: one-line context, the Assumption Strength + the 2–3 fragile points in sentences, the "what to watch" line. Salutation-ready. |
| **Quick note** (personal) | Terse bullets at TL;DR density — fragile points + statuses only. |
| **Talking points** (a meeting) | Bulleted speaking notes; each fragile point as a spoken line with its break condition. |
| **Doc / memo** (paste into a report) | The structured sections (Assumption Map headline, Load-Bearing Vulnerabilities, World Verdict) as pasteable markdown. |
| **Client-facing plain-language** (hand to a non-professional) | The report re-expressed in **plain sentences with the taxonomy removed** — no "layer 4", "criticality", "base_severity" jargon. Each fragile point becomes "The idea leans on X; right now the data does/doesn't support that; it would stop working if Y." Lead with the one thing that matters most. This is the RM / wealth-advisor / retail-readability answer to "the body is too dense." It translates *language only* — every status, caveat, the no-recommendation framing, and the (profile-appropriate) disclaimer are preserved unchanged. It never becomes a recommendation just because it is now readable. |

**Guardrails on every export variant — non-negotiable:**

- **The disclaimer travels with the copy.** If a `client_profile` was in play, the *stronger*
  client-profile disclaimer variant is included; otherwise the standard one plus the "maps risk in
  an argument; does not make a recommendation" line. An export that omits it is a compliance leak.
- **No fabricated recommendation.** Tailoring for an email must not smooth the language into a
  buy/sell/hold or a suitability call to make it "read naturally." The no-recommendation framing is
  preserved verbatim in intent.
- **Material caveats survive compression.** If a stated status rests on a staleness caveat or an
  Unconfirmed read, that qualifier stays in the copy — you may shorten it, not drop it.
- **Nothing new appears in the export** that was not in the report it summarizes.
- Purpose tailors **format and length only** — never the substance of a status or a flag.

## 9. Role-tailored presentation (`role`)

An optional `role` input names *who is driving the run*, so the skill can **default** to the outputs
that role most needs. It changes which optional features lead — never the analysis. Recognized roles:

| `role` | Leads with | Why |
|---|---|---|
| `individual` | plain-language throughout, `standard` depth, taxonomy minimized | the holder is the reader; the layer/criticality jargon is noise |
| `rm` (relationship manager) | client-facing **plain-language export** + **Talking points** offered up front; suitability flags surfaced prominently | preparing to brief *their* client — the analyzed holder is that client |
| `wealth_advisor` | as `rm`, with the stronger client-profile disclaimer emphasized | suitability-sensitive audience |
| `fund_manager` | `standard`/`deep`, **book mode** and **Run Provenance** on by default | runs many theses; wants cross-thesis concentration + auditability |
| `research_analyst` | `deep` verbosity, per-assumption rationale, peer detail | due-diligence reader; wants the full reasoning chain |
| `engineering` / `embedder` | **`--json`** structured output by default | consuming the payload in a harness, not reading prose |

**Language register — the words, not just which sections lead.** Role also sets the default prose
register, so the same finding reads differently for a different objective. This is presentation, not
analysis:

| Register | Roles | Reads like |
|---|---|---|
| **Plain-English** | `individual`, `rm`, `wealth_advisor` | short sentences; taxonomy words (`layer 4`, `criticality`, `base_severity`) removed or translated; each fragile point becomes "the idea leans on X; right now the data does/doesn't back it; it stops working if Y." An individual reader wants clearly-defined plain language, not the jargon. |
| **Full-detail** | `fund_manager`, `research_analyst`, `engineering` | the complete factor/criticality/layer vocabulary, per-assumption rationale, the nitty-gritty kept in — this reader *wants* the mechanism, not a simplification. |

The register changes wording only: a plain-English render of a `Contradicted` assumption is still
Contradicted, just in plainer words — same statuses, same caveats, same disclaimer. It is the §6
"Client-facing plain-language" translation discipline, applied by default to the whole report for the
reader-facing roles rather than only in an export block. Absent role → `standard` register (neither
stripped or maximally verbose).

Hard rules (same spirit as every mode above):

- **Role tailors which optional features surface by default and the language register — nothing
  else.** It never changes a status, skips Phase 0, drops the disclaimer or AI disclosure, or turns a
  risk observation into advice. Every feature stays available on request regardless of role.
- **Role is not the `client_profile`.** For an RM/advisor the analyzed holder is their *client*, whose
  profile is supplied separately; for an `individual` the operator and the holder coincide. A role
  with no `client_profile` still runs Pass 1 only.
- Unknown/absent role → no tailoring; run the standard defaults. Ask for it via the clickable
  questionnaire (`client-conditioning.md`, "Collecting the profile interactively") when it would
  change which outputs you lead with — but never block the run waiting for it.

## 10. Follow-up questions on the conclusion (in-chat)

After the report, invite the reader to ask follow-up questions on the conclusion — "why is `macro-1`
the load-bearing one?", "what would flip it to Strong?", "walk me through the holder flag", "which leg
is Parallax weakest on?". This is the natural chat form of the skill; it needs no new mode, only these
rules:

- **Answer from the records already produced.** A follow-up re-reads the Phase 2–5 records this run
  generated — it does **not** re-run tools or re-derive a status, because re-deriving risks drift
  against the numbers already shown to the reader. Re-fire a live read **only** when the question
  genuinely needs data this run didn't fetch (a new ticker, a market not queried, a fresh read on a
  Unconfirmed leg), and say so explicitly when you do.
- **Every invariant travels into the answer.** A follow-up that asks for a call — "so should I buy?",
  "is this a good position for me?" — gets the same no-recommendation framing as the report, not a
  softened answer because the exchange is now conversational. The Pass-1/Pass-2 boundary, the "rates
  the argument, not the security" framing, and the disclaimer all still hold in a follow-up.
- **Nothing persists.** Follow-ups live in the current session only; the skill writes nothing and
  remembers nothing across sessions. A "compare to last week" follow-up routes through the §8
  decay-compare input path (the caller supplies the prior JSON) — it is not a stored state the skill
  reaches for.
- When a follow-up outgrows the existing records — a genuinely new thesis leg, a new name, a different
  layer to test — offer a fresh scoped run rather than stretching an in-place answer past what the
  run's reads actually cover.
