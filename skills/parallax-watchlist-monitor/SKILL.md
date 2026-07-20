---
name: parallax-watchlist-monitor
description: "Monitor a watchlist of tickers: flag score changes, news alerts, technical shifts, and analyst updates via Parallax MCP tools. Provide list of symbols. NOT for single stock analysis (use /parallax-deep-dive), not for portfolio diagnostics (use /parallax-morning-brief)."
---

<!-- white-label: integration-pattern.md -->

# Watchlist Monitor

## When not to use

- Single stock deep dive → use /parallax-deep-dive
- Portfolio with weights → use /parallax-morning-brief or /parallax-client-review
- Weighted client books ranked by who to call → use /parallax-desk-call-list
- Building a portfolio → use /parallax-portfolio-builder

## Gotchas

- JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, fallback patterns, and the §0.2 integer-param serialization caveat
- This is a surveillance skill — optimized for breadth over depth
- get_score_analysis with 4-8 weeks is sufficient for detecting recent changes — fire all in parallel. `weeks` is non-default here and must be passed as a typed integer at the call site (see conventions §0.2)
- Only call get_news_synthesis for names with significant score changes (saves API calls)
- Rank output by magnitude of change — most-changed at top
- Cost: ~54 tokens at 10 symbols (see `_parallax/token-costs.md`): 1/symbol score scan + ~11 per flagged name (news 5 + technicals 5 + outlook 1)
- Coverage: listed equities and ETFs only; fund/OEIC symbols surface the conventions §1 not-covered fallback, not a raw error
- JIT-load `_parallax/white-label/integration-pattern.md` before the Pre-Render step. Loader call is `load_visual_branding()` (7-key visual subset; voice structurally excluded — `branding["voice"]` raises `KeyError`). Apply §5 (Branding Header) and §7 (About This Report) in Output Format.

Surveillance scan across a list of tickers — flag what's changed, what needs attention.

## Usage

```
/parallax-watchlist-monitor AAPL.O MSFT.O GOOGL.O AMZN.O META.O NVDA.O TSLA.O
/parallax-watchlist-monitor AAPL.O JPM.N XOM.N JNJ.N weeks=8
```

## Workflow

Call `ToolSearch` with query `"+Parallax"` to load the deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call. Execute using `mcp__claude_ai_Parallax__*` tools:

1. **Score Scan** — For each symbol, call `get_score_analysis` with `weeks` as int N, where N is the user-supplied value from the invocation (e.g., `weeks=8`) or 8 if none provided. This is non-default (server default is 52) — see conventions §0.2 for the serialization caveat. Compute change in total score over the period.
2. **Flag Movers** — Identify symbols with significant score changes (>1 point total score change or any factor moving >2 points).
3. **Flagged Drill-Down (single parallel batch)** — For flagged symbols only, fire in ONE batch (conventions §3): `get_news_synthesis` (catalysts), `get_technical_analysis` (trend changes), and `get_stock_outlook` with `aspect="recommendations"` (consensus shifts). News and technicals are async (30-90s) — never phase them serially; if any call times out, apply the Degraded-state rule (§4 no-retry) rather than re-waiting.

## Output Format

- **Watchlist Summary** (table: all symbols, current total score, score change, alert flag)
- **Verdict sensitivity** (one line, per `parallax-conventions.md` §11 by reference): the 1-2 symbols nearest the alert boundary (the >1-point total / >2-point single-factor cutoffs in Workflow step 2) and the arithmetic that would flip Alert ↔ Stable.
- **Alerts** (ranked by magnitude of change):
  - **Symbol** — score change, which factors moved, brief catalyst
- **Stable Names** (one-liner each — "no material changes")
- **Recommended Actions** (which names warrant a deeper look via /parallax-deep-dive)
- **About This Report** (always present, even when branding is default):
  - Use a real markdown heading: `## About This Report`
  - First line inside the section: `Branding: default Parallax`
  - Unconditional second line, per integration-pattern.md §7: `Currency: figures as reported by source data; no base-currency conversion applied.`
  - If a logo was skipped under white-label, add `Logo on file: <basename>`

Keep it scannable. Lead with what changed.

## Output additions

- **Branding Header** (only if `white_label_active` AND `client_name != ""`) — single line at the very top: `**<client_name>** watchlist scan`. Logo handling per integration-pattern.md §5.
- **About This Report** (always present): render a `## About This Report` section with the branding-state line above. Place it before the AI disclosure/disclaimer footer. If a logo was skipped, include `Logo on file: <basename>` as a second line.

### Pre-Render — Load white-label branding

Load `_parallax/white-label/integration-pattern.md` §2 and compute `white_label_active` + `client_name` per that section. Apply §5 (Branding Header) and §7 (About This Report) when composing the Output Format.

### Render — deterministic gate (LAST step, mandatory)

Compose the complete report per **Output Format** above (including the disclosure and disclaimer below), then run it through the shared render gate in **one Bash step** before replying. Use a private `mktemp` file (never a fixed/predictable path — `/tmp` symlink hazard). The shared gate is `_parallax/render_gate.py`, a sibling of the directory you loaded this SKILL.md from; pass this skill's key (use the loaded directory's absolute path as `<skill-dir>`):

```
DRAFT="$(mktemp "${TMPDIR:-/tmp}/watchlist.XXXXXX")"
cat > "$DRAFT" <<'REPORT'
<your complete drafted report goes here>
REPORT
python3 "<skill-dir>/../_parallax/render_gate.py" --skill watchlist-monitor < "$DRAFT"; rm -f "$DRAFT"
```

**Your entire final message is exactly that command's stdout** — nothing before it (no step/batch-completion notes, no scratch computation, no "no active house view" / white-label config-probe narration), nothing after it.

**Degraded-state rule:** if an async tool (e.g. `get_assessment`, `get_news_synthesis`) times out or returns no data, render the pending/unavailable note INSIDE the relevant section or the About This Report line — NOT as a preamble above the report — so it is part of the rendered body and survives the gate. (The gate also hoists a leaked degraded note as a backstop.)

`_parallax/render_gate.py` is pure-stdlib and deterministically drops anything before the first rendered block (House View Preamble banner / Branding Header / Ground-truth Integrity / this skill's title or first rendered section), preserving the active-house-view banner in every `view_status` state. Same operator-agnostic-helper pattern as `view_status.py` / `loader.py` (a real Bash tool call, not prose).

**AI-interaction disclosure (required regardless of view state):** Render `parallax-conventions.md §9.2` immediately above the disclaimer below.

Render the standard disclaimer verbatim from `parallax-conventions.md` §9.1.
