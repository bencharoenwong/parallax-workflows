# JIT augmentation policies

Operational rules for the just-in-time (JIT) data augmentation path used by consumer skills when the active house view is silent on a dimension a portfolio decision depends on. Reads as a one-pager for a compliance officer or operations lead.

## 1. Staleness policy

When a consumer skill makes a JIT data lookup, every suggestion carries a `data_as_of` timestamp from the response. Behavior by age:

| Age (today − response date) | Behavior |
|---|---|
| ≤ 7 days | Use directly. Tag with the source tool + as-of date. |
| 8–30 days | Use, but mark the source tag as stale and record a staleness warning on the audit entry. |
| > 30 days | Refuse. Treat the dimension as neutral and log a refused-stale entry on the audit chain. Operator should re-run for fresh data or accept the explicit-pure path. |

**No silent freshening.** The skill never auto-re-runs to bring a response within tolerance. Re-invocation is the operator's choice.

**No client-side caching across consumer-skill invocations.** Each portfolio construction fires its own calls. This is verbose at scale (200 portfolios × N calls each) but correct under the auditability frame: every portfolio's audit row carries the response that drove THAT portfolio's tilts. Cross-portfolio caching would break per-portfolio provenance. The right scaling answer is server-side response-level deduplication, not client-side caching.

## 2. Augmentation flag persistence

Today the JIT-augment flag is per-call. Operators running fan-outs (200 portfolios per morning) set it once in the calling script; manual operators set it per invocation.

**Compliance risk:** the same client's portfolio reviewed Monday with augment ON and Tuesday with augment OFF leaves audit trails with different provenance shapes for the same portfolio. A compliance officer reading the trail can see the inconsistency (the flag value is recorded on every audit row) — so it's auditable, but not prevented.

**Mitigation today:** every audit entry records the flag value. Inconsistency is visible.

**Future direction (deferred):** desk-level persistent default. The desk lead sets one default policy that applies across an operator's session; the audit entry records both the desk default and the session-effective value. The implementation choice (operator-controlled config vs centrally-managed policy) depends on first prospect feedback — for regulated entities, centrally-managed is likely the right answer.

**Until that ships:** operators running fan-outs should pass the flag consistently across the batch.

## 3. What this gets you for the auditability story

A compliance officer reading the audit chain can answer:

- **"Was this multiplier the bank's view or current data?"** → source tag column on the holdings table, row-by-row.
- **"If current data, when was it?"** → `data_as_of` in the augmented-dimensions block. If beyond 30 days, the dimension was refused (audit row says so).
- **"Why did this portfolio get augmented but yesterday's didn't?"** → flag value on each audit row. Inconsistency is visible.
- **"Can I reconstruct what the system saw at the time?"** → yes, by hash. View hash + audit entry hash chain.

That's the determinism + auditability story made operational.
