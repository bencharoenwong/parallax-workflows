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
| `analyze_portfolio.json` | `mcp__claude_ai_Parallax__analyze_portfolio` | Factor + sector + concentration, plus extended fields (company_contribution, portfolio_summary, drawdown_analysis, performance_metrics, latest_holdings, sector_allocation, sector_contribution, time_period_returns, portfolio_scores) used by cio-letter-prep Batch B. Schema updated 2026-06-10 to reflect the corrected `portfolio` + `fields` call shape. `rolling_metrics` is in the schema (OPTIONAL) but not in this mock — contract tests for skills that request it will not exercise that field via this fixture. |
| `export_price_series.json` | `mcp__claude_ai_Parallax__export_price_series` | One holding's daily OHLCV |
| `get_company_info.json` | `mcp__claude_ai_Parallax__get_company_info` | One holding; ground-truth name oracle |
| `check_portfolio_redundancy.json` | `mcp__claude_ai_Parallax__check_portfolio_redundancy` | **PROVISIONAL** — see below |
| `check_portfolio_redundancy_silent_fail.json` | `mcp__claude_ai_Parallax__check_portfolio_redundancy` | **Failure-mode fixture** — models the empty-payload silent-failure on sector-concentrated portfolios. Pair with the happy-path mock when testing skills that have sanity-check gates against this mode (portfolio-builder Step 4 + Step 6 fallback, halal-screen Step 2). |
| `get_assessment.json` | `mcp__claude_ai_Parallax__get_assessment` | AI synthesis (async, ~30-90s) |
| `get_score_analysis.json` | `mcp__claude_ai_Parallax__get_score_analysis` | Weekly score history per ticker |
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

## How to refresh when the live MCP server changes

When upstream Parallax MCP changes a response shape:

1. **Capture the new shape.** Hit the live endpoint via the MCP tool and save the response. Sanitize any tenant-specific identifiers.
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
