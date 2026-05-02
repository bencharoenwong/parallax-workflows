---
name: parallax-pair-finder
description: "Long/short equity pair builder: given one leg, suggest top-3 counter-leg candidates from peers; given both legs, report residual factor / sector / macro / dollar / beta exposure. Symbols in RIC format. NOT for single-stock analysis (use /parallax-deep-dive), not for peer comparison tables (use /parallax-peer-comparison), not for portfolio analysis (use /parallax-morning-brief)."
negative-triggers:
  - Single stock deep dive → use /parallax-deep-dive
  - Generic peer table only → use /parallax-peer-comparison
  - Multi-position portfolio analysis → use /parallax-morning-brief
  - Long-only stock screening → use /parallax-thematic-screen
gotchas:
  - JIT-load _parallax/parallax-conventions.md for RIC resolution, parallel execution, and fallback patterns
  - JIT-load references/residual-math.md for factor-net, beta, and hedge-ratio formulas
  - "Default selection criterion (mode B): closest peer with worst total score for short candidates; closest peer with best total score for long candidates"
  - Suggestion mode (one leg given) uses single export_peer_comparison call to guarantee cross-sectionally comparable factor scores across all candidates
  - Evaluate mode (both legs given) MUST flag score-comparability uncertainty when short_ric is NOT in long's peer set (cross-sector pair)
  - "v1 scope cuts: no revenue-geography mix (use domicile/listing-currency only), no share counts (dollar/beta-neutral ratios only), no cross-sector suggestions (within-sector peers only). Evaluate mode accepts cross-sector pairs but flags them."
  - "Liquidity disclaimer is MANDATORY in every output: ADV / borrow / float not validated by Parallax — verify externally before sizing."
---

# Pair Finder

Long/short equity pair construction for fundamental PMs. Given one leg of a thesis, suggest the other leg from peers and report what residual exposure survives the hedge. Given both legs, report the residual.

## Usage

Three invocation modes:

```bash
# Mode 1 — Find short candidate for a long thesis
/parallax-pair-finder NVDA.O long
/parallax-pair-finder NVDA.O long --candidates=3 --with-history

# Mode 2 — Find long candidate for a short thesis
/parallax-pair-finder INTC.O short

# Mode 3 — Evaluate a pair the PM already has
/parallax-pair-finder long=NVDA.O short=AMD.O
/parallax-pair-finder long=NVDA.O short=AMD.O --with-history
```

**Flags:**
- `--candidates=N` (default 3 in suggestion modes; ignored in evaluate mode)
- `--with-history` (adds 60d→180d realized correlation, pair vol, max drawdown, hit rate)

**Default selection criterion (v1):** closest peer with worst total score for short candidates; closest peer with best total score for long candidates. (Same-sector relative-value framing.)

## Workflow

JIT-load `_parallax/parallax-conventions.md` for execution mode, RIC resolution, and fallback patterns. JIT-load `references/residual-math.md` for factor-net, beta, and hedge-ratio formulas. Call `ToolSearch` with query `"+Parallax"` to load deferred MCP tool schemas before the first `mcp__claude_ai_Parallax__*` call.

Detect mode from invocation:
- `<symbol> long` → Mode 1 (find short candidate)
- `<symbol> short` → Mode 2 (find long candidate)
- `long=<symbol> short=<symbol>` → Mode 3 (evaluate pair)
- Anything else → ask the user to clarify which mode.

(Mode-specific workflows in subsequent tasks.)
