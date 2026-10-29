# Parallax Workflows — Project Context

**Project Type:** MCP
**Security Gate:** required

This repository contains Parallax equity-research skills. The markers above
select MCP review scope: all 12 SEC-XX items in the security audit.
Read [CONTRIBUTING.md](CONTRIBUTING.md) before modifying the repository.

## Public repository boundaries

This repository is public. Keep these categories out of files, paths, commit
messages, branches, PR text and every other public surface:

- Proprietary methods, including scoring composition, routing, private parameter
  bounds, valuation integration and internal frameworks.
- Internal database, schema, table and service identifiers. Public MCP tool names
  are permitted.
- Client, partner and fund names, in every spelling, and firm-specific operations.
  The public Parallax product name is permitted.
- Private development artifacts, including research results, evaluation findings,
  internal audit detail, planning notes and handoffs.

Develop private work in the separate private repository. Promote only reviewed,
generalised, self-contained changes. Write functional commit messages describing
behavior. Never name material removed or withheld; that description also publishes it.

Register every client form before its first client-work commit. Scan generalised
files before promotion. Follow the authoritative
[client-name guide](CONTRIBUTING.md#client-names-and-client-first-work) for
registration, promotion, hooks, CI trust, manual review and rollout.

Before every push, install or refresh the blocking hook with
`bash skills/_parallax/scripts/install_git_hooks.sh` and run
`python3 skills/_parallax/scripts/scan_commit_messages.py` from the repository root.
The hook checks actual pushed refs; the standalone scanner defaults to outgoing
commits. Guard-key errors and scan failures block guarded pushes. Read the
[local push checks](CONTRIBUTING.md#local-push-checks) for exclusions, legacy-clone
warnings and installer refusals. Verify repository protection separately; a
workflow file alone establishes no required check.

## Security-audit documents

`docs/security/` is public too. Describe checks by category and location; never
quote restricted terms, including in absence claims. Scan every audit before
committing it. This requirement also applies to security-auditor output.

`docs/security/audit-latest.md` is a symlink. Write a new dated audit first, then
repoint the symlink. Redirecting onto the symlink overwrites its previous target.
After an audit write, status should show one new dated file and a modified symlink.

## Running skills

For `/parallax-<workflow>`, read `skills/parallax-<workflow>/SKILL.md` and follow it.
Shared conventions live in `skills/_parallax/parallax-conventions.md`.

- Use RIC symbols. `parallax-should-i-buy` can resolve plain tickers.
- Batch independent MCP calls as the conventions specify.
- Discover connected tools and use their exact names and schemas.
  Do not require a fixed server alias. Report missing capabilities as
  unavailable; a configured alias does not prove a working connector.
- Cross-check company identity after scoring. The conventions define each field;
  `get_score_analysis` requires checking `data[0].symbol` against the requested RIC.
- Mark failed analysis sections unavailable. Decision gates fail closed to
  `UNVERIFIED`; see conventions §4.0.

## Repository layout and generated files

`skills/` contains workflow sources and shared `_parallax/` helpers. `evals/`
contains evaluation infrastructure. `plugin/` and `.claude-plugin/marketplace.json`
are generated; never edit them directly. Edit sources and rebuild with
`python3 skills/_parallax/scripts/build_bundle.py plugin`. Follow distribution
and release instructions in [AGENTS.md](AGENTS.md) and
[docs/releases.md](docs/releases.md).

## Git and the no-mistakes gate

Commit, push, tag and publish only when the user requests the action. Publishing
also requires explicit owner approval. From the repository root, push branches
through the `no-mistakes` remote when it exists:

```bash
no-mistakes axi run --intent "<task>" --no-publish-intent --skip=pr,ci
```

This validates and pushes through the configured gate without publishing raw
validation transcripts. Write and scan the public PR title and body before
opening the PR, then inspect its GitHub checks. The gate's CI wait is skipped
because this checkout's workflows do not run on feature-branch pushes.

The gate runs review, tests, documentation and lint in an isolated worktree,
and forwards to `origin`. Its documentation step can add a commit
that bypasses this clone's pre-push hook. Review final changes and commit
messages before merging; local scans do not certify gate-added changes.

Attach with `no-mistakes`. Bypass through `origin` only intentionally and explain
why in the same response. Follow the host's Git and data-perimeter rules before
initializing or using an external gate agent.
