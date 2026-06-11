# Auto-on-load house-view drift check

JIT-loaded by parallax-portfolio-builder, parallax-rebalance, and
parallax-thematic-screen. Single source of truth so changes to the
pattern don't require touching 3 files.

## When to fire

Fire ONLY when ALL of:
1. An active house view exists (`view_status` returns state other than `none`).
2. View age > 30 days (`view_status.banner.days_since_effective > 30`).
3. The consuming skill has not received `--skip-drift-check` flag.

## How to invoke

1. Call `/parallax-judge-house-view --dry --json` (the `--dry` flag uses
   the same MCP fan-out shape but skips the LLM-as-judge recommendation
   step; the `--json` flag returns structured output).
2. If the judge skill is NOT installed (ImportError or skill directory
   missing): surface a single-line preamble note: "/parallax-judge-house-view
   not installed; drift check skipped." Do NOT fail or warn — continue
   with the consuming skill's normal flow.
3. Parse the returned `severity` field.
4. If `severity == "drift_material"`: surface a one-line banner ABOVE the
   consuming skill's output:
   "⚠️ House view drift detected (material). Last refreshed N days ago.
   Run /parallax-judge-house-view for the full report or
   /parallax-load-house-view to update."
5. Otherwise (drift_minor or drift_moderate): no banner. The user does
   not need to know about minor drift in every consumer skill load.

## What NOT to do

- Do NOT call the judge LLM step (`--dry` is mandatory).
- Do NOT modify the active view.
- Do NOT block the consuming skill on judge failure — graceful skip is
  always the right behavior.
- Do NOT cache the judge result across consuming skill invocations within
  a single Claude session (acceptable v0 — cadence.py handles in-skill
  caching).