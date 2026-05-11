# Parallax Workflows — Project Context

This repo contains Claude Code skills for Parallax equity research. Each skill in `skills/` orchestrates Parallax MCP tools via structured workflows.

## For Claude Code

When a user invokes `/parallax-<workflow>`, read the corresponding `skills/<workflow>/SKILL.md` and follow it exactly. All skills share conventions in `skills/_parallax/parallax-conventions.md`.

## Conventions

- Symbols use RIC format (AAPL.O, JPM.N). `/parallax-should-i-buy` auto-resolves plain tickers.
- Independent MCP tool calls should fire in parallel (batch pattern in conventions).
- Cross-validate company names after `get_score_analysis` — the scoring tool may map to the wrong company.
- Handle tool failures gracefully — mark sections as "unavailable" rather than erroring out.

## Structure

```
skills/
├── _parallax/           # Shared: conventions, token costs, AI profile framework
├── should-i-buy/        # Quick stock eval (accepts plain tickers)
├── deep-dive/           # Full analysis + AI assessment
├── due-diligence/       # Financials + Palepu + Parallax research report
├── client-review/       # RM meeting prep with talk tracks
├── portfolio-checkup/   # Individual investor health check
├── morning-brief/       # Fund manager daily brief
├── AI-buffett/          # Buffett-style factor profile
├── AI-consensus/        # Multi-profile meta-skill
└── ... (16 more)
```

## Prerequisites

The Parallax MCP server must be connected as `claude_ai_Parallax`. If tools return "not found", the server is not configured.

## Gated push (no-mistakes)

This repo is initialized with the `no-mistakes` gate. Push branches via:

```
git push no-mistakes <branch>
```

The gate runs review / test / document / lint in an isolated worktree, forwards to `origin`, and opens a PR. PR #20 was the first one through. The `document` step has auto-fix enabled and may add a commit; everything else reports findings only. CI step idles until timeout because this repo has no `.github/workflows/` — append `-o no-mistakes.skip=ci` to the push command to skip it.

Attach to an active run with `no-mistakes` (TUI). Bypass with `git push origin <branch>` only when intentional and announced. See global CLAUDE.md §"Gated push via no-mistakes" for the full convention.
