# Portfolio Diff Harness — Interface Specification

This document defines the protocol shape for verifying that a house view changes the output of a downstream consumer skill (e.g. `portfolio-builder`). Calibration parameters and auxiliary probe fixtures are internal to the reference implementation and not part of this public interface.

## Protocol: Dual-Leg Diff

Executes two "legs" of the same request within the same session:

1. **Leg A (Baseline):** Run without the house view.
2. **Leg B (Applied):** Run with the active house view.

### Environment Control

- **Leg A:** Set `PARALLAX_HOUSE_VIEW_DIR` to a fresh empty directory (e.g. `/tmp/empty-view-<pid>/`).
- **Leg B:** Set `PARALLAX_HOUSE_VIEW_DIR` to the directory containing the bundle to test.

### Paired-Call Assertion

For each leg, capture the exact tool-call signature for the primary universe-generation call (typically `build_stock_universe`).

- **Assertion:** The `query` parameter for `build_stock_universe` MUST be identical in both legs (except for tilt-prepended context).
- **Assertion:** Both outputs MUST contain the log line: `Active house view resolved from: <path>`.

## Output Contract

The agent must output the rank/weight diff in a strict JSON block wrapped in `<diff_output>` markers.

```json
<diff_output>
{
  "bundle_id": "<bundle-identifier>",
  "baseline": [
    {"symbol": "AAA.X", "rank": 1, "weight": 0.20}
  ],
  "applied": [
    {"symbol": "BBB.Y", "rank": 1, "weight": 0.20}
  ]
}
</diff_output>
```

If the agent fails to emit this block, the consumer runner is expected to flag a failure.

## Mechanical "What changed why"

Below the `<diff_output>` block, for every position with non-trivial shift, emit one mechanical line:

`SYMBOL SHIFT — tilt_reason, mult=X.XX×`

## Exit Semantics

Consumer runners implementing this protocol should distinguish at least three outcomes:

- **PASS** — median absolute shift within the calibrated pass/fail band for the bundle.
- **WEAK** — median absolute shift above the minimum but outside the warning band.
- **KILL** — median absolute shift below the threshold at which friction eats signal.

Specific band values and the kill-criterion threshold are maintained internally by the provider of the house-view reference implementation; this spec intentionally does not name them.
