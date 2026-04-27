---
name: parallax-house-view-diff
description: "Interface spec for verifying that a house view changes downstream portfolio output. Describes the dual-leg paired-call protocol and output contract. Calibration and reference runner are internal to Parallax."
negative-triggers:
  - Just loading a view → use /parallax-load-house-view
  - General portfolio building → use /parallax-portfolio-builder
gotchas:
  - This skill is a SPEC, not an executable runner. Consumers implementing the protocol provide their own execution + calibration.
  - JIT-load _parallax/house-view/tests/portfolio_diff_harness.md for the protocol definition.
  - Output MUST follow the `<diff_output>` JSON contract defined in the protocol spec.
---

# House View Diff — Interface Spec

Defines the protocol shape for verifying that an active house view shifts the output of a downstream consumer skill.

## Purpose

A consuming agent running a portfolio workflow with an active house view should be able to demonstrate — in the same session — that the view actually changed the resulting portfolio vs. the baseline. This skill describes *how* that demonstration is structured. It does not ship the calibration thresholds or a reference runner.

## Protocol (summary)

1. **Leg A:** execute the downstream skill with `PARALLAX_HOUSE_VIEW_DIR` pointing at an empty directory.
2. **Leg B:** execute the same skill with `PARALLAX_HOUSE_VIEW_DIR` pointing at the active view bundle.
3. Both legs must use identical `build_stock_universe` query parameters (except for tilt-prepended context).
4. Emit a `<diff_output>` JSON block comparing ranks and weights.
5. Append mechanical "what changed why" lines for shifted positions.

Full protocol: [`_parallax/house-view/tests/portfolio_diff_harness.md`](../_parallax/house-view/tests/portfolio_diff_harness.md).

## Exit semantics

Consumer runners should surface at least three outcomes — PASS, WEAK, KILL — corresponding to the shift magnitude falling within the pass band, outside the warning band, or below the economic-viability threshold respectively. Specific band values are maintained internally by the reference-implementation provider.

## Troubleshooting

- **"View did not load"** → Check `PARALLAX_HOUSE_VIEW_DIR` resolution per `_parallax/house-view/loader.md §1`.
- **"Paired-call protocol violated"** → Ensure `build_stock_universe` query is identical across legs.
- **"Markers absent"** → Ensure output is wrapped in `<diff_output>` tags.
