# wire-branding-houseview-skills — Post-Implementation Analysis

**Date:** 2026-05-17
**Requirements file:** *None pre-existing.* REQ-XX + Constitution synthesized post-hoc from the locked plan note (`~/.claude/notes/2026-05-16-1900-final-plan-wire-branding-houseview-skills.md`) plus the upstream white-label design spec (`docs/superpowers/specs/2026-04-30-white-label-onboarding-design.md`). **This violates the skill's "no retroactive Constitution" guardrail by explicit user authorization** to dogfood `/analyze-implementation` against its first real candidate; the synthesis itself is flagged as the primary methodological finding.
**Plan file:** `~/.claude/notes/2026-05-16-1900-final-plan-wire-branding-houseview-skills.md`
**Commit range:** `a4915ed..ebf2da9` (14 commits; the plan listed a 15th item — "AUDIT GATE" — as a process step, not a code commit)

## Synthesized REQ-XX (post-hoc — read with scepticism)

| ID | Statement | Done-When |
|---|---|---|
| REQ-01 | Add `load_visual_branding()` subset wrapper to `loader.py` — 5 lines, returns the 6 allowed visual keys only | Function exists; returns dict of exactly `{client_name, colors, logos, fonts, source, error}`; never returns voice |
| REQ-02 | Create `_parallax/white-label/integration-pattern.md` with §1–§8 contract | File exists; sections §1 Purpose through §8 Gotchas present |
| REQ-03 | Retrofit `cio-letter-prep` to consume integration-pattern (sentinel + JIT-ref); voice guardrail stays inline | SKILL.md contains sentinel comment + Load directive; voice guardrail prose intact in gotchas |
| REQ-04 | Tier 1 (client-review, due-diligence, deep-dive) inline the loader call + 6-key allowlist | All 3 SKILL.md files contain `from loader import load_visual_branding` snippet + 6-key allowlist directive |
| REQ-05 | Tier 2 (12 skills) JIT-reference integration-pattern.md via sentinel + Load directive | Drift-gate test passes for each Tier 2 SKILL.md |
| REQ-06 | Step naming: `### Pre-Render — Load white-label branding` (branding) and `### Pre-Workflow — Load Active House View` (HV) | grep finds these exact headers in the respective skills |
| REQ-07 | Drift-gate test enforces sentinel AND proximate Load directive via regex | `test_integration_pattern_referenced.py` exists; pattern matches required structure; test passes for all 16 wired skills |
| REQ-08 | macro-outlook gets new §7.4 macro-regime-alignment mode | macro-outlook SKILL.md references §7.4 + Post-Workflow alignment block |
| REQ-09 | §3 portfolio multipliers wired into portfolio-checkup, scenario-analysis, country-deep-dive | All 3 SKILL.md files reference §3 multiplier application |
| REQ-10 | §7 read-only HV mode wired into pair-finder (dual-single-stock) + due-diligence (single-stock) | Both SKILL.md files reference §7 read-only mode |
| REQ-11 | peer-comparison gets FULL §7 surface: §7.1 note + §7.2 peer-suggest tokens + §7.3 tension banner + §6 audit log | All four sub-section references present in peer-comparison SKILL.md |
| REQ-12 | Concrete e2e test for cio-letter-prep retrofit vs `golden_pack_2026-04.docx`: styles, palette, header image (±5% EMU), section/table counts | `compare_docx.py` exists with all 4 checks; runnable on demand |
| REQ-13 | Tier 1 pilot manual scenarios (3 each for client-review + due-diligence) | Scenarios documented + executed against pilot pair |
| REQ-14 | Tier 2 per-skill mini-scenarios (1 each for the 5 non-pilot HV consumers) | Scenarios documented + executed |
| REQ-15 | DECISIONS.md entry scheduling Tier 1 → integration-pattern.md convergence follow-up PR | grep finds entry in `DECISIONS.md` with stated flip conditions |

## Synthesized Constitution (post-hoc — same caveat)

**Non-Negotiables:**

- **NN-1** Voice-related branding never reaches non-voice consumers (structurally enforced, not prose-enforced)
- **NN-2** `cio-letter-prep` retains its inline voice guardrail; integration-pattern.md remains voice-free
- **NN-3** Graceful degradation: missing logo / corrupt config / schema mismatch never breaks downstream rendering
- **NN-4** Every wired skill must have BOTH the sentinel comment AND a Load directive in proximity (machine-enforced)
- **NN-5** Tier 2 consumers must JIT-reference, not inline-copy, the loader contract

## Spec Fidelity

| REQ | Status | Done-When result | Evidence |
|-----|--------|------------------|----------|
| REQ-01 | Built & verified | pass | 18 tests in `skills/_parallax/white-label/tests/test_loader.py` pass, incl. `test_visual_branding_excludes_voice_and_v2_keys`, `test_visual_branding_voice_in_source_config_is_filtered`, `test_visual_branding_keys_are_subset_of_load_client_branding` (commit db08b84) |
| REQ-02 | Built but Done-When fails (silent expansion) | partial | `grep -E "^## §" integration-pattern.md` finds §1–§8 **plus an unplanned §9 Versioning**. Plan specified §1–§8 only; §9 added in the creation commit (1afa342); not logged in DECISIONS.md → **silent drift** |
| REQ-03 | Built & verified | pass | sentinel at SKILL.md:35, Load directive at SKILL.md:144, voice guardrail intact at SKILL.md:202 ("white-label substitution... never-overridden semantic tokens"); commit 9d1ad32 |
| REQ-04 | Built & verified | pass | `from loader import load_visual_branding` present in exactly 3 SKILL.md files: client-review:100, due-diligence:88, deep-dive:92; 6-key allowlist prose at client-review:114, due-diligence:100, deep-dive:104 (commits db82844, 03ad035, 6344f38) |
| REQ-05 | Built & verified | pass | `test_integration_pattern_referenced.py` parametrizes over all 16 wired skills; all 18 tests pass (15 Tier 2 + cio-letter-prep + root + at-least-one), commit 7697522 |
| REQ-06 | Built & verified | pass | `Pre-Render — Load white-label branding` header found in client-review:90, due-diligence:78, deep-dive:82, cio-letter-prep:142; `Pre-Workflow — Load Active House View` in due-diligence:35 |
| REQ-07 | Built & verified | pass | Regex `(?s)<!--\s*white-label:\s*integration-pattern\.md\s*-->.*?Load.*?integration-pattern\.md` in `test_integration_pattern_referenced.py`; 16 parametrized cases pass (commit 7697522) |
| REQ-08 | Built & verified | pass | macro-outlook SKILL.md:15 ("call it §7.4 by analogy"), :16 (inline §7.4 definition), :42 (Pre-Workflow capture of `view.macro_regime`), :66 ("Post-Workflow — §7.4 Regime alignment check"); commit 90a582d |
| REQ-09 | Built & verified | pass | portfolio-checkup:16,39 (§3 multipliers to factor scoring); scenario-analysis:16 (§3 to replacement-candidate scoring); country-deep-dive:14,39,58 (§3 multipliers to Top Opportunities ranking); commit 886fb0c |
| REQ-10 | Built & verified | pass | pair-finder:18 (§7.3 tension banner + §7.1 note + §6 audit; §7.2 N/A documented), due-diligence:14 (§7 single-stock read-only, §7.1+§7.3+§6, §7.2 N/A); commits 3b7c469, 03ad035 |
| REQ-11 | Built & verified | pass | peer-comparison SKILL.md:14 (FULL §7 surface enumerated), :79–82 (Post-Workflow steps 1–4 implementing §7.3, §7.2, §7.1, §6 in order), :94,97 (Output Format slots); commit 1c54a71 |
| REQ-12 | Built but Done-When not runnable | partial | `compare_docx.py` (225 lines) exists with all 4 checks (a) styles, (b) theme palette, (c) header image ±5% EMU, (d) section/table counts; fixture `golden_pack_2026-04.docx` present. **Cannot execute end-to-end here**: there is no post-retrofit candidate .docx artifact to compare; the script is a one-shot manual gate by design (SKILL.md docstring: "Not a CI test — cio-letter-prep is an LLM-driven Claude skill"). Audit gap: the gate exists but has not been demonstrated to fire green at least once. Commit 9d1ad32 |
| REQ-13 | Not built (or built off-tree) | — | No commit in the audited range adds a scenario log, test, or doc named after the three pilot scenarios in the plan. Plan commit ordering item #6 was "[AUDIT GATE] — 3 scenarios on each pilot" — a process step, not a code commit. No evidence the gate ran. Follow-up. |
| REQ-14 | Built but Done-When not runnable | inferred | Mini-scenarios are described in the locked plan (`portfolio-checkup`: view active with sector tilt +2 → multiplier applied; etc.) and embedded in each SKILL.md's Pre-Workflow / Post-Workflow prose. None of them is executable without a live Parallax MCP session and an active CIO view. Each is "verifiable by manual MCP run", which is the same audit gap as REQ-12 — the protocol exists, the receipt does not. |
| REQ-15 | Built & verified | pass | `DECISIONS.md:160` "2026-05-16: Tier 1 inline branding skills slated for convergence to integration-pattern.md" with explicit flip conditions at :168; commit ebf2da9 |

## Constitution Drift

| Non-Negotiable | Status | Verification method | Notes |
|----------------|--------|---------------------|-------|
| NN-1 Voice never reaches non-voice consumers | Upheld (mechanical) | `test_loader.py::test_visual_branding_excludes_voice_and_v2_keys`, `…::test_visual_branding_voice_in_source_config_is_filtered` both pass; loader uses dict-comprehension over `_VISUAL_BRANDING_KEYS` constant | Structural, not prose-enforced. Adding a key requires touching both the constant and integration-pattern §3 — drift gate is the third loader test |
| NN-2 cio-letter-prep retains inline voice guardrail | Upheld (mechanical) | grep `cio-letter-prep/SKILL.md` for "voice": finds the substitution-table reference (line 202) describing "never-overridden semantic tokens" — i.e., voice/copy never substituted; integration-pattern.md grep for "voice" finds only §6 cross-reference back to cio-letter-prep, not a voice contract | The voice guardrail is now distributed: machine-enforced in `loader.py` (excludes voice key) AND prose-enforced in cio-letter-prep (substitution semantics). Both layers verified. |
| NN-3 Graceful degradation | Upheld (mechanical) | `test_loader.py::test_missing_config`, `…::test_corrupt_yaml`, `…::test_schema_invalid`, `…::test_one_logo_missing`, `…::test_both_logos_missing`, `…::test_schema_unavailable` all pass; loader returns shape with `error` field, never raises | Six failure modes mapped to six tests; downstream skills branch on `branding["error"]` |
| NN-4 Sentinel + Load directive proximity | Upheld (mechanical) | `test_integration_pattern_referenced.py` regex `(?s)<!--\s*white-label:\s*integration-pattern\.md\s*-->.*?Load.*?integration-pattern\.md` passes for all 16 wired skills | Note: regex is `(?s)` (DOTALL) and `.*?` — proximity is "anywhere after sentinel" not "within N chars". A skill that put sentinel at top and Load directive 200 lines later would still pass. Adequate for current scale; brittle if file shape diverges |
| NN-5 Tier 2 must JIT-reference, not inline-copy, the loader contract | Upheld (mechanical) | `grep -rln "from loader import load_visual_branding" skills/ --include="*.md"` returns exactly 3 files: client-review, due-diligence, deep-dive (the Tier 1 set). 13 other wired skills mention `load_visual_branding()` in prose but do NOT inline the Python snippet | The distinguishing test is the import statement, not the function name. A future drift-gate addition could assert "Tier 2 skills must NOT contain the import line" |

## Plan vs Shipped

Plan locked 15 ordered items (14 commits + 1 audit gate). Shipped 14 commits in the same order.

| Sha | Subject | Classification |
|---|---|---|
| `db08b84` | `feat(white-label): add load_visual_branding() wrapper for non-voice consumers` | **In scope** (REQ-01) |
| `1afa342` | `docs(white-label): add integration-pattern.md (§1-§8 shared contract)` | **Scope expansion (silent)** — also added §9 Versioning. Plan said §1–§8. Not logged in DECISIONS.md. → propose backfill |
| `9d1ad32` | `refactor(cio-letter-prep): retrofit to consume integration-pattern.md` | **In scope** (REQ-03 + REQ-12). Bundles the compare_docx.py e2e gate as the plan specified |
| `db82844` | `feat(client-review): wire white-label branding (Tier 1 pilot, inline)` | **In scope** (REQ-04, REQ-06) |
| `03ad035` | `feat(due-diligence): wire white-label branding + §7 read-only hv` | **In scope** (REQ-04, REQ-06, REQ-10) |
| *(plan item 6: AUDIT GATE)* | *no commit* | **Process step skipped or done off-tree** — no scenario log committed; no evidence of execution. → REQ-13 finding |
| `6344f38` | `feat(deep-dive): wire white-label branding (Tier 1 closeout)` | **In scope** (REQ-04, REQ-06) |
| `b2ce975` | `feat(tier2-batch-a): wire branding into 4 portfolio skills` | **In scope** (REQ-05) — morning-brief, portfolio-builder, rebalance, explain-portfolio |
| `e70b391` | `feat(tier2-batch-b): wire branding into should-i-buy + thematic-screen` | **In scope** (REQ-05) |
| `886fb0c` | `feat(tier2-batch-c): wire branding + NEW §3 hv into 3 portfolio skills` | **In scope** (REQ-05, REQ-09) |
| `3b7c469` | `feat(pair-finder): wire branding + NEW §7 hv (dual-single-stock)` | **In scope** (REQ-05, REQ-10) |
| `1c54a71` | `feat(peer-comparison): wire branding + FULL §7 hv` | **In scope** (REQ-05, REQ-11) |
| `90a582d` | `feat(macro-outlook): wire branding + NEW §7.4 regime-alignment mode` | **In scope** (REQ-05, REQ-08) |
| `7697522` | `test(white-label): drift gate for integration-pattern.md consumers` | **In scope** (REQ-07) |
| `ebf2da9` | `docs(decisions): schedule Tier 1 -> integration-pattern.md convergence PR` | **In scope** (REQ-15) |

Two findings of substance:

1. **§9 Versioning was added silently.** The commit message for `1afa342` does not mention §9; the locked plan does not mention §9; DECISIONS.md does not mention §9. The section is harmless in content (it documents the additive-only key contract and points at the third loader test as the drift gate) — but the change discipline failed: it should have been a separate commit or a logged amendment.
2. **The AUDIT GATE was a process step with no artifact.** Plan item #6 specified "3 scenarios on each pilot" between the Tier 1 pilots and Tier 1 closeout. There is no commit, no test file, no scenario log added in that slot. The gate either ran verbally and the result was not captured, or it was skipped. Either way, REQ-13 is unverifiable.

## Lessons

- **Synthesizing requirements from a locked plan + design spec works mechanically but degrades the audit's signal.** The interesting findings (§9 silent expansion, missing AUDIT GATE artifact) emerged because the plan note happened to be detailed enough to back-derive REQ-XX. A leaner plan would have left the synthesis underdetermined. **For real production features going forward, the requirements doc has to be written first** — `/analyze-implementation` is genuinely degraded without it. (Source: this audit.)
- **Drift gates that check structure are cheap and work.** `test_integration_pattern_referenced.py` (regex over 16 SKILL.md files) and `test_visual_branding_keys_are_subset_of_load_client_branding` (assertion over a Python constant) caught the two highest-stakes invariants (NN-4, NN-1) in O(ms). The cost was one test file each. (Source: commits 7697522, db08b84.)
- **Tier 1 vs Tier 2 split is a temporary state by deliberate design.** The decision was logged with explicit flip conditions (DECISIONS.md:168) — not a silent split-brain. This is the discipline §9 lacked. (Source: DECISIONS.md:160–168.)
- **The e2e test that "runs on demand only" is a category gap.** REQ-12's `compare_docx.py` exists, has 4 checks, and is well-documented — but it has never demonstrably fired green because the cio-letter-prep retrofit hasn't been exercised against the golden pack post-commit. A gate that has never run is not a gate. (Source: `skills/cio-letter-prep/scripts/compare_docx.py`.)

## Follow-ups

- [ ] **Backfill DECISIONS.md entry for §9 Versioning** in integration-pattern.md (silent scope expansion in commit 1afa342). Rationale should be: additive-only contract documentation; future key additions require updating §9 + `_VISUAL_BRANDING_KEYS` + the third loader test together. Treats §9 as policy, not text.
- [ ] **Run cio-letter-prep retrofit against golden_pack_2026-04 once and commit the receipt.** Either (a) produce a post-retrofit candidate .docx and run `compare_docx.py`, capturing exit code 0 in a one-line log under `docs/analysis/`; or (b) downgrade the gate to "documented manual check" and remove the claim that it's an automated gate. Don't leave the gate dark.
- [ ] **Resolve the AUDIT GATE artifact gap (REQ-13).** Either (a) commit a brief scenario log (3 lines per pilot × 3 scenarios × 2 pilots) showing the gate ran, or (b) acknowledge it was skipped and assess whether the Tier 1 pilots ever got their pre-Tier-1-closeout review. Don't ship a process gate that left no trace.
- [ ] **Tighten the drift-gate regex if it ever produces a false positive.** Current proximity check is `(?s).*?` (anywhere-after-sentinel). If a maintenance edit moves the Load directive far from the sentinel without breaking it, the gate won't catch it. Consider a max-character distance or section-anchor constraint when the failure first appears.
- [ ] **Add a "no inline `from loader import load_visual_branding` in Tier 2" drift gate.** Currently NN-5 is upheld by manual grep. Mirror the REQ-07 pattern: a parametrized test over the 13 Tier 2 SKILL.md files asserting the import statement is absent. Cheap, prevents copy-paste regression at the convergence PR.
- [ ] **For the next Constitution + REQ-XX feature, write the requirements doc BEFORE coding.** The single highest-value follow-up. The current audit's degraded-input synthesis cost ~20 minutes and produced a real but cloudier picture than it would have with a proper preamble.

## Cross-references

- DECISIONS.md entries proposed (drafted, awaiting user approval):
  1. *§9 Versioning section added to integration-pattern.md without plan / DECISIONS approval (silent scope expansion).* **Why:** additive-only key contract documentation; the constant `_VISUAL_BRANDING_KEYS` in loader.py is the machine-enforced source of truth and `test_visual_branding_keys_are_subset_of_load_client_branding` is the drift gate; §9 documents the human-readable side of that contract. **Flip conditions:** if a new key gets added without updating all three (constant, §3 list, §9 versioning note) in the same commit, escalate to a real schema-version field. **Status:** approved retroactively.
- LEARNINGS.md entries proposed (drafted, awaiting user approval):
  1. *Drift gates that test structure are the cheapest invariant — write one per Non-Negotiable that can be tested with a regex over file contents.* Triggers: integration-pattern.md consumer pattern (REQ-07); voice-key subset enforcement (REQ-01).
  2. *Requirements-first beats requirements-synthesized.* The audit dogfood run was useful but the synthesis step is the failure mode `/analyze-implementation` was designed to catch — running it on a feature without a Constitution + REQ-XX doc inverts the skill's purpose. Future production features get the doc before the first commit.
  3. *"Manual on-demand" gates need at least one captured receipt before they count.* The cio-letter-prep e2e test exists, is correct, and has never run. The discipline is: any gate that ships must run once with the output logged.
