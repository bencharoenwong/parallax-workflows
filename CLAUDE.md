# Parallax Workflows — Project Context

**Project Type:** MCP
**Security Gate:** required

This repo contains Claude Code skills for Parallax equity research. Each skill in `skills/` orchestrates Parallax MCP tools via structured workflows.

> The `**Project Type:**` and `**Security Gate:**` markers above are consumed by `~/.claude/hooks/pre-push`. They override the file-signature classifier (which would otherwise mis-classify this repo as academic because `notes/HANDOFF.md` is present). MCP scope = all 12 SEC-XX items evaluated by `security-auditor`.

## ⚠️ THIS IS A PUBLIC REPOSITORY

`github.com/bencharoenwong/parallax-workflows` is **public**. Nothing here — in tracked **files OR commit messages** — may leak proprietary or sensitive material. Before committing anything, confirm it contains none of:

- **Proprietary methodology internals** — scoring/ensemble composition, regional routing, non-public parameter bounds, valuation-integration details, or named internal frameworks.
- **Internal data-source / schema names** — database, warehouse, or table identifiers; internal service names. (Public Parallax MCP tool names like `get_peer_snapshot` are fine — only internal stores are sensitive.)
- **Firm-specific / client-specific material** — hedge-fund operations, client names, white-label partners. (The "Parallax" product name itself is public.)
- **Artifacts from the private development repo** — eval-harness metrics and findings, research results, internal security-audit detail, planning/decision/handoff notes. These live ONLY in the separate **private** repo and must be sanitized out before any change is ported here.

**Commit messages are public too.** Keep them functional (describe what the code does, e.g. a security fix). Do not describe what was scrubbed, redacted, or held back — naming the redaction is itself the leak. Development happens in the private repo; only sanitized, self-contained changes land here.

**Security-audit docs are public too — describe checks generically.** Files under `docs/security/` are tracked and public. When an audit records a canary or grep check, describe the canary set generically (e.g. "internal warehouse/schema identifiers, partner names, framework code-names") — NEVER reproduce the literal terms, even inside a "found none" evidence line: naming a term to prove its absence still publishes it. Before committing any audit artifact, grep it for the canary set. The `security-auditor` agent must follow this too.

## For Claude Code

When a user invokes `/parallax-<workflow>`, read the corresponding `skills/parallax-<workflow>/SKILL.md` (directory name matches the skill name) and follow it exactly. All skills share conventions in `skills/_parallax/parallax-conventions.md`.

## Conventions

- Symbols use RIC format (AAPL.O, JPM.N). `/parallax-should-i-buy` auto-resolves plain tickers.
- Independent MCP tool calls should fire in parallel (batch pattern in conventions).
- Cross-validate company names after `get_score_analysis` — the scoring tool may map to the wrong company.
- Handle tool failures gracefully — mark sections as "unavailable" rather than erroring out.

## Structure

```
skills/
├── _parallax/                   # Shared: conventions, token costs, AI profile framework
├── parallax-should-i-buy/       # Quick stock eval (accepts plain tickers)
├── parallax-deep-dive/          # Full analysis + AI assessment
├── parallax-due-diligence/      # Financials + Palepu + Parallax research report
├── parallax-client-review/      # RM meeting prep with talk tracks
├── parallax-portfolio-checkup/  # Individual investor health check
├── parallax-morning-brief/      # Fund manager daily brief
├── parallax-ai-buffett/         # Buffett-style factor profile
├── parallax-ai-consensus/       # Multi-profile meta-skill
└── ... (16 more)
```

`plugin/` and `.claude-plugin/marketplace.json` are the **generated** Claude Code plugin bundle — never hand-edit them. Edit the sources under `skills/` and rerun `python3 skills/_parallax/scripts/build_bundle.py plugin` (a gate test fails when the tracked bundle is stale). See the `build_bundle.py` docstring for the build gates.

## Prerequisites

The Parallax MCP server must be connected as `claude_ai_Parallax`. If tools return "not found", the server is not configured.

## Gated push (no-mistakes)

This repo is initialized with the `no-mistakes` gate. Push branches via:

```
git push no-mistakes <branch> -o no-mistakes.skip=ci
```

The `-o no-mistakes.skip=ci` flag is required for this repo — there is no `.github/workflows/`, so the `ci` step would otherwise idle for 4h waiting for checks that never register.

The gate runs review / test / document / lint in an isolated worktree, forwards to `origin`, and opens a PR. The `document` step has auto-fix enabled and may add a commit; everything else reports findings only.

Attach to an active run with `no-mistakes` (TUI). Bypass with `git push origin <branch>` only when intentional, and state the reason in the same response. See global CLAUDE.md §"Gated push via no-mistakes" for the full convention, the safety rule on hooks not firing inside the gate, and the data-perimeter constraint on `no-mistakes init`.
