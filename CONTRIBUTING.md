# Contributing

Thanks for the interest. A few notes on what fits and what doesn't.

## What we accept

- **Bug reports.** Open an issue with: command run, expected output, actual output, and the relevant `SKILL.md` filename if you're touching a specific workflow.
- **Documentation fixes.** Typos, broken links, unclear instructions — PRs welcome.
- **New sample CIO views** for `skills/parallax-load-house-view/samples/`. We use these in regression coverage; the more variety, the better.
- **Test coverage** for the Python modules under `skills/_parallax/house-view/`. New tests should go in the adjacent `tests/` directory and follow the existing fixture conventions.
- **Workflow forks.** If you've built a useful variant of one of the skills (different output format, different tool sequence, different audience), open an issue describing it. We may add a pointer in the README.

## What we don't accept

- **New core workflows.** The set of `/parallax-*` skills is curated against the Parallax product roadmap. If you want a new workflow, fork the repo and ship it under your own naming. We're happy to link it.
- **Changes to the scoring methodology.** The Parallax scoring engine is not open-source; PRs that try to adjust factor weights, multipliers, or score interpretation in the loader will be closed. The schema and loader are intentionally scoring-engine-agnostic so you can swap the backend, but the multiplier mapping in `loader.md` is part of the Parallax contract.
- **Hash-chain or audit-trail changes** without a prior issue and a security review. The audit chain is load-bearing for compliance use cases. Any change here needs a clear failure mode discussion before code lands.
- **Scope expansion of `gap_detect` / `gap_suggest`** beyond the current eligible dimensions (`macro_regime`, `factors`, `regions`, `sectors`). Pillars are encoding-only; themes/styles/excludes are CIO judgment, not data-fillable. This is enforced at planner level with hard assertions.

## Before opening a PR

1. **Check `CHANGELOG.md` and open issues.** A quick search for the area you're touching will surface prior work. If your PR reverses a shipped behavior, explain why.
2. **Run the tests.** Set `PARALLAX_ROOT` to your checkout's absolute path.
   Run repository-relative commands below from that root:

   ```bash
   cd "$PARALLAX_ROOT"
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r skills/_parallax/house-view/requirements.txt \
               -r skills/_parallax/white-label/requirements.txt \
               -r skills/_parallax/client-policy/requirements.txt \
               -r skills/_parallax/white-label/requirements-test.txt \
               pytest pillow
   bash skills/_parallax/scripts/run-gate-tests.sh
   ```
   The runner discovers test roots and runs each in a separate `pytest` process.
   This prevents colliding `conftest.py` registrations. Use `--list-roots` to
   inspect current roots. The run is offline by default and deselects the external DESIGN.md linter smoke under the legacy
   `npx` marker. The validator requires a separately installed executable and
   checksum; it does not download dependencies. `PARALLAX_GATE_MODE=network`
   opts that integration back in for an explicitly authorized run. While iterating you
   can run just one area, e.g. `pytest skills/_parallax/house-view/tests/` or
   `cd evals && python3 -m pytest graders -q`.
3. **For SKILL.md changes**, verify the workflow runs end-to-end in a fresh Claude Code session. The runtime caches SKILL.md content at session start, so unit-style tests don't catch SKILL.md regressions.
   If a gated skill renames its title or first rendered section, update its
   `SKILL_ANCHORS` entry and `test_render_gate.py` start example in the same
   change. The render-gate tests enforce the documented label, anchor, and
   SKILL.md command wiring on every gate run.
4. **If your change touches a skill or shared file in the plugin's general-release set**, rebuild the bundle (`python3 skills/_parallax/scripts/build_bundle.py plugin`) and commit the regenerated `plugin/` alongside your source edit — a gate test fails when the tracked bundle drifts from the sources. Never edit `plugin/` by hand.
5. **Keep the diff focused.** One concern per PR. Refactors that bundle multiple unrelated changes get bounced.

## Client names and client-first work

This is the authoritative operational guide for the client-name guard. Every
public file, path, commit message, branch, tag, PR and comment must exclude
client, partner and fund names, in every spelling. Public material can persist
in history after deletion. Keep proprietary methods, internal identifiers and
private development artifacts outside this repository too.

### Promotion and registration

Build client-first work in the private client-work repository. Use synthetic
fixtures here; real brand guides, letters, logos, URLs and client materials stay
private. Register every written form before the first client-work commit:
legal name, short name, brand and domain. A long form does not cover a short one.

A key holder runs `python3 skills/_parallax/scripts/client_guard.py add`, with
one name per stdin line, then includes `.client-guard/registry.json` in the next
authorized commit. The registry holds keyed hashes only. The command checks
HEAD, unpublished history, staged paths and contents, and tracked or untracked
working files before writing. Without `origin/main`, it checks all reachable
history. Remove new-name occurrences and retry a refused registration. Its
locations print locally, including matching paths; keep that output private.

Before promotion, run
`python3 skills/_parallax/scripts/client_guard.py scan-path <directory>` on the
generalised files. Copy with `cp -L` or `rsync -L` so the promoted files contain
the reviewed bytes. A plain copy can preserve a symlink instead of its target.

Unreadable or unsupported content fails the guard. This includes PDFs, legacy
Office files, images, fonts, nested archives, Git LFS pointers and other binaries.
After reviewing exact bytes, a key holder can run
`python3 skills/_parallax/scripts/client_guard.py allow <path>` and include
`.client-guard/allow-binary.txt` in the next authorized commit. Allowlist entries
cover that exact content only. Maintainer notes and client-work directories are
refused by path, including member paths inside supported archives, regardless
of the key. See the script for the complete path rules.

The CI scanner merges trusted and proposed registries and refuses registry
removals that the change makes since its fork point from `main`. To correct a
mistaken registration, a key holder must review the removal locally and obtain
owner approval for an admin bypass where required.

### Local push checks

Install or refresh the hook in each clone:
`bash skills/_parallax/scripts/install_git_hooks.sh`. Also run
`python3 skills/_parallax/scripts/scan_commit_messages.py` before every push.
The standalone scanner defaults to `origin/main..HEAD`, then `main..HEAD`, and
fails when neither base exists. It prints commit identifiers and categories,
never matched message text. CI does not run this message-vocabulary scanner.

The hook checks the refs Git actually pushes, including each outgoing commit,
its changed files, messages and identities, tags and ref names. Deletion-only
pushes publish no new objects. It prefers the client guard from `origin/main`
and merges that revision's registry with the checkout's registry. A missing or
wrong key, unreadable content, or scanner failure blocks the guarded push.
Keep the key in `~/.config/parallax/client-guard.key` or `CLIENT_GUARD_KEY`;
obtain it from the maintainer and keep it outside the repository.

The hook refreshes `origin/main` with transport timeouts. It excludes already
published default-branch commits only when that fetch succeeds and the push URL
matches origin's fetch URL. A different `pushurl`, another remote, or the
`no-mistakes` remote gets no default-branch exclusion. New branches scan their
whole history before any permitted exclusion. A failed fetch warns and drops
the exclusion; the cached guard may also lack recent registrations.

The layer sets `GIT_NO_REPLACE_OBJECTS=1` for its Git reads and restores the
caller's value afterward. It preserves stdin for subsequent hook layers.
The installer prepends its layer, backs up modified hooks, and refreshes old
versions. It refuses symlinked or non-shell hooks, incomplete layer markers,
and hooks outside the clone. `PARALLAX_HOOKS_FORCE=1` overrides only the
outside-clone refusal. It does not repair symlinks, non-shell hooks or broken markers.

Coverage limits matter. A missing message scanner blocks when `origin/main`
ships it; legacy clones without either copy only warn. A push to another remote
without any client guard blocks. Legacy pushes to origin without a guard warn.
The message scanner runs from the checkout, so edits to its rules need review.
A commit added inside the `no-mistakes` gate bypasses this clone's hook. Review
the gate's final diff and commit messages before merge. Hooks can be bypassed;
they do not replace maintainer review or server-side protection.
The repository gate configuration disables the generated Intent section of PR
descriptions. To also withhold intent from PR drafting, pass
`--no-publish-intent` when starting the run. Installed gate versions may still
append raw validation transcripts. For a public-safe description, start the run
with `--skip=pr,ci`, complete the gated push, then write and scan the public
title and body before opening a concise PR by hand. Check GitHub CI on that PR.
Generated text is not a privacy
filter.

### CI trust and coverage

[client-guard.yml](.github/workflows/client-guard.yml) requires the rollout below
before it provides merge protection. A file in a branch does not establish a
required check. Verify active GitHub rules and workflow runs separately.

The workflow uses `pull_request_target` for PRs targeting `main`. Its workflow
comes from the default branch; PR content is fetched as Git objects and is never
checked out or executed. The guard comes from the trusted base revision. Proposed
registry and allowlist edits are read through `CLIENT_GUARD_CHANGE_REV`.
Supplying that change revision requires `CLIENT_GUARD_TRUSTED_REV` as well;
incomplete trust configuration fails before scanning.

All three conditions must hold before a PR reaches the keyed scan:

1. The head repository equals this repository.
2. The author is not a bot.
3. `author_association` is `OWNER`, `MEMBER` or `COLLABORATOR`.

Every other PR fails with one fixed message before fetching or scanning its
content. This includes same-repository Dependabot PRs, whose bodies can contain
third-party release notes. There is no label, rerun or CI override that admits
untrusted content. A keyed result reveals information about the private registry,
even if output contains only counts or pass/fail status.

Trusted PR scans cover title, body, branch name, commits and the full head tree.
Push runs cover `main`. Issue and comment runs require the text's own author to
pass the same non-bot association rule. A comment run scans only that comment,
never the issue or PR text it belongs to. These associations imply push access
for this personal-account repository. Revisit trust checks before moving to an
organization, where read and triage roles differ.

CI excludes review text, review comments, release text, other branch pushes and
tag pushes. Local hooks cover Git pushes; review other public text separately.
The PR that first installs the workflow has no `pull_request_target` guard run.
A `[skip ci]` message can skip a push run; it does not skip the PR guard run.
A reported location containing a registered name is withheld in CI. Keep local
scan output private even when CI would withhold it.

### Reviewing an untrusted PR

A maintainer reviews outside-fork and bot PRs locally. Run commands from
`PARALLAX_ROOT`; replace the placeholders with the reviewed PR number and SHAs.

1. Refresh the trusted base: `git fetch origin main`.
2. Fetch the candidate: `git fetch origin refs/pull/<N>/head:pr-<N>`.
   Record its exact head SHA. Read its content without executing it.
3. Use the trusted base's guard and registry to run
   `client_guard.py scan-range <head-sha> ^origin/main` and
   `client_guard.py scan-tree <head-sha>`. Check messages and author identities too.
   Never run the PR's edited guard to judge that same PR.
4. Scan the PR title, body and head branch name with the trusted
   `client_guard.py scan-text --label <field>`. For example, read a field with
   `gh pr view <N> --json title -q .title` and pipe it into the trusted scanner.
   Repeat for `body` and `headRefName`.
5. Keep all guard output private. Do not quote, repost or reference the untrusted
   text in another public item; that republishes the content under review.
6. After every scan passes and the owner authorizes merge, use:
   `gh pr merge <N> --admin --squash --match-head-commit <head-sha> --subject "<maintainer-written>" --body ""`.
   The subject and empty body prevent copying untrusted text into the merge
   message. The head check prevents merging later, unscanned commits.

The untrusted PR's guard check stays red by design once the workflow is active.
An admin bypass is needed when branch protection requires that check. Never
reinterpret a red result as permission to merge without the local review.
The merge decision itself reveals that the reviewed content passed.

### Maintainer checklist before merging `client-guard.yml`

Green tests alone do not complete rollout. Owner authorization remains required
for commits, pushes, merges and publication. Recheck these settings before
merging the initial workflow or a later workflow change:

1. Create the `client-guard` environment with a deployment branch policy allowing
   only `main`. Verify the environment and its branch policy through the API.
2. Put `CLIENT_GUARD_KEY` in that environment. Verify the secret's presence
   through the API without printing its value.
3. Protect workflow edits through a ruleset requiring this workflow by file path,
   or an enforced code-owner review rule covering `.github/workflows/` and
   `.github/CODEOWNERS`. A CODEOWNERS file alone provides no enforcement.
   A required status check keyed only by job name can be satisfied by another
   job with that name. Verify PR review requirements separately from required
   status checks; requiring PR review does not require the guard check to pass.
4. After verifying the environment policy and secret, delete any repository-level
   copy of `CLIENT_GUARD_KEY`. Complete this before merge; a leftover copy is
   available to other branch workflows and defeats environment scoping.
5. Merge only after authorized local review. Older workflows may fail closed
   between secret migration and merge. After merge, verify the new workflow
   succeeds on `main`; keep the repository-level secret absent throughout.
6. Verify the intended required checks or required workflow in the active ruleset.
   Confirm a real PR attaches the guard result to the revision being judged.
   Until those checks succeed, treat automated merge protection as unverified.

## Style

- **Python:** type hints on function signatures, docstrings on public APIs, `pytest` for tests. Pure functions where possible. Modules under `_parallax/house-view/` that perform I/O by design: `audit_chain` (append-only log), `audit_export` (tarball), `chain_emit` (chain YAML write), `chain_prune` (file deletion CLI), `manifest_cache` (cache read/write). Everything else (`gap_detect`, `gap_suggest`, `manifest_verify`) is pure — keep it that way.
- **Markdown:** standard CommonMark. Tables for reference material, prose for explanation. Code blocks tagged with the language.
- **Commit messages:** `<type>(<scope>): <subject>`. Types: `feat`, `fix`, `docs`, `test`, `chore`. Examples in `git log`.

## Reference templates

Read `skills/_parallax/skill-structure-conventions.md` first — it defines the step spine, the host-portability rule (name host primitives from `parallax-conventions.md` §14, never host tools), the authority header for shared files, and the two closing sections (`## Failure modes`, `## Done when`) that are the target for every orchestrator — forward-only, with the two orchestrators below (`parallax-credit-lens`, `parallax-load-house-view`) migrated first in the structure sweep. Then mirror the structure of one of the newer reference units:
- `skills/parallax-credit-lens/` — typed dataclasses (`AltmanInputs`, `CreditReport`, `Flag`, `MetricRow`), pure scoring functions, comprehensive test classes (`TestReportBuilders`, `TestEdgeCases`, `TestAbsoluteFlagging`).
- `skills/parallax-load-house-view/` — multi-stage workflow with schema, validation, audit chain, and signed reasoning chains. Use as the reference for any skill that needs persistence + audit guarantees.
- `skills/_parallax/white-label/` — extraction + validation pattern, modular tests under `tests/`. When wiring a new visual-rendering consumer skill, JIT-load `_parallax/white-label/integration-pattern.md` (the canonical §1–§9 consumer-side contract) via the `<!-- white-label: integration-pattern.md -->` sentinel; the drift gate at `tests/test_integration_pattern_referenced.py` enforces the sentinel ↔ load-directive pairing and will fail the build on silent drift.

Older skills (`parallax-deep-dive`, `parallax-peer-comparison`, `parallax-due-diligence`, `parallax-should-i-buy`) predate this discipline and remain SKILL.md-only — that is fine for prompt-orchestration skills with no Python plumbing. **Don't refactor them mechanically just to match.** Upgrade only when a real reason to touch them surfaces (a bug, a new feature, observed user friction).

## License

By contributing, you agree your contributions are licensed under the same MIT license as the rest of the repository. See `LICENSE`.

## Contact

Issues and PRs are the preferred channel. For commercial questions about the Parallax MCP server itself (data feeds, scoring methodology, enterprise licensing), email Chicago Global at the address listed on [chicago.global](https://chicago.global).
