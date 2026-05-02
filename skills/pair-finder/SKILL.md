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

(Workflow body to follow in subsequent tasks.)
