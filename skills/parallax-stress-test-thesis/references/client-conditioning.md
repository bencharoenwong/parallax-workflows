# Phase 5 — Condition on the client (Pass 2)

Loaded when Phase 5 fires — **only when a `client_profile` was supplied**. This is the only phase
in the entire skill that reads the profile. Everything upstream (Phases 1–4) is client-invariant
and has already produced its verdict before this phase begins.

## The invariant this phase must not break

**Pass 2 never changes a Pass-1 `status` field (Supported / Contradicted / Unconfirmed).** A break
condition being intolerable for this specific investor does not make the underlying assumption
"Contradicted" — it changes the *severity* of that break condition for them. If Phase 5's output
would require flipping any Phase 1–4 status, that is a bug in this phase, not a valid finding:
stop and re-check the re-weighting logic below instead of editing the Pass-1 record.

The mechanical reason this holds: Phase 5 only ever writes to a *new* field (`client_severity`,
alongside the untouched `base_severity`) and to the new layer-5 assumption rows. It has no write
path to a layer 1–4 `status` field. When composing the optional re-call to `get_assessment` (see
below), the prompt must explicitly instruct: "Do not restate or reclassify the Pass-1
Supported/Contradicted/Unconfirmed statuses — they are fixed inputs. Evaluate only the
holder-dependent layer and severity re-weighting."

## The `client_profile` schema

The profile is a session-only input (JSON object or equivalent key/value block). No field is
persisted. Fields the re-weighting below actually reads:

| Field | Type | Required? | Used by | Notes |
|---|---|---|---|---|
| `horizon` | string (e.g. `"2-3 years"`, `"20+ years"`) | **Required** — ask if missing | (b) horizon vs. time-to-play-out; (c) re-rank | Half the model. A break that resolves over 3–5y is survivable long, terminal short. |
| `income_reliance` | enum-ish string (`"accumulating"`, `"drawing income"`) | **Required** — ask if missing | (b) sequence-of-returns lever | The sharpest lever: a drawdown *during withdrawal* removes the recovery path. |
| `risk_capacity` | `"low"` / `"med"` / `"high"` | Optional (degrades gracefully) | (a) hold-through test; (b) capacity vs. magnitude | Ability to absorb loss without forced selling — distinct from `risk_tolerance`. |
| `position_size_pct_networth` | float `0–1` | Optional | (a) concentration test; (b) whole-portfolio scaling | Same break in a 2% vs. 40% position is not the same severity even for one holder. |
| `risk_tolerance` | `"low"` / `"med"` / `"high"` | Optional | (a) hold-through test (willingness) | Stated *willingness* to bear risk — pair with `risk_capacity` (ability); they can diverge. |
| `age` | int | Optional | context for (a)/(d) | Corroborates horizon/income-reliance; never the sole basis for a flag. |
| `constraints` | free text | Optional | (a) tax/legacy exit-path test | E.g. tax lots, legacy intent, liquidity needs the thesis doesn't account for. |

**Required vs. optional:** only `horizon` and `income_reliance` are hard-required — they drive the
two dominant levers, so a profile missing either is under-specified and Phase 5 asks for them
before running (per `SKILL.md` degenerate-input handling). Every other field degrades gracefully:
if absent, skip the dimension it feeds and note the reduced resolution in Confidence & Caveats
rather than guessing a value. Unknown extra fields are ignored, not errors.

## Collecting the profile interactively — clickable buttons

When Phase 5 needs a `client_profile` that wasn't supplied (or is missing a required field), gather
it with a **clickable `AskUserQuestion`**, not a free-text prompt — one call can carry up to four
questions, so ask them together rather than in a back-and-forth. Preset options (the user can always
type their own via the automatic "Other"):

| Question | Header | Options |
|---|---|---|
| Your role | Role | Individual investor · Relationship manager · Fund manager · Research analyst *(Wealth advisor / Engineering via Other)* |
| Time horizon | Horizon | `< 2 years` · `2–5 years` · `5–10 years` · `10+ years` |
| Income from this capital | Income | Accumulating (no withdrawals) · Partially drawing income · Fully drawing income |
| Capacity to absorb a loss | Risk capacity | Low · Medium · High |

Fold the depth question (`output-modes.md` §3: Quick / Standard / Deep) into the same call when depth
was not given, and — if you still need it — ask position size as a **band** (`< 2%` · `2–10%` ·
`10–25%` · `> 25%` of net worth) rather than a raw float. `horizon` and `income_reliance` are the two
required fields; if the user skips them, re-ask before running Phase 5. `role` tailors presentation
only (`output-modes.md` §9) — never the analysis — so a missing `role` never blocks the run.

## (a) Evaluate the holder-dependent layer

Every layer-5 assumption from Phase 1 (populated on every run, marked `needs-client-profile` until
now) gets tested against the actual profile fields:

- Can the investor hold through a deep/long drawdown without forced selling? → compare against
  `risk_capacity` and `position_size_pct_networth`.
- Does the investor need this capital for income within the horizon? → compare against
  `income_reliance` and `horizon`.
- Is the resulting concentration tolerable? → `position_size_pct_networth` alone, independent of
  market direction.
- Do tax/legacy constraints force an exit path the thesis doesn't account for? → free-text
  constraints field, if supplied.

Classify each Supported / Contradicted *for this person* — this is the one place in the skill
where "Contradicted" is legitimately client-relative, because layer 5 claims are about the holder
by definition, not about the market.

## (b) Re-weight each Pass-1 break condition's severity

For every layer-1–4 assumption that carries a `break_condition` (i.e., was Supported or
Contradicted in Phase 2/3 — Unconfirmed ones have nothing to re-weight), compare its
`time_to_play_out` and `magnitude` (both captured in Phase 2/3 — this is why those fields are
mandatory) against the profile:

| Dimension | Compare | Effect |
|---|---|---|
| Horizon vs. time-to-play-out | `client_profile.horizon` vs. the break condition's `time_to_play_out` | A break that resolves over 3–5y is survivable for a long-horizon holder, terminal for a short one — same break condition, opposite severity |
| Risk capacity vs. magnitude | `client_profile.risk_capacity` vs. the break condition's `magnitude` | Low capacity + large magnitude compounds toward `client_severity: high` even if `base_severity` was `med` |
| Income reliance / sequence-of-returns | `client_profile.income_reliance` | **This is the sharpest lever in the whole model.** A drawdown that hits *while the investor is withdrawing* locks in losses that a pure accumulator would simply ride out — it can convert a `base_severity: med, recoverable` read into `client_severity: high, effectively terminal`, because forced sales during the drawdown remove the recovery path entirely |
| Position size | `client_profile.position_size_pct_networth` | Scales everything above by whole-portfolio impact — the same break condition in a 2% position and a 40% position is not the same severity even for the identical holder |

Write `client_severity` (high/med/low) alongside the untouched `base_severity` for every
re-weighted assumption. Note explicitly *why* it moved (which of the four dimensions above drove
the change) — this is what makes the re-ranking auditable rather than a black box.

## (c) Re-rank Load-Bearing Vulnerabilities

Produce a client-conditioned ranking using `client_severity` in place of `base_severity`. State
what moved relative to the Pass-1 (world) ranking and why — e.g., "the financing-cost assumption
was #3 by world severity but is #1 client-conditioned, because the client's 2-year horizon is
shorter than this break condition's 3–5y time-to-play-out."

## (d) Suitability-relevant flags

Where a re-weighted assumption lands at `client_severity: high` specifically because of a
holder-dependent factor (not because the world-level read itself was severe), emit an explicit
flag: this is a **risk observation**, phrased descriptively ("this position's break condition, if
it fires, would coincide with this investor's stated income-reliance window") — **never** a
buy/sell/hold call, and never phrased as a suitability determination. Close every flag block with
a reminder that a formal suitability assessment must be made by a qualified professional against
the individual's full circumstances — Pass 2 is heuristic reasoning over a partial profile, not a
calibrated model (see `SKILL.md` "Failure modes the operator must know" — *Not a suitability
engine*).

## Optional re-call to `get_assessment`

If the client-conditioned picture is complex enough to benefit from a synthesis pass, re-call
`get_assessment` with: the original Pass-1 prompt's findings (fixed), the profile, and the explicit
instruction quoted under "The invariant this phase must not break" above. This call is optional —
skip it if the re-weighting above already produces a clear verdict; don't burn the ~3min async
round-trip for a thesis where the client-conditioning is obviously one-directional.

## Disclaimer variant

Any run that reaches this phase renders the **stronger, client-profile disclaimer variant** in
Output Format (not the standard one) — see `SKILL.md` Output Format section for the exact wording.
