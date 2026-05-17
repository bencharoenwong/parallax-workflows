# PR #25 follow-up — drift-gate regex tightening

**Status:** LATENT. No current consumer trips the gap; flagged in PR #25 gate review for future-author awareness.

## What was specced

`LOAD_DIRECTIVE_RE` in `test_integration_pattern_referenced.py`:

```python
LOAD_DIRECTIVE_RE = re.compile(
    r"(?:load|jit-load|consume|apply)\b[^.\n]{0,200}?integration-pattern\.md",
    re.IGNORECASE,
)
```

Intent: detect a load directive (`Load <something> integration-pattern.md`) within 200 characters of the verb, on the same logical line / span.

## What was actually shipped

The regex as-written.

## Gap

The character class `[^.\n]{0,200}?` excludes periods. A future skill author writing:

> Load `loader.md` and `integration-pattern.md` for the full contract.

would NOT match the regex because the period inside `loader.md` terminates the span before the regex reaches `integration-pattern.md`. The directive is real; the gate would fail it spuriously.

All current consumers wrap the reference in backticks and structure the sentence to avoid a period between verb and `integration-pattern.md`, so no consumer currently trips this. Latent trap for next-time authors who write more natural prose.

## Recommended follow-up

**P3 (small fix):** Drop the period exclusion. The canonical Tier 2 phrasing wraps the target in backticks (`` `_parallax/white-label/integration-pattern.md` ``), so the target literal lives INSIDE backticks. A naive backtick-aware regex (e.g., the alternation `(?:[^\n` + "`" + `]|` + "`" + `[^` + "`" + `\n]*` + "`" + `){0,200}?` consuming backtick spans wholesale) breaks the 16 existing consumers because the backtick span eats the target. **DO NOT use that pattern — empirically verified to fail all 16 wired SKILL.mds.**

The correct minimal regex simply drops the period exclusion:

```python
LOAD_DIRECTIVE_RE = re.compile(
    r"(?:load|jit-load|consume|apply)\b[^\n]{0,200}?integration-pattern\.md",
    re.IGNORECASE,
)
```

The 200-char bound prevents runaway matches across paragraphs (the newline exclusion is preserved). Periods inside filenames are now permitted because they're no longer excluded.

**Acceptance criteria:**

1. All 16 wired SKILL.mds still pass (regression).
2. A fixture SKILL.md with text "Load `loader.md` and `integration-pattern.md`" passes.
3. A fixture SKILL.md with text "Load integration-pattern. Maybe someday. Look at integration-pattern.md somewhere far down" does NOT pass (false-positive guard preserved).

## Risk if deferred

LOW. No consumer trips it today. Becomes relevant the first time a future PR author writes a load directive containing multiple `.md` references on the same line.

## Notes

This is independent of (but complementary to) the structural-assertion strengthening in [[2026-05-17-tier2-import-line-drift-gate]]. The regex fix is a minimal patch; the structural assertion is a category-level fix.

## Related

- PR #25 gate review finding (Round 1, item 4)
- [[2026-05-17-tier2-import-line-drift-gate]]
- [[2026-05-17-audit-gate-artifact]] — surfaced this item via the broader audit-gate review
