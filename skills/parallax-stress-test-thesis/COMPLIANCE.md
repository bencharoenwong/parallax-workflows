# Compliance & review map — `parallax-stress-test-thesis`

A focused guide for a human / compliance reviewer. It states the skill's guardrails, points to
exactly where each is **enforced in code** (not just asserted in prose), and flags the one surface
that needs sign-off before production reliance. Read this first, then spot-check the referenced
lines — the compliance-critical paths are small and localized.

## What this skill is (and is not)

It maps risk in an **argument**: it decomposes a stated investment thesis into falsifiable
assumptions, tests the market-facing ones against live Parallax signals, and reports which
assumptions the case depends on and where it breaks. **It never issues a buy/sell/hold call, a
suitability determination, or a price target.** It is read-only and persists nothing.

## The three invariants — and where each is enforced

| Invariant | Where it's stated | Where it's enforced (code) |
|---|---|---|
| **No recommendation** — never buy/sell/hold, never a rating/target | `SKILL.md` Output Format + Failure modes | `evals/skills/stress-test-thesis/eval_config.py` — `verdict_no_rec` (catches casual imperatives, not just formal tokens) and `json_no_rec` (no signal-shaped key in any structured payload); tests in `evals/graders/test_stress_test_thesis_checks.py` |
| **No writes / no persistence** — `client_profile` is session-only | `SKILL.md` "Where artifacts live" | No write path in the workflow; `client_profile` never leaves the session |
| **Pass-1 is client-invariant** — a client's situation never rewrites what is true about the world | `references/client-conditioning.md` "The invariant this phase must not break" | `evals/graders/test_two_pass_acceptance.py` — grades a *pair* of transcripts: identical Pass-1 statuses across two profiles, divergent client severity only |

## Disclaimers (rendered on every run)

- **No profile:** the standard `parallax-conventions.md` §9.1 disclaimer + "maps risk in an argument;
  does not make a recommendation."
- **Profile supplied:** the stronger bespoke variant (heuristic reasoning over a partial profile, not
  a calibrated suitability model, formal suitability must be made by a qualified professional).
- The token **"not investment advice"** is present in both and checked by `disclaimer_present_correct`.
- The **AI-interaction disclosure** (`parallax-conventions.md` §9.2) renders above the disclaimer and
  is checked by `ai_disclosure_present`.

## Known limitations a reviewer should weigh

1. **The 🔴/🟡/🟢 lights are heuristic, not outcome-calibrated.** Assumption Strength and the Bias &
   Conviction "hype meter" rate *argument quality*, not realized outcomes. This is disclosed at the
   point of use and in Confidence & Caveats, and the disclosure is **grader-enforced**
   (`lights_heuristic_disclosed`). Treat the lights as a decision aid, not a screen.
2. **The client-conditioning pass (Pass 2) is the highest-liability surface** — it conditions on a
   holder's horizon / income-reliance / risk-capacity and emits *suitability-relevant flags*. These
   are framed strictly as descriptive risk observations, each closing with a mandatory
   qualified-professional reminder, and never as a determination. **Pass 2 is pending compliance /
   legal sign-off before production reliance.** If a faster path to publishing the core is wanted,
   ship **Pass-1-only** (no `client_profile`) first and gate Pass 2 behind that sign-off.
3. **Live validation is limited.** Behavior has been validated live against current Parallax signals
   on a small set of theses (inline, not yet in an isolated cold session). A cold-session CI run
   needs Parallax connector credentials in CI (the runner + preflight gate are included). More live
   coverage before a production claim is prudent.

## Fast reviewer checklist

- [ ] Read `SKILL.md` Output Format (disclaimer variants) + "Failure modes the operator must know".
- [ ] Confirm `verdict_no_rec` / `json_no_rec` in `eval_config.py` and their tests.
- [ ] Confirm the Pass-1/Pass-2 boundary test (`test_two_pass_acceptance.py`).
- [ ] Decide whether the heuristic-lights disclosure is sufficient, or the lights should be softened
      to words-only for v1.
- [ ] Route the Pass-2 client-conditioning surface to compliance/legal for sign-off (or ship
      Pass-1-only first).
