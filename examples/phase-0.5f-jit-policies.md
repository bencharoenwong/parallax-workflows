# Phase 0.5f operational policies — JIT staleness + flag persistence

> Closes two compliance/UX gaps surfaced by senior review on 2026-04-27 (quant-trading-analyst go/no-go pass). Reads as a one-pager for a private-bank compliance officer or RM desk lead.

## 1. JIT timestamp staleness policy

When `/parallax-portfolio-builder --augment-silent` (or any future Phase-0.5f-wired consumer skill) makes a JIT MCP call to fill a silent dimension, every Suggestion carries a `data_as_of` timestamp from the Parallax response (`report_date` for `macro_analyst`, `report_date` for `get_telemetry`).

The policy:

| Age of `data_as_of` (today − response date) | Behavior |
|---|---|
| ≤ 7 days | Use directly. Tag as `[parallax_jit, <tool>[<args>]@<date>]`. No staleness annotation. |
| 8–30 days | Use, but tag as `[parallax_jit, <tool>[<args>]@<date>] (stale-N-days)` in the Tilt Source column. Include in the audit log entry as `staleness_warnings: [{path, days_old}]`. |
| > 30 days | Refuse to use. Treat the dimension as `[neutral]`. Log a `parallax_jit_refused_stale` entry on the audit chain with the requested call + the response's `data_as_of` so an auditor can reconstruct what was tried. Recommend the operator either run the consumer skill on a fresh date or switch to the explicit-pure path (no `--augment-silent`). |

**No silent freshening.** The skill never auto-re-runs an MCP call to bring the response within tolerance. If the operator wants fresh data, they re-invoke the consumer skill — that re-fires the MCP call at THIS new run's `now()`, gets a fresh response with a fresh `data_as_of`, and the new audit entry replaces the old one for that portfolio.

**Caching:** the consumer skill does NOT cache MCP responses across invocations. Each portfolio construction fires its own calls. This is wasteful at scale (200 portfolios per morning would fire ~8 MCP calls each = ~1600 calls), but correct under the auditability frame: every portfolio audit row carries the response that drove THAT portfolio's tilts. Caching across portfolios would mean two portfolios with `data_as_of: 2026-04-24` could differ on whether the response was fresh-at-construction-time or cached-from-3-days-ago — provenance breaks.

The right scaling answer is server-side caching at the Parallax MCP layer (response-level deduplication if the same call comes from N consumer-skill invocations within a short window), not client-side caching at the consumer-skill layer. That's a Parallax MCP team concern, not a house-view skill concern.

## 2. `--augment-silent` per-call vs per-RM-persistent flag

**Today (v1):** the flag is per-call. Each `/parallax-portfolio-builder` invocation either has `--augment-silent` or doesn't. RMs running the call manually can forget. RMs running the call via an automation (e.g., a morning-batch script for 200 portfolios) set it once in the script.

**The compliance risk:** when the same client's portfolio is reviewed across mornings — Monday with augment, Tuesday without (RM forgot the flag) — the audit trail shows different provenance shapes for the same portfolio. A compliance officer reading the trail will ask: "did the bank's view get fresher overnight, or did the RM's process change?" The honest answer (the latter) is operationally embarrassing.

**Mitigation in v1 (already in the SKILL.md):** every audit entry records the flag value. `augment_silent_flag: true` or `augment_silent_flag: false`. Compliance can see the flag-vs-augmentation correlation, so the inconsistency is auditable even if it's not prevented.

**The Phase 0.5g fix (deferred — separate ship):** desk-level persistent default. Two layers:

1. **Per-RM-desk default** in a config file the RM's session reads at start (`~/.parallax/rm-policy.yaml` or similar). E.g., `default_augment_silent: true` for desks where the policy is "always augment with current data." `default_augment_silent: false` for desks where the policy is "treat silent as neutral, never blend bank view with Parallax data without explicit per-call opt-in."
2. **Per-RM session toggle** to switch the default mid-day if needed. The audit entry records both the desk default and the session-effective value.

The Phase 0.5g design choice is whether the desk default goes in a file the operator controls (more flexible, harder to audit) or a server-side config (less flexible, fully auditable). For private banks the latter is probably right — the desk lead sets policy, the RM cannot override silently. **Decision deferred until first prospect feedback.**

**Until Phase 0.5g lands:** RMs running portfolio-builder for a fan-out batch should pass `--augment-silent` (or not) consistently across the batch. The audit-row `augment_silent_flag` field exposes inconsistency but does not prevent it.

## 3. What this gets you for the auditability pitch

A compliance officer reading the audit chain after these two policies are in place can answer:

- "Was this multiplier the bank's view or Parallax's?" → source tag column on the holdings table answers this row-by-row.
- "If Parallax's, when was the data?" → `data_as_of` in the augmented_dimensions block. If `> 30` days old, the dimension is refused (audit row says so).
- "Why did this portfolio get Parallax-augmented but yesterday's didn't?" → `augment_silent_flag` field on each audit row. Inconsistency is visible.
- "Can I reconstruct exactly what the system saw at the time?" → yes, by hash. View hash + audit entry hash chain + (Phase 0.5g) trusted_keys version.

That's the determinism+auditability story made operational.
