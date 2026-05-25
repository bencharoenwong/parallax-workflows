# Skill Structure & Length Conventions

Conventions for how `skills/<name>/SKILL.md` should be organized as the file grows. Established 2026-05-06 per council deliberation (notes/2026-05-06-1023-council-white-label-restructure.md). Pairs with `jit-load-compliance-audit.md` — the audit protocol that gates any structural restructure.

JIT-load this file before drafting a new skill, before committing any change that adds ≥100 lines to an existing SKILL.md, and during periodic skill-evolve passes.

## Why this exists

`SKILL.md` files are loaded by Claude Code at session start. Every line in every SKILL.md the operator might invoke is a token tax paid before any work begins. As skills accumulate functionality, SKILL.md size drifts upward; the median across `parallax-workflows/skills/` was 340 lines as of 2026-05-06 with one outlier at 969. Without a convention, the outlier multiplies — three skills at >800 lines means triple the tax even when none of them is invoked.

`references/` files are JIT-loaded only when SKILL.md directs them. Splitting reference material out of SKILL.md and behind explicit load directives reclaims session context for the work the operator actually came to do.

The pattern is established outside this convention by `translate-chinese-finance` (7 references files), `translate-thai-finance` (5), and `_parallax/house-view/` (10+ Python module files plus references). This convention codifies what those skills did organically.

## When to split

A SKILL.md should be split into orchestrator + references/ when **any one** of the triggers below fires:

| Trigger | Threshold |
|---|---|
| Total line count | >500 lines |
| Distance above sibling median | >2× the median across `skills/<name>/SKILL.md` |
| Step count in workflow | >7 steps with substantial sub-content |
| Operator complaint | "I can never find X" said about this skill twice |

Below these thresholds, keep the SKILL.md monolithic. Splitting too early fragments the workflow and forces JIT-load round-trips for content the operator needs every time.

## What stays in SKILL.md (the orchestrator)

The orchestrator is the file the model reads at every invocation. It contains:

1. **Frontmatter** — `name`, `description`, `negative-triggers`, `gotchas`
2. **Usage** — how to invoke (CLI examples)
3. **Where artifacts live** — paths the skill reads/writes
4. **Integration with downstream skills** — the consumer contract
5. **Workflow skeleton** — Steps 0 → N as numbered headings, each with a one-paragraph summary AND an explicit `→ Load references/<file>.md` directive when the step's full content lives in references/
6. **Operational modes** — `--status`, `--clear`, etc., one row each
7. **Success criteria** — what "done" looks like
8. **Failure modes the operator MUST know without loading anything else** — security gates, compliance gates, irreversible-action warnings

Target: ≤250 lines. The orchestrator should be navigable in one screen-scroll.

## What moves to references/

Anything that:

- Has its own logical name (`error-handling.md`, `validation-rules.md`, `voice-frameworks.md`)
- The operator only consults when a specific trigger fires (`load_when: error_X`)
- Is reference material rather than runtime workflow
- Has table-heavy or example-heavy content that bloats the orchestrator

Suggested file organization:

```
skills/<name>/
├── SKILL.md                       # orchestrator (≤250 lines)
├── INSTALLATION.md                # one-time setup; loaded only on first install
├── README.md                      # human-facing index; "operator → SKILL.md, devops → INSTALLATION.md"
└── references/
    ├── step-N-<topic>.md          # deep workflow per step (loaded when step fires)
    ├── error-handling.md          # error-table content (loaded when error fires)
    ├── operational-modes.md       # --status/--clear/--audit details
    ├── validation-rules.md        # validator details
    ├── frameworks.md              # background patterns this skill is built on
    └── examples/<scenario>.md     # walkthroughs (loaded only when operator asks)
```

`README.md` and `INSTALLATION.md` can be consolidated into a single README with an operator/Claude/devops fork at the top.

## JIT-load directive convention

Every reference moved out of the orchestrator must be reachable through an explicit directive in SKILL.md. The directive is the seam — without it, the model has no signal to load the file.

Two valid forms:

```markdown
### Step 3 — Validate assets

Run validators in parallel. → Load references/step-3-validation.md for the
full validator catalog and per-validator gate logic.
```

Or as a frontmatter gotcha:

```yaml
gotchas:
  - JIT-load references/voice-frameworks.md before composing the voice block
    in Step 1.5 — it carries the Lago 7-section template + Rezvani Tone Matrix
    + Genesys 4-phase reference that the prompt is built on.
```

The directive must:

1. Name the file by relative path (`references/<file>.md`).
2. State the trigger condition (when to load).
3. Be present at the call site (not buried in the README).

## Build-time check

`build-skills.sh` should grow a check that:

1. Greps every SKILL.md for `references/<name>.md` patterns
2. Asserts each referenced file exists
3. Fails the build if any directive points at a missing file

This is the JIT-load directive drift mitigation flagged by Reviewer A in the council session. Until that check ships, JIT-directive drift is a silent-failure mode — a renamed file leaves the directive pointing nowhere, and the model proceeds without the reference (often paraphrasing from training rather than erroring).

Implementation sketch (~20 lines of bash):

```bash
# inside build-skills.sh, after coverage-lint
for skill_md in skills/*/SKILL.md; do
  skill_dir=$(dirname "$skill_md")
  while IFS= read -r ref; do
    if [ ! -f "$skill_dir/$ref" ]; then
      echo "FAIL: $skill_md references $ref but file does not exist"
      exit 1
    fi
  done < <(grep -oE 'references/[a-zA-Z0-9_-]+\.md' "$skill_md" | sort -u)
done
```

## Migration protocol (for splitting an existing SKILL.md)

Splitting is reversible but costs reviewer attention. Follow this protocol so a split commit is small and atomic:

1. **Pre-flight (≤30 min)** — see `jit-load-compliance-audit.md`. Run a representative invocation against the current monolithic SKILL.md and capture whether the model would have loaded references/ files if they existed (i.e., does the model honor `→ Load X.md when Y` directives in practice). If the audit fails, do NOT split — strengthen the directives first.

2. **Draft the orchestrator skeleton FIRST** — write the ≤250-line orchestrator with explicit load directives BEFORE moving any content. This forces the load-sequence question to surface before code is moved. Common mistake: extract content first, write directives later → directives drift.

3. **Move content in one commit per file** — `references/step-3.md` is one commit, `references/error-handling.md` is another. Don't bundle. Smaller diffs are easier to review and easier to revert.

4. **Run the build-time check + a fresh-session walkthrough** — both must pass before merging. The build-time check catches drift; the fresh-session walkthrough catches behavioral degradation (model skipping the loads).

5. **Update the build_skills.sh package list** if the skill ships as a `.skill` artifact — the new references/ files must be included in the zip.

## Anti-patterns

The following patterns have been considered and rejected:

- **`INDEX.md` / `NAVIGATION.md` as a separate top-level file** — rejected by 4/5 advisors in council. A third source of truth competing with SKILL.md and DECISIONS.md drifts within months. The skills/ directory listing IS the navigation. Use README.md if you need a human-facing entry-point fork.

- **TOC at the top of an unsplit SKILL.md** — provides 1% of the value of an actual split for 50% of the noise. Skip; either split or live with the monolith.

- **Splitting Python infrastructure (`extract.py`, `loader.py`) into a package solely to mirror SKILL.md splits** — Python files don't load into Claude's context. Split a Python module only when the module exceeds ~800 lines AND has ≥5 distinct responsibilities. The white-label `extract/` package split was justified by both criteria; mirror-splitting smaller modules is over-engineering.

## Description / Trigger Completeness

When a skill exposes a flag or mode that materially changes its output workflow (examples: `--augment-silent` in portfolio-builder, basket vs. single-ticker in AI-soros, `--macro` / `--no-macro` in thematic-screen), the frontmatter `description` must include at least one natural-language trigger phrase that an operator would type without knowing the flag name. This ensures the Codex matcher surfaces the mode to white-label operators and that natural-language invocations don't silently hit the default path when the operator wanted the mode.

**Rule: new flag or mode added to a skill from 2026-05-25 onward → one trigger phrase in `description` before merge.** No exceptions for "advanced" or "opt-in" modes — those are precisely the modes that get lost without a trigger phrase. The trigger phrase should be operator-vocabulary, not internal terminology (e.g., "fill house view gaps from Parallax data" not "augment silent dimensions via gap_detect").

**Scope is forward-only.** A retroactive audit found 10+ existing skills with flag modes (judge-house-view, load-house-view, make-house-view, etc.) lacking trigger phrases. That backlog is NOT closed by this rule — it is accepted debt with no scheduled cleanup. New skills (added 2026-05-25 onward) must comply; existing skills are exempt until separately scoped.

**Enforcement seam:** none today. The rule depends on author discipline and PR review. A future addition to `build-skills.sh` could lint skills with `--`-prefixed flags in Usage blocks for trigger-keyword presence in description — see the JIT-load build check above as the implementation template.

PRISM-vocabulary guard: trigger phrases ship verbatim to white-label deployments via the Codex matcher index. Do not embed proprietary signal names, factor decomposition labels, or pillar vocabulary in trigger strings. Generic finance language only.

## Provenance

- Council session: `notes/2026-05-06-1023-council-white-label-restructure.md`
- DECISIONS.md entry: 2026-05-06 (later) — white-label-onboard restructure, Phase 2 conditional
- Companion file: `jit-load-compliance-audit.md`
- Description / Trigger Completeness rule added 2026-05-25 per tech-debt closeout audit covering AI-soros basket-mode invisibility and portfolio-builder --augment-silent undiscoverability.
