# Sample thesis corpus

Test theses for `/parallax-stress-test-thesis`, per `_parallax/`-style repo convention (mirrors
`parallax-load-house-view/samples/`). Used for golden-output review before a PR — not consumed at
runtime by the skill itself.

| File | Covers |
|---|---|
| `macro-led-long.md` | Macro-led long (rates → duration equity), no client profile — Pass 1 only |
| `single-name-financing.md` | Single-name bull case with an implicit financing-cost assumption |
| `ai-infra-sector.md` | Sector/theme thesis (AI infrastructure) with a fragile demand assumption |
| `weak-thesis.md` | Deliberately weak thesis — confirms the skill pushes back rather than rubber-stamping |
| `crypto-rotation-accumulator.md` + `crypto-rotation-retiree.md` | Same thesis, two `client_profile`s (27yo accumulator vs. 85yo drawing income) — the two-pass client-conditioning acceptance test: Pass-1 statuses must be identical across both runs; the holder-dependent layer and client-conditioned ranking must differ; the retiree run must be harsher and use the stronger disclaimer variant |
| `book-shared-rate-cut.md` | Three theses in one run — the **book-mode / Phase 6** acceptance test: two theses secretly share a "Fed keeps cutting" load-bearing premise (must canonicalize into one concentrated assumption + a correlated single-point-of-failure break condition); the third is a rates-agnostic diversifier. No sizing/recommendation; per-thesis Pass-1 statuses unchanged |

These files are the inputs, not the
expected outputs — outputs are produced live against current Parallax signals and reviewed
per-run, not pinned as golden fixtures (this skill has no house-view-style regression corpus by
design — it deliberately reads *today's* signal set, not a fixed historical snapshot).
