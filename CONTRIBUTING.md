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
2. **Run the tests.** From the repo root, the full skill/eval suite — exactly what
   the no-mistakes gate runs — is one command:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r skills/_parallax/house-view/requirements.txt \
               -r skills/_parallax/white-label/requirements.txt \
               -r skills/_parallax/client-policy/requirements.txt \
               -r skills/_parallax/white-label/requirements-test.txt \
               pytest pillow
   bash skills/_parallax/scripts/run-gate-tests.sh   # all roots, ~1,600 tests
   ```
   It runs one `pytest` process per top-level test root, because three skills ship
   a `tests/conftest.py` that collide in a single invocation. The run is offline by
   default and deselects the external DESIGN.md linter smoke under the legacy
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

This repo is public. Branches, commit messages and PR descriptions are public the
moment they are pushed or opened, and cannot be recalled. No client, partner or
fund name may appear in any of them, in any spelling.

- **Build client-first work outside this repo.** A feature built for one client
  lives in the private client-work repo until it is generalised. Real client
  material (brand guides, letters, decks, logos, URLs) never becomes a fixture
  here; fixtures are synthetic (`Acme`, `Example Fund`).
- **Promote by copying, then scanning.** Before copying generalised files in, run
  `python3 skills/_parallax/scripts/client_guard.py scan-path <dir>` on them.
- **Install the blocking hook once per clone:**
  `bash skills/_parallax/scripts/install_git_hooks.sh`. Its pre-push layer runs
  `client_guard.py` over every commit being pushed (file contents and paths,
  messages, the branch name) and refuses the push on a hit. The guard needs the
  client-guard key in `~/.config/parallax/client-guard.key` or `CLIENT_GUARD_KEY`;
  ask the maintainer. Without the key it blocks. Commits already on
  `origin/main` are skipped only when the push goes straight to `origin` and
  the hook could refresh `origin/main`; otherwise it scans the whole branch.
  A push to any other remote with no client guard available is blocked.
- **CI runs the same scan** on every PR (including its title and body) and every
  branch and tag push, using the guard and registry from the PR base or `main`,
  not from the change under test. It is a required check, so a hit cannot merge.
  Changes to `.github/workflows/` need a careful review: the workflow file is
  the one part a PR can still change for itself.
- **Registering a new client** is a maintainer step:
  `python3 skills/_parallax/scripts/client_guard.py add` with one name per line
  on stdin, then commit `.client-guard/registry.json`. Register every form the
  client is written in: legal name, short name, brand, domain. A long registered
  form does not match a shorter one. The registry holds keyed hashes only.
  Register the names before the first commit of any work for that client.
- **Files the guard cannot read are blocked**: PDFs, legacy Office files,
  images, fonts, compressed or nested archives, Git LFS pointers, any binary.
  After reviewing such a file, a key holder runs
  `python3 skills/_parallax/scripts/client_guard.py allow <path>` and commits
  `.client-guard/allow-binary.txt`. Each entry is bound to that exact content.
- Maintainer-only notes (`DECISIONS.md`, `LEARNINGS.md`, `LESSONS.md`,
  `PLANS.md`, handoff notes, `notes/`, `docs/plans/`, `docs/analysis/`) and any
  `clients/` or `client-work/` directory are refused by path, with or without the
  key.

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
