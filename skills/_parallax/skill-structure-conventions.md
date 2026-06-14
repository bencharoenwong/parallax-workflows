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

1. **Frontmatter** — `name` and `description` only (agentskills.io spec; see "Spec compliance" below)
2. **`## When not to use`** — negative triggers, first body section after the H1
3. **`## Gotchas`** — operational gotchas + JIT-load directives, second body section
4. **Usage** — how to invoke (CLI examples)
5. **Where artifacts live** — paths the skill reads/writes
6. **Integration with downstream skills** — the consumer contract
7. **Workflow skeleton** — Steps 0 → N as numbered headings, each with a one-paragraph summary AND an explicit `→ Load references/<file>.md` directive when the step's full content lives in references/
8. **Render step (deterministic gate)** — mandatory final `mktemp` + `cat` + `python3 _parallax/render_gate.py` Bash block for report skills (see `parallax-conventions.md §10`)
9. **Operational modes** — `--status`, `--clear`, etc., one row each
10. **Success criteria** — what "done" looks like
11. **Failure modes the operator MUST know without loading anything else** — security gates, compliance gates, irreversible-action warnings

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

Or as a bullet in the `## Gotchas` body section:

```markdown
## Gotchas

- JIT-load references/voice-frameworks.md before composing the voice block
  in Step 1.5 — it carries the Lago 7-section template + Rezvani Tone Matrix
  + Genesys 4-phase reference that the prompt is built on.
```

The directive must:

1. Name the file by relative path (`references/<file>.md`).
2. State the trigger condition (when to load).
3. Be present at the call site (not buried in the README).

**Two path shapes, two bases.** `references/<file>.md` resolves relative to the skill's own directory. The shared `_parallax/<file>.md` prefix (used by 30+ Parallax skills for conventions, house-view, white-label) resolves relative to the *skills root* — `_parallax/` is a sibling of every skill directory, reachable at `~/.claude/skills/_parallax/` (a symlink to `parallax-workflows/skills/_parallax/`). If a bare `_parallax/...` path does not resolve from the current working directory (e.g. CWD is a project repo, not the skills root), fall back to the absolute `~/.claude/skills/_parallax/<file>.md` rather than hunting or paraphrasing from memory.

## Build-time check

`build-skills.sh` runs two reference-integrity lints in its `RUN_LINT` block; both hard-fail the build:

1. **JIT-load directive lint** (`lint_jit_directives`, inline) — every `references/<name>.md` directive in a SKILL.md must resolve to a real file (local, `../sibling`, or bare cross-skill). Closes the silent-drift mode where a renamed reference file leaves the directive pointing nowhere and the model paraphrases from training instead of erroring.
2. **Section-reference lint** (`_parallax/scripts/section-ref-lint.py`) — every `<file>.md §N[.M]` cross-reference must resolve to a heading in the named file. Closes the same drift class for section pointers (the kind of bug where a `§N.M` pointer outlives its heading). Scoped to cross-file refs — bare intra-file `§N.M` is too noisy (~870 in-repo) to disambiguate; recognizes indented headings, resolves bare `SKILL.md §N` to the sibling SKILL.md, and ignores refs inside HTML comments.

Both replaced earlier author-discipline-only enforcement (the JIT lint was originally specced here as a future "should grow" check; it and the section-ref lint now ship). Trigger-completeness (`--`-flag ↔ description-keyword) remains an unbuilt seam — see "Description / Trigger Completeness" below.

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

Proprietary pillar/factor vocabulary guard: trigger phrases ship verbatim to white-label deployments via the Codex matcher index. Do not embed proprietary signal names, factor decomposition labels, or pillar vocabulary in trigger strings. Generic finance language only.

## Canonical source & path resolution

`parallax-workflows/` is the single source of truth for every `parallax-*` skill and for the shared `_parallax/` conventions, house-view modules, schemas, and white-label loaders. `~/.claude/skills/` consumes them as symlinks into this repo — but symlink coverage is **partial**: `_parallax`, `parallax-should-i-buy`, and most consumer skills are symlinked, while a few (e.g. `parallax-template`, `parallax-deck-prep`) are `~/.claude`-native real directories. Treat that split as a hazard, not a convenience.

1. **Resolve before you read or edit.** Before a should-i-buy / two-lens / house-view workflow JIT-loads any `_parallax/...` path, resolve it to the canonical `parallax-workflows/skills/_parallax/` file. Do not assume the installed skill directory contains it — `ls -l` / `readlink` the path when unsure (a directory symlink resolves its children through canonical; a native fork does not).
2. **Never edit a forked or divergent copy of canonical content.** Shared `_parallax/...` conventions and every symlinked skill are edited in `parallax-workflows` — in `~/.claude` the entry *is* the symlink, not a separate file. A `~/.claude`-native real directory (e.g. `parallax-template`, `parallax-deck-prep`) is canonical for its *own* SKILL.md, but must never host edits to shared behavior, and must never be `cp -R`'d into a second divergent copy. A change written to a fork drifts silently from canonical and is invisible to every other consumer.
3. **Verify the unit you graded is the unit that runs.** When auditing or editing a registered skill, first confirm whether `~/.claude/skills/<name>` is a symlink (edit canonical) or a native dir (edit in place, and flag whether it should be migrated to canonical). `cp -R` of a dir-symlink re-links to the same target — use `cp -RL` for a true throwaway copy. (Mirrors the "measure the deployed unit; check the directory symlink" rule in `CLAUDE.verification.md`.)

## Provenance

- Council session: `notes/2026-05-06-1023-council-white-label-restructure.md`
- DECISIONS.md entry: 2026-05-06 (later) — white-label-onboard restructure, Phase 2 conditional
- Companion file: `jit-load-compliance-audit.md`
- Description / Trigger Completeness rule added 2026-05-25 per tech-debt closeout audit covering AI-soros basket-mode invisibility and portfolio-builder --augment-silent undiscoverability.

## Spec compliance (agentskills.io)

Every skill in this repo conforms to the [agentskills.io specification](https://agentskills.io/specification):

- **Frontmatter** may contain only the spec's top-level keys: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`. House content (negative triggers, gotchas) lives in the `## When not to use` and `## Gotchas` body sections — never in frontmatter. This also eliminates the YAML-quoting hazard of markdown prose inside YAML lists.
- **`name`** is 1–64 chars of lowercase `a-z0-9-` (no leading/trailing/consecutive hyphens) and **must match the skill's directory name**.
- **`description`** is 1–1024 chars and carries both what the skill does and when to use it (including the NOT-for routing clauses).
- **Body** target stays ≤250 lines per the orchestrator rule above (spec recommends <500).

Known accepted deviations:

- Shared `_parallax/...` references resolve outside the individual skill directory (the spec recommends references one level deep inside the skill). The shared-conventions architecture is deliberate; `.skill` packaging for claude.ai inlines or excludes these as needed.
