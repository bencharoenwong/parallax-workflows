# PR #25 follow-up — Tier 2 import-line drift gate scope

**Status:** PARTIALLY COVERED. Existing drift gate detects sentinel↔body-reference pairing but does NOT verify the body reference is the canonical load directive a model would actually execute.

> **Branch state (as of writing 2026-05-17):** `test_integration_pattern_referenced.py` lives on `feat/wire-branding-houseview-skills` (PR #25, OPEN). It is NOT yet on `main`. The 18-test passing count below reflects the branch state; will be on `main` after PR #25 merges.

## What was specced

The drift gate test (`skills/_parallax/white-label/tests/test_integration_pattern_referenced.py`) was specified to:

- For each SKILL.md carrying the sentinel `<!-- white-label: integration-pattern.md -->`, assert the body also carries a load directive within 200 characters of `integration-pattern.md`.
- Regex: `(?:load|jit-load|consume|apply)\b[^.\n]{0,200}?integration-pattern\.md` (case-insensitive).

## What was actually shipped

- ✅ 18 tests passing: 16 wired skills + 2 smoke checks.
- ✅ Covers Tier 1 inline (3 skills with sentinel but inlined snippet — sentinel is metadata, body still mentions integration-pattern.md as reference).
- ✅ Covers Tier 2 (12 skills with sentinel + JIT-ref directive in body).
- ✅ Covers cio-letter-prep retrofit (sentinel + ref).

## Gap

The test asserts a **textual** pattern: "verb within 200 chars of `integration-pattern.md`". It does NOT assert the directive is structurally embedded as an instruction Claude will execute at runtime. Three drift cases pass the test but produce silent wiring failure:

1. **Reference in a comment / footnote.** A future author writing `<!-- TODO: move integration-pattern.md content elsewhere -->` AND `Load some-other-file.md` (with `integration-pattern.md` only in the comment, but `load` verb proximate to `integration-pattern.md` via the HTML comment text) could pass the regex without a real runtime load.

2. **Reference in a `--- DEPRECATED ---` section.** Same regex match, no runtime effect.

3. **Reference in a code block as illustrative, not directive.** Example: a docstring showing `Load _parallax/white-label/integration-pattern.md` as illustration of what a NEW skill author should do, while the skill itself does not JIT-load it.

## Recommended follow-up

**P2 (regex tightening + structural check):** Two layers.

**Layer 1 — Regex tightening (small fix, covered separately):** see [[2026-05-17-drift-gate-regex-tightening]].

**Layer 2 — Structural assertion:** require the load directive to live OUTSIDE of:
- HTML comments (`<!-- ... -->`)
- Code blocks (triple-backtick fenced regions)
- "Deprecated" / "TODO" / "Example" labeled sections (regex-tagged)

Implementation sketch: pre-process the SKILL.md to strip HTML comments and code blocks, then apply the load-directive regex to the remainder. Add a test scenario per drift case (fixture SKILL.md files demonstrating each false-positive pattern; assert the strengthened gate FAILS them).

**P3 (semantic assertion):** longer-term — assert the load directive appears under a Workflow section (heading-aware parsing). The gate becomes "the directive is in a position a model executing the workflow would actually reach." Heavier; deprioritize unless Layer 2 still false-positives in observed drift.

## Risk if deferred

LOW. No current skill triggers the false-positive patterns. The latent drift only materializes if a future SKILL.md edit introduces one of the three cases. PR review catches it manually if reviewers look.

## Related

- PR #25 adversarial-reviewer BUG-005 (sentinel test scope)
- [[2026-05-17-drift-gate-regex-tightening]]
- [[2026-05-17-audit-gate-artifact]]
