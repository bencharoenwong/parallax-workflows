# PR #25 follow-up — Tier 1 audit-gate artifact

**Status:** INFORMAL. Three e2e runs were executed during the implementation session, but the results live only in the conversation transcript — no committed artifact captures them.

## What was specced

The locked implementation plan (`~/.claude/notes/2026-05-16-1900-final-plan-wire-branding-houseview-skills.md`) included an `[AUDIT GATE]` step between Tier 1 pilots and Tier 2 propagation. Three scenarios per pilot:

1. No client config, no active view → default-Parallax output
2. Valid client config, no view → Branding Header + Provenance with `white-label (source: ...)`
3. `error=logo_missing` → text-only header, Provenance notes unavailable

Plus, for skills with new house-view wiring, a fourth scenario: active view → §7 / §3 / §7.4 tokens fire correctly.

## What was actually executed

| Skill | Scenarios run live | Result |
|---|---|---|
| macro-outlook | Default config + active view; §7.4 regime-alignment fired | ✅ Partial-alignment case handled |
| portfolio-checkup | Default config + active view; §3 multipliers applied (6.19 → 6.01) | ✅ Per-holding scores unchanged |
| due-diligence | Default config + active view; §7.1 fired, §7.3 correctly suppressed (score 5.2 < 7), §6 audit log structure rendered | ✅ Read-only invariant preserved |

Each run involved real Parallax MCP calls. Results were rendered as in-chat Output Format and inspected against expected structural elements (preamble placement, tilt application or non-application, Provenance line, view-aware disclaimer).

## Gap

The audit happened. The artifact didn't. Specifically missing:

- No committed receipt showing the three skill runs (output, observed properties, pass criteria).
- No record of the 13 skills NOT verified live (assumed-correct by pattern uniformity with the 3 that were).
- The DECISIONS.md entry on "Tier 1 convergence follow-up" mentions trigger criteria ("1 week stable + 0 voice-leak observations") that depend on operational observation, not on this audit gate.

## Recommended follow-up

**P2 (artifact creation):** Convert the conversation-transcript audit into `docs/analysis/2026-05-17-tier1-pilot-audit-receipt.md` with:

1. Per-skill scenario table (skill, inputs, view state, expected output structure, observed output structure, PASS/FAIL).
2. The three full rendered outputs as appendices (or links to the prior session if accessible).
3. Explicit list of 13 unverified Tier 2 skills assumed-correct by pattern; concrete plan to verify on first real invocation OR via a synthetic e2e run for at least one Tier 2 with new hv wiring (recommend pair-finder — has both §7 and dual-leg complexity that's unlike the verified ones).

**P3 (operational ongoing):** Establish "first-invocation audit" pattern: when each of the 13 unverified skills is invoked for real for the first time, capture observed Branding Header / Provenance / view rendering against expected. Append to the receipt doc.

## Risk if deferred

MEDIUM. The 3 verified skills exercise the dominant patterns (§3, §7, §7.4) but pair-finder is single-stock-dual-leg which has no precedent in the verified set. A wiring bug specific to pair-finder would only surface on first long/short pair invocation. Not data-loss risk; presentation-only.

## Related

- PR #25: feat/wire-branding-houseview-skills
- DECISIONS.md entry 2026-05-16 (Tier 1 convergence schedule)
- [[2026-05-17-cio-letter-prep-e2e-receipt]]
- [[2026-05-17-drift-gate-regex-tightening]]
