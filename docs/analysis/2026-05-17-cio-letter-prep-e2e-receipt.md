# PR #25 follow-up — cio-letter-prep retrofit e2e receipt

**Status:** NOT RUN. Documented as a one-shot manual procedure; not yet executed against a real post-retrofit `.docx`.

> **Branch state (as of writing 2026-05-17):** `compare_docx.py` and the retrofit procedure live on `feat/wire-branding-houseview-skills` (PR #25, OPEN). They are NOT yet on `main`. The "What was actually shipped" section below describes the state of that branch; once PR #25 merges, fill in the merge date here.

## What was specced

Per `skills/cio-letter-prep/SKILL.md` (Output Format → "Retrofit gate procedure"):

1. Confirm `~/.parallax/client-branding/config.yaml` does NOT exist (default-Parallax path).
2. Run `/parallax-cio-letter-prep` with the worked-example three-holding fixture. Save as `post-retrofit.docx`.
3. Run `python skills/cio-letter-prep/scripts/compare_docx.py post-retrofit.docx fixtures/golden_pack_2026-04.docx`.
4. Expected: PASS on fonts, palette, section / table-row counts. Any FAIL blocks the retrofit.

## What was actually shipped

- ✅ `scripts/compare_docx.py` written and smoke-tested via self-comparison (golden == golden → PASS).
- ✅ Procedure documented inline in SKILL.md.
- ❌ No `post-retrofit.docx` ever generated. Real comparison never performed.
- ❌ No commit / receipt artifact exists proving the retrofit produces equivalent output.

## Gap

The retrofit is the only commit in PR #25 that modifies a production-working skill (`cio-letter-prep`). The structural verification (script self-test + ~75-line SKILL.md diff review) is strong evidence the retrofit is correct, but it is NOT direct evidence. A subtle behavior change in the `docx` skill chain or in how the model interprets the relocated substitution table would only surface when an actual CIO letter is generated.

## Recommended follow-up

**P1 (one-shot, cheap):** Generate a single post-retrofit `.docx` with the worked-example fixture, run `compare_docx.py`, archive the output + PASS receipt to `docs/analysis/cio-letter-prep-retrofit-receipt-<DATE>.md`. ~10 min of operator time.

**Acceptance criterion:** `compare_docx.py` returns exit 0 with the exact string `PASS — fonts, palette, logo properties, sections, and table rows identical between candidate and golden.` (note the `between candidate and golden.` suffix is part of the literal output — operators parsing programmatically should match the full string, not a prefix).

**Trigger to execute:** before the first real client invocation of `/parallax-cio-letter-prep` post-merge, or within 1 week of merge, whichever comes first.

## Risk if deferred

LOW — the retrofit changes are mechanical (sentinel + JIT-ref + Output Format table relocation). A subtle regression would surface visibly on first real client letter rather than silently. But the gate exists precisely to catch it pre-issue, not post.

## Related

- PR #25: feat/wire-branding-houseview-skills
- Adversarial reviewer BUG-002: e2e test concrete spec
- [[2026-05-17-audit-gate-artifact]]
