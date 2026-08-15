# Shared MCP Mock Fixtures

One JSON file per Parallax MCP endpoint consumed by parallax-* skills. These mocks back the contract tests in `../contract_validator.py` + `../contract_schemas.py` and are imported by per-skill `test_mcp_contracts.py` files.

## Why these exist

Multiple skills orchestrate the same Parallax MCP endpoints. Each skill reads a specific subset of fields from each response. If an upstream response shape changes silently, every consuming skill degrades silently.

The contract tests:

1. Define a per-endpoint schema (in `../contract_schemas.py`) listing the fields skills are **known** to read, marked required vs optional with expected types.
2. Validate that each happy-path mock JSON in this directory conforms to that schema.
3. Run sanity checks on values (factor scores in `[0,10]`, dates ISO, prices positive, weights in `[0,1]`).

A red contract test in CI surfaces drift before a customer hits it.

## Files

| File | Endpoint | Notes |
|---|---|---|
| `get_telemetry.json` | `mcp__claude_ai_Parallax__get_telemetry` | Market regime, signals, divergences |
| `analyze_portfolio.json` | `mcp__claude_ai_Parallax__analyze_portfolio` | **MANAGED — generated.** Full response: `{"success": true, "result": {…}}`. **Consumers read `response["result"][<block>]`** — the blocks are not at the top level. A 4-holding / 3-sector / 28-calendar-day book. `result` carries `_meta`, `portfolio_parameters`, `data_quality`, `portfolio_summary`, `performance_metrics`, `drawdown_analysis`, `portfolio_scores`, `concentration_metrics`, `company_contribution`, `sector_contribution`, `sector_allocation`, `time_period_returns`, `latest_holdings`. Shape corrected 2026-08-13 to the live response: `sector_allocation` and `sector_contribution` are **lists**, not dicts; holdings key on `ric`, not `symbol`; there is no `factor_exposures` block. `rolling_metrics` and `benchmark_prices` are not in this mock. |
| `analyze_portfolio_credit_exhausted.json` | `mcp__claude_ai_Parallax__analyze_portfolio` | **MANAGED — generated. Failure-mode fixture.** The credit-exhausted envelope: `success: true` on a call that FAILED, a `detail` object, and **no `result` key at all**. Branch on the presence of `result`, never on `success` — `if payload["success"]` passes here and then raises `KeyError`. |
| `export_price_series.json` | `mcp__claude_ai_Parallax__export_price_series` | One holding's daily OHLCV |
| `get_company_info.json` | `mcp__claude_ai_Parallax__get_company_info` | **MANAGED — generated.** One synthetic holding; ground-truth name oracle. Cross-references the first `analyze_portfolio` holding. |
| `check_portfolio_redundancy.json` | `mcp__claude_ai_Parallax__check_portfolio_redundancy` | **PROVISIONAL** — see below |
| `check_portfolio_redundancy_silent_fail.json` | `mcp__claude_ai_Parallax__check_portfolio_redundancy` | **Failure-mode fixture** — models the empty-payload silent-failure on sector-concentrated portfolios. Pair with the happy-path mock when testing skills that have sanity-check gates against this mode (portfolio-builder Step 4 + Step 6 fallback, halal-screen Step 2). |
| `get_assessment.json` | `mcp__claude_ai_Parallax__get_assessment` | AI synthesis (async, ~30-90s) |
| `get_score_analysis.json` | `mcp__claude_ai_Parallax__get_score_analysis` | **MANAGED — generated.** Weekly score history per ticker. Shape corrected 2026-08-13 to the live response: rows live under **`data`** (not `history`) with **lowercase** factor keys, sub-scores are 0-10 ints, and `total` is a separately-computed 0-10 composite that is **not** the mean of the five. Resolves the three-way divergence recorded in the 2026-08-11 `DECISIONS.md` entry ("Convert the credit-lens quality-trend bands…", fact D and the deferred fixture-shape alternative). |
| `get_news_synthesis.json` | `mcp__claude_ai_Parallax__get_news_synthesis` | News synthesis per ticker (async) |
| `macro_analyst.json` | `mcp__claude_ai_Parallax__macro_analyst` | One country's tactical view |

For multi-holding fan-out endpoints, the mock represents **one** call's response. Skills call them in parallel per holding / per top-mover.

## Provisional schemas

`check_portfolio_redundancy` field-level usage is not yet documented in any SKILL.md with explicit field reads. The schema is best-inference from the function name and the redundancy concept used in `portfolio-checkup`. When a skill explicitly relies on a specific field, validate the schema against an actual MCP call and update both the schema and this mock.

## How to add contract tests for a new skill

Create `skills/<skill>/scripts/test_mcp_contracts.py` and follow the import
pattern from any existing `test_mcp_contracts.py`. Per-skill realistic-values
tests encode the specific value assumptions that skill makes; structural
conformance is shared via ``contract_validator.validate``.

## Provenance: three categories, and one of them is generated

Every `.json` here is classified in `../test_fixture_provenance.py`, and the union of the three categories must equal this directory's listing. A file nobody classified fails the gate — that is the whole point. An unclassified file is one whose provenance nothing checks, so the gate refuses it until someone states where it came from.

| Category | What it claims | How it is checked |
|---|---|---|
| `MANAGED` | Reproducible byte-for-byte from `../gen_mock_fixtures.py` at a pinned seed | **Gate 1**: regenerate and compare. A proof, not a heuristic. |
| `HAND_AUTHORED` | Deliberately not regenerable (models a failure mode) | **Gate 2** precision budget only |
| `PRE_EXISTING` | Authored before the generator; outside its scope | **Gate 2** precision budget only |

`analyze_portfolio.json`, `get_company_info.json` and `get_score_analysis.json` are **MANAGED — do not hand-edit them and never paste a live capture over them.** They are generated:

```
python3 skills/_parallax/scripts/gen_mock_fixtures.py --write
```

The generator derives every value from a seeded synthetic price path, so the arithmetic identities the live API satisfies hold by construction rather than by transcription. `../test_gen_mock_fixtures.py` asserts those identities independently of the generator, which is what stops a generator edit from quietly changing the contract while gate 1 still agrees with itself.

Read the generator's module docstring before changing it. It documents the traps the fixture exists to keep exercised — the mean-vs-sum split inside `sector_contribution`, `invalid_fields` being `null` rather than `[]`, the calendar (not trading-day) grid, `top_5_share` exceeding 1, and above all that **`quantity × close_local` deliberately does not equal `ending_value`**, which is confirmed API behaviour and must never be asserted as an identity.

## How to refresh when the live MCP server changes

**For a `MANAGED` fixture, do not capture and paste.** Change `../gen_mock_fixtures.py` so it derives the new shape, re-run it with `--write`, and commit the generator change together with the regenerated fixture. Gate 1 fails otherwise, by design. Capturing a live response to "check the shape" is fine as a local, uncommitted reference; committing it is the incident.

For `HAND_AUTHORED` and `PRE_EXISTING` fixtures:

1. **Capture the new shape.** Hit the live endpoint via the MCP tool to read the shape. Author the fixture from that shape with your own values — do not commit captured output, and do not rely on scrubbing it, which has failed every time it was attempted.
2. **Update the mock** in this directory to match the new shape. Keep the same file name.
3. **Update the schema** in `../contract_schemas.py` to reflect the new contract — remove dropped fields, add new fields with required/optional markers, change types as needed.
4. **Re-read every SKILL.md that imports the schema** to confirm those skills are still reading fields that exist in the new shape. If a skill needs to change to read new fields, do that in the same PR.
5. **Run the tests** across all affected skills:
   ```
   pytest $(find skills -name test_mcp_contracts.py) -q
   ```
6. **Commit mock + schema + skill changes together.** The contract test is only a guard if it stays in sync with the live endpoint.

## How to add a new endpoint to the contract surface

1. Read the consuming SKILL.md(s) and identify which fields the skill reads from the response.
2. Add a new mock JSON in this directory (one happy-path response).
3. Add a new schema constant in `../contract_schemas.py` listing the fields with required/optional markers and types.
4. Per-skill: add `test_<endpoint>_mock_conforms_to_schema` + `test_<endpoint>_mock_has_realistic_values` in that skill's `test_mcp_contracts.py`.
5. Update the table above.

## Out of scope (v2)

- **Error-path mocks.** Each endpoint here gets one happy-path mock (exception: `check_portfolio_redundancy_silent_fail.json` was added 2026-05-25 to model the documented empty-payload silent-failure mode that 3 skills sanity-check against). Modeling other error responses ("data unavailable", quota exceeded, partial coverage) is deferred — failure-handling contracts are documented in `_parallax/coverage-matrix.md` and exercised in skill-level integration tests.
- **Cross-endpoint consistency.** The mocks each pin a single endpoint in isolation; they are not jointly consistent. Integration tests within each skill use coordinated fixture sets where needed.
