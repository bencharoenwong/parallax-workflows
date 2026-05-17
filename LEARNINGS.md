# Parallax Workflows — Cumulative Learnings

Methodology and process insights distilled from feature work and post-implementation audits. Each entry is a one-line claim plus the trigger that produced it. Entries graduate here from `docs/analysis/*-analysis.md` files after explicit user approval.

---

## 2026-05-17: Drift gates that test structure are the cheapest invariant

Write one drift gate per Non-Negotiable that can be tested with a regex over file contents or an assertion over a Python constant. Examples in this codebase: `test_integration_pattern_referenced.py` (sentinel + Load directive proximity, 16 wired skills, ~ms to run) and `test_visual_branding_keys_are_subset_of_load_client_branding` (loader subset wrapper, voice exclusion). Both caught the highest-stakes invariants (NN-4, NN-1) in the wire-branding audit with one test file each.

**Trigger:** Post-implementation audit of `feat/wire-branding-houseview-skills` — both structural gates passed mechanically; the unverified invariants (manual scenarios) were the audit gaps.

**Source:** `docs/analysis/2026-05-17-wire-branding-houseview-skills-analysis.md`.

---

## 2026-05-17: Requirements-first beats requirements-synthesized

`/analyze-implementation` degrades meaningfully when run without a real Constitution + REQ-XX doc. The synthesis step (back-deriving REQs from a locked plan + design spec) inverts the skill's purpose — instead of catching drift between spec and code, the auditor invents the spec to match the code, which is the LLM-eyeballing failure mode `CLAUDE.verification.md` warns about. The wire-branding audit produced real findings only because the plan note was unusually detailed; a leaner plan would have left the synthesis underdetermined and the audit toothless.

**Rule going forward:** For any Parallax/CG production feature with 3+ REQ-XX, write the requirements doc BEFORE the first implementation commit. Path convention: `docs/plans/YYYY-MM-DD-<feature-slug>-requirements.md`. Without this, `/analyze-implementation` is a documentation exercise, not an audit.

**Trigger:** Dogfood run of `/analyze-implementation` on `feat/wire-branding-houseview-skills` — the audit ran but required user authorization to override the skill's "no retroactive Constitution" guardrail because the feature was wrapped without a requirements doc.

**Source:** `docs/analysis/2026-05-17-wire-branding-houseview-skills-analysis.md`.

---

## 2026-05-17: Manual on-demand gates need at least one captured receipt before they count

A gate that has never run is not a gate. The `compare_docx.py` e2e test for the cio-letter-prep retrofit (REQ-12) is well-designed — four checks (styles, palette, header image ±5% EMU, section/table counts), runnable on demand, fixture in place. But it has never demonstrably fired green because the cio-letter-prep retrofit has not been exercised against `golden_pack_2026-04.docx` post-commit. The right ceremony for any new gate that ships:

1. Run it once.
2. Capture exit code 0 (and the relevant output snippet) in a one-line log under `docs/analysis/` or alongside the gate script.
3. Reference that receipt from the gate's docstring or SKILL.md.

If steps 1–3 cannot happen (e.g., LLM-output gate that has no automatable trigger), explicitly downgrade to "documented manual check" — don't ship the claim that it's an automated gate.

**Trigger:** REQ-12 in the wire-branding audit classified as "Built but Done-When not runnable" because the gate's automation surface is real but the gate has no firing history.

**Source:** `docs/analysis/2026-05-17-wire-branding-houseview-skills-analysis.md`.

---
