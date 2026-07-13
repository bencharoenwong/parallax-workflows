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
