# JIT-Load Compliance Audit Protocol

<!-- authority: contract -->
<!-- verified: 2026-09-05 -->
<!-- overrides: none -->

A protocol for validating that a skill loads its references when instructed. Use it with [skill-structure-conventions.md](skill-structure-conventions.md), which defines when to split an orchestrator.

JIT-load this file before any SKILL.md restructure, and after any change that adds or modifies a `→ Load references/<file>.md` directive.

## Why this exists

JIT-load directives instruct a model to read a reference. A tool-use transcript must establish whether the model followed that instruction.

The downside risk is real and asymmetric: a 150-line orchestrator with six "→ load references/X.md when Y" directives may produce *worse* outcomes than a 969-line monolith if Claude skips loads and operates on incomplete context. Tokens saved at session start are recouped only if the loads actually happen when needed.

This audit establishes whether they happen.

## When to run

Mandatory:

- Before any SKILL.md restructure that moves >150 lines of content into references/
- Before merging a PR that adds 3+ new `→ Load references/<file>.md` directives
- After any rename of a referenced file (drift check)
- Quarterly across the top-3 most-invoked skills (drift check)

Optional but recommended:

- During `skill-evolve` runs over a skill that has split content
- When operator reports "the model gave a generic answer" and the skill has reference content the directives should have pulled in

## What it checks

Two compliance levels, audited together:

### Level 1 — Static directive validity

For every `references/<name>.md` mentioned in SKILL.md:

1. The file exists at the referenced path
2. The file has non-trivial content (not stub-only)
3. The directive surrounding the reference includes a clear trigger condition

This is the static check that `build-skills.sh` should enforce per the convention. It catches drift but says nothing about whether the model actually executes the directive.

### Level 2 — Behavioral compliance

Run a representative invocation in a fresh Claude Code session and observe whether the model loads each referenced file when its trigger fires. This is the load-bearing audit.

Three possible behaviors per directive:

| Behavior | Meaning | Verdict |
|---|---|---|
| Load fires when trigger condition is met | Compliant | Pass |
| Trigger fires but load is skipped; model paraphrases from surrounding context | Non-compliant | **Fail** — directive needs strengthening or the content moves back inline |
| Trigger does not fire because the operator's path doesn't hit it | Inconclusive | Skip; re-audit with a different invocation |

A skill passes the audit only if **every Level-1 directive is also Level-2 compliant** under at least one representative invocation.

## Protocol (≤30 min per skill)

### Step 0 — Inventory

List every `→ Load references/<file>.md` directive in SKILL.md. For each, note:

- File path
- Trigger condition (e.g., "when error X occurs", "before Step 3", "always")
- Expected behavior (e.g., "model reads file before composing voice block")

Save the baseline as `YYYY-MM-DD-jit-audit-<skill>.md` in a private workspace outside this public checkout.

### Step 1 — Pick representative invocations

Identify 1–3 invocations that should hit each directive. Examples for `parallax-white-label-onboard`:

- Onboard with `<URL>` only → should hit the URL extraction step's directives
- Onboard with `<folder>` containing 5 mixed files → should hit folder mode F-1 to F-4 directives
- Onboard with `--status` → should hit operational-mode directives

Each invocation is a separate audit run. Combine results.

### Step 2 — Fresh-session execution

For each invocation:

1. Open a fresh Claude Code session (no carry-over context)
2. Issue the invocation
3. Capture the tool-use transcript — specifically every `Read` call against `skills/<name>/references/`
4. Capture the resulting output (what the skill produced)

The fresh session matters: SKILL.md content is loaded at session start. A long-running session that has already accumulated context may skip loads even when a fresh session would honor them.

### Step 3 — Score

Per directive, three checks:

1. **Trigger fired?** Did the invocation hit the directive's trigger condition?
2. **Load fired?** If trigger fired, did the model issue a `Read` against the referenced file?
3. **Content used?** If load fired, does the output show evidence of the loaded content (e.g., specific framework citation, validation table values, error-handling phrasing)?

Score:

- 3/3 → directive is compliant
- 2/3 (load but no use) → directive is loading but model is paraphrasing — strengthen the prompt to require citation
- 1/3 (trigger but no load) → **directive is being skipped** — either strengthen wording, move content inline, or accept the degradation and document it

### Step 4 — Verdict and remediation

For each non-compliant directive, choose one:

| Remediation | When to pick |
|---|---|
| Strengthen the directive wording | Trigger phrasing is ambiguous; add explicit "MUST load" or move directive earlier in SKILL.md |
| Move content inline | Directive is correctly worded but model skips loads in practice; the content is too important to risk |
| Accept the degradation | Content is genuinely optional reference material; document in the audit report |
| Add a hook | The compliance failure is structural; runtime hook (not skill prose) is the leverage move |

Record the verdict in the audit baseline file.

## Strengthening directives

If a directive is being skipped, common fixes ordered by leverage:

1. **Move it earlier** — directives in the top-half of SKILL.md fire more reliably than directives near the bottom.
2. **Add an imperative verb** — `Load references/X.md before Step 3` is stronger than `See references/X.md for details`.
3. **Cite specific content** — `Load references/X.md; the extraction table at the top of that file is required input to Step 3` gives the model a payoff signal.
4. **Add to gotchas** — directives in the frontmatter `gotchas` block fire more reliably than directives in step body text.
5. **Make it a hook** — when prose fails, a runtime hook that auto-injects the reference content removes the compliance question entirely.

## Audit report format

Use the same private baseline file for the completed report. Structure:

```markdown
# JIT-Load Audit — <skill>

Date: YYYY-MM-DD
Skill: skills/<name>/SKILL.md (commit <sha>)
Auditor: <name or session-id>

## Inventory
| Directive | Path | Trigger | Expected behavior |
|---|---|---|---|
| ... | references/... | when ... | model reads ... |

## Invocations
1. `<command>` — covers directives [N, M]
2. `<command>` — covers directives [P, Q]

## Results
| Directive | Trigger fired | Load fired | Content used | Verdict |
|---|---|---|---|---|
| ... | yes | yes | yes | Pass |
| ... | yes | no  | -   | Fail — skipped |
| ... | no  | -   | -   | Inconclusive |

## Remediation actions
- [ ] Strengthen directive in SKILL.md line N: ...
- [ ] Move references/X.md content back inline (Step Y)
- [ ] Add hook for Z compliance gate

## Verdict
PASS | FAIL | PARTIAL — <one-sentence summary>
```

## Limitations

This audit is not exhaustive:

- Single-invocation sampling may miss directives that fire only on rare error paths
- Model behavior is non-deterministic across runs; one PASS doesn't prove future invocations will also load
- Level 2 (behavioral compliance) requires inspecting a fresh-session tool-use transcript — straightforward on Claude Code and on Codex CLI's own call log (`parallax-conventions.md` §14.2); it may be unavailable on claude.ai's uploaded-skill runtime. Where it is unavailable, run Level 1 only and record the gap in the audit baseline.

For high-stakes restructures (skills that affect compliance, money, or client-facing output), run the audit at least three times across different operators and session states. Cross-validate.
