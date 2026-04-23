# Portfolio Diff Harness — Public Spec

Interface specification for the house-view diff protocol. The spec describes the method shape — paired dual-leg execution, call-capture assertions, output contract. The reference implementation and calibration parameters are internal to Parallax.

## What this spec covers

- Protocol: dual-leg paired-call execution (Leg A baseline, Leg B applied)
- Environment control via `PARALLAX_HOUSE_VIEW_DIR`
- Paired-call assertion on `build_stock_universe` invocations
- Output contract: `<diff_output>` JSON block + "what changed why" mechanical lines
- Exit semantics: PASS / WEAK / KILL (calibration thresholds are internal)

See [`portfolio_diff_harness.md`](portfolio_diff_harness.md) for the protocol.

## What this spec does not cover

Calibration parameters, auxiliary test fixtures, and the reference runner are maintained internally and not part of the public interface contract.

## Running the spec

Implementors build their own diff runner against the protocol. The `/parallax-house-view-diff` skill shell describes the expected invocation shape for Claude Code agents orchestrating the diff.

For enquiries about the Parallax reference runner or calibration, contact the Parallax team.
