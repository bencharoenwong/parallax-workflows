---
profile_id: soros
display_name: Soros-style
status: active
public_anchor:
  type: book
  citation: "Soros, G. (1987). The Alchemy of Finance. Simon & Schuster. ISBN 978-0471445494."
  doi_or_url: "N/A — book source."
  retrieved: 2026-04-07
  notes: "Soros's own published articulation of the reflexivity framework: markets and fundamentals influence each other through feedback loops; regime breaks occur when narrative diverges sharply from underlying conditions and either narrative collapses or fundamentals catch up. Most defensible non-Buffett v1 profile because the investor wrote his own source."
secondary_anchor:
  citation: "Drobny, S. (2006). Inside the House of Money: Top Hedge Fund Traders on Profiting in the Global Markets. John Wiley & Sons."
  doi_or_url: "N/A — book source."
  notes: "Interview-based account of macro traders including Soros's collaborators describing the top-down workflow: regime thesis → exposed industries/geographies → concentrated high-conviction positions."
direction: top_down
asset_class: multi_asset
factor_tilts: {}
factor_tilts_notes: "Soros-style is not characterized by Parallax factor loadings. It is characterized by macro regime identification, telemetry-based theme detection, and dual-channel ticker exposure mapping."
leverage_overlay: null
output_shape: trade_ideas
output_shape_single_ticker: inferred_exposure_verdict
tool_sequence_basket:
  - list_macro_countries
  - macro_analyst:component=tactical
  - get_telemetry
  - build_stock_universe
  - get_peer_snapshot
tool_sequence_single_ticker:
  - list_macro_countries
  - macro_analyst:component=tactical
  - get_telemetry
  - get_company_info
  - get_peer_snapshot
  - build_stock_universe
required_factors_present: []
thresholds:
  markets_analyzed_min: 3
  markets_analyzed_max: 5
  themes_surfaced_min: 1
  themes_surfaced_max: 3
  exposure_channels_for_match: 2
  exposure_channels_for_partial: 1
owner: parallax-workflows
last_legal_review: PENDING
last_anchor_test: 2026-04-07
anchor_test_notes: "Workflow tools verified: list_macro_countries returns 12 covered markets (US, JP, UK, DE, FR, CN, IN, KR, SG, MY, CA, Global) ✓; macro_analyst(United States, tactical) returns substantive bond-overweight/equity-caution thesis dated 2026-03-26 (PCE upgraded to 2.7%, easing cycle narrative dead, Hormuz/Iran as invalidation) ✓; build_stock_universe is async ~15-40s and tends to time out in single-call tests (see Greenblatt anchor test); get_telemetry returned 'Admin org not configured' in this MCP session — Channel B of dual-channel logic unavailable in current environment, graceful fallback per dispatcher kicks in (single-ticker mode retains industry-only observations but final fit is skipped). These historical tool observations are not a fresh-session or production validation; the current dispatcher evidence-state contract governs failures."
---

# Soros-style profile

## What the anchor documents

George Soros's 1987 *The Alchemy of Finance* is his own articulation of reflexivity: markets do not simply reflect fundamentals; prices and fundamentals influence each other through feedback loops. Regime breaks occur when a dominant market narrative diverges sharply from underlying conditions, opening a window where the narrative either collapses or the fundamentals are forced to catch up. Identifying such regime breaks is the core framework. Steven Drobny's 2006 *Inside the House of Money* provides interview-based context describing the top-down workflow used by Soros and his collaborators: macro thesis → identify exposed geographies and industries → concentrate high-conviction positions on the highest-expected-value trades.

## What this profile does

Unlike other v1 profiles, Soros operates top-down in two distinct modes:

**Basket / screening mode (no ticker):** Run `list_macro_countries` → `macro_analyst(tactical)` on 3-5 markets in parallel → `get_telemetry` for cross-market regime divergence signals → identify 1-3 regime themes where macro and telemetry agree on direction → `build_stock_universe` for each theme → rank top names per theme. Output: ranked trade-idea list with regime thesis.

**Single-ticker mode (one ticker):** Run the same macro workflow, then check the input ticker against two related exposure channels:
- **Channel A — Industry exposure (two sub-paths, either sufficient to flag):**
  - **A1 — Sample membership:** does the ticker appear in a valid returned theme sample? Successful checked absence is `NOT_FLAGGED` for that sample only; timeout/missing result is `UNAVAILABLE`, not negative membership.
  - **A2 — Sector/industry classification match:** does the ticker's verified sector/industry from `get_company_info` match a theme's target industry? Missing classification is `UNAVAILABLE`. (Does NOT require the universe build.)
  - Channel A is `FLAGGED` if either evaluable path flags; `NOT_FLAGGED` only when both paths are evaluable and negative; otherwise `UNAVAILABLE`. Report A1/A2 separately. A2 can establish classification exposure, never sample membership.
- **Channel B — Telemetry basket theme:** does the ticker fall into any of the regime baskets surfaced by `get_telemetry`? If telemetry is unavailable (e.g., "Admin org not configured" in current env), Channel B is `UNAVAILABLE` (not `NOT_FLAGGED`).

Fetch the target `get_peer_snapshot` unconditionally in single-ticker mode, independently of universe inclusion, and verify it against `get_company_info.data.name` per conventions. Missing snapshot/identity stops the profile. With both required A/B channels evaluable: both flagged → `match`; one → `partial_match`; neither → `no_match`. Any unavailable required channel gives `skipped`, retaining verified observations. These paths are not independent statistical confirmations.

## What this profile does NOT capture

- **Trade execution.** Soros's actual trades involve specific entry/exit timing, position sizing, and stop-loss logic. Profile identifies themes and ticker exposure; it does not generate trade execution instructions.
- **Currency and rate positions.** Macro traders trade FX and rates alongside equities. Parallax is equity-centric; this profile cites currency/rate context but does not recommend FX or rate trades.
- **Leverage and concentration.** Macro traders run concentrated, leveraged positions. Profile is a signal, not a position-sizing recommendation.
- **Reflexivity loop timing.** Soros's "regime break" call is a timing judgment about when narrative-fundamentals divergence resolves. Profile surfaces current signals but cannot predict the resolution date.
- **Single-stock bottom-up analysis.** Single-ticker mode is explicitly partial. Soros does not care about a single stock's factor profile; he cares whether it rides the right macro wave.

## How to interpret the output

**Basket mode:** A ranked list of trade ideas organized by regime theme. Each idea includes the macro thesis, the directional view, and why the named ticker is exposed. Closest to what macro traders actually produce.

**Single-ticker mode:** Dual-channel verdict. The user learns (1) what regime themes are currently prominent, (2) whether the ticker is industry-exposed (channel A), (3) whether the ticker fits a telemetry basket (channel B), (4) the combined verdict. A `match` means both documented exposure checks flagged; it does not prove causal exposure or independent corroboration. A `partial_match` means one channel flagged it. A `no_match` means both evaluated channels were not flagged; unavailable evidence instead gives `skipped`.

## Anchor test plan

Basket mode: spot-check that surfaced themes match recent macro narratives from Bloomberg / Reuters / FT (qualitative — exact match not expected). Single-ticker mode: pick a sector clearly in a current theme (expect `match` or `partial`), pick a sector not in any theme (expect `no_match`).
