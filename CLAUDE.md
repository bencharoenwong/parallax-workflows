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
├── _parallax/           # Shared: conventions, token costs
├── should-i-buy/        # Quick stock eval (accepts plain tickers)
├── deep-dive/           # Full analysis + AI assessment
├── due-diligence/       # Financials + Palepu + CG report
├── client-review/       # RM meeting prep with talk tracks
├── portfolio-checkup/   # Individual investor health check
├── morning-brief/       # Fund manager daily brief
└── ... (12 more)
```

## Prerequisites

The Parallax MCP server must be connected as `claude_ai_Parallax`. If tools return "not found", the server is not configured.
