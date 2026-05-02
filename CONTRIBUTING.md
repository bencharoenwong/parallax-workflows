# Contributing

Thanks for the interest. A few notes on what fits and what doesn't.

## What we accept

- **Bug reports.** Open an issue with: command run, expected output, actual output, and the relevant `SKILL.md` filename if you're touching a specific workflow.
- **Documentation fixes.** Typos, broken links, unclear instructions — PRs welcome.
- **New sample CIO views** for `skills/load-house-view/samples/`. We use these in regression coverage; the more variety, the better.
- **Test coverage** for the Python modules under `skills/_parallax/house-view/`. New tests should go in the adjacent `tests/` directory and follow the existing fixture conventions.
- **Workflow forks.** If you've built a useful variant of one of the skills (different output format, different tool sequence, different audience), open an issue describing it. We may add a pointer in the README.

## What we don't accept

- **New core workflows.** The set of `/parallax-*` skills is curated against the Parallax product roadmap. If you want a new workflow, fork the repo and ship it under your own naming. We're happy to link it.
- **Changes to the scoring methodology.** The Parallax scoring engine is not open-source; PRs that try to adjust factor weights, multipliers, or score interpretation in the loader will be closed. The schema and loader are intentionally scoring-engine-agnostic so you can swap the backend, but the multiplier mapping in `loader.md` is part of the Parallax contract.
- **Hash-chain or audit-trail changes** without a prior issue and a security review. The audit chain is load-bearing for compliance use cases. Any change here needs a clear failure mode discussion before code lands.
- **Scope expansion of `gap_detect` / `gap_suggest`** beyond the current eligible dimensions (`macro_regime`, `factors`, `regions`, `sectors`). Pillars are encoding-only; themes/styles/excludes are CIO judgment, not data-fillable. This is enforced at planner level with hard assertions.

## Before opening a PR

1. **Check `DECISIONS.md`.** It's a long file, but a quick search for the area you're touching will surface prior reasoning. If your PR contradicts a `[DROP]` entry, explain why.
2. **Run the tests.** Python modules have coverage in `skills/_parallax/house-view/tests/`. From the repo root:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r skills/_parallax/house-view/requirements.txt pytest
   pytest skills/_parallax/house-view/tests/
   ```
3. **For SKILL.md changes**, verify the workflow runs end-to-end in a fresh Claude Code session. The runtime caches SKILL.md content at session start, so unit-style tests don't catch SKILL.md regressions.
4. **Keep the diff focused.** One concern per PR. Refactors that bundle multiple unrelated changes get bounced.

## Style

- **Python:** type hints on function signatures, docstrings on public APIs, `pytest` for tests. Pure functions where possible. Modules under `_parallax/house-view/` that perform I/O by design: `audit_chain` (append-only log), `audit_export` (tarball), `chain_emit` (chain YAML write), `chain_prune` (file deletion CLI), `manifest_cache` (cache read/write). Everything else (`gap_detect`, `gap_suggest`, `manifest_verify`) is pure — keep it that way.
- **Markdown:** standard CommonMark. Tables for reference material, prose for explanation. Code blocks tagged with the language.
- **Commit messages:** `<type>(<scope>): <subject>`. Types: `feat`, `fix`, `docs`, `test`, `chore`. Examples in `git log`.

## Reference templates

When adding or substantially upgrading a skill, mirror the structure of one of the newer skills:
- `skills/credit-lens/` — typed dataclasses (`AltmanInputs`, `CreditReport`, `Flag`, `MetricRow`), pure scoring functions, comprehensive test classes (`TestReportBuilders`, `TestEdgeCases`, `TestAbsoluteFlagging`).
- `skills/load-house-view/` — multi-stage workflow with schema, validation, audit chain, and signed reasoning chains. Use as the reference for any skill that needs persistence + audit guarantees.
- `skills/_parallax/white-label/` — extraction + validation pattern, modular tests under `tests/`.

Older skills (`deep-dive`, `peer-comparison`, `due-diligence`, `should-i-buy`) predate this discipline and remain SKILL.md-only — that is fine for prompt-orchestration skills with no Python plumbing. **Don't refactor them mechanically just to match.** Upgrade only when a real reason to touch them surfaces (a bug, a new feature, observed user friction).

## License

By contributing, you agree your contributions are licensed under the same MIT license as the rest of the repository. See `LICENSE`.

## Contact

Issues and PRs are the preferred channel. For commercial questions about the Parallax MCP server itself (data feeds, scoring methodology, enterprise licensing), email Chicago Global at the address listed on [chicago.global](https://chicago.global).
