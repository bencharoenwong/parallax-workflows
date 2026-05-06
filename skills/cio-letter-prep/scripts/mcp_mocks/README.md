# MCP Mock Fixtures

One JSON file per Parallax MCP endpoint that the `cio-letter-prep` skill
consumes. These mocks back the contract tests in
`../test_mcp_contracts.py` and double as fixtures for the future
end-to-end / golden-Word integration test.

## Why these exist

The skill orchestrates ~9 Parallax MCP endpoints (Batches A and B in the
`SKILL.md` workflow). Each endpoint has a documented response shape — a
contract — and the skill reads specific fields from that shape. If an
upstream response shape changes silently, the skill degrades silently.

The contract tests:

1. Define a per-endpoint schema (in `test_mcp_contracts.py`) listing the
   fields the skill is **known** to read, marked required vs optional with
   expected types.
2. Validate that each happy-path mock JSON in this directory conforms to
   that schema.
3. Run sanity checks on values (factor scores in `[0,10]`, dates ISO,
   prices positive, weights in `[0,1]`).

A red contract test in CI surfaces drift before a customer hits it.

## Files

| File | Endpoint | Notes |
|---|---|---|
| `get_telemetry.json` | `mcp__claude_ai_Parallax__get_telemetry` | Market regime, signals, divergences |
| `analyze_portfolio.json` | `mcp__claude_ai_Parallax__analyze_portfolio` | Factor + sector + concentration; called twice (current + prior) — same shape |
| `export_price_series.json` | `mcp__claude_ai_Parallax__export_price_series` | One holding's daily OHLCV; skill fans out per equity holding |
| `get_company_info.json` | `mcp__claude_ai_Parallax__get_company_info` | One holding; ground-truth name oracle |
| `check_portfolio_redundancy.json` | `mcp__claude_ai_Parallax__check_portfolio_redundancy` | **PROVISIONAL** — see below |
| `get_assessment.json` | `mcp__claude_ai_Parallax__get_assessment` | One mover's AI synthesis (async, ~30-90s) |
| `get_score_analysis.json` | `mcp__claude_ai_Parallax__get_score_analysis` | One mover's weekly score history |
| `get_news_synthesis.json` | `mcp__claude_ai_Parallax__get_news_synthesis` | One mover's news (async) |
| `macro_analyst.json` | `mcp__claude_ai_Parallax__macro_analyst` | One country's tactical view |

For multi-holding fan-out endpoints (`export_price_series`,
`get_company_info`, `get_score_analysis`, `get_assessment`,
`get_news_synthesis`), the mock represents **one** call's response. The
skill calls them in parallel per holding / per top-mover.

## Provisional schemas

`check_portfolio_redundancy` field-level usage is not yet documented in
any existing SKILL.md that we could find. The schema is best-inference
from the function name and from the redundancy concept used in
`portfolio-checkup`. When the skill author wires this endpoint into
`cio-letter-prep`, validate the schema against an actual MCP call and
update both the schema and this mock.

## How to refresh when the server changes

When upstream Parallax MCP changes a response shape:

1. **Capture the new shape.** Hit the live endpoint via the MCP tool and
   save the response (or copy from a real run's logs). Sanitize any
   tenant-specific identifiers.
2. **Update the mock** in this directory to match the new shape. Keep
   the same file name.
3. **Update the schema** in `../test_mcp_contracts.py` to reflect the
   new contract — remove dropped fields, add new fields with
   required/optional markers, change types as needed.
4. **Re-read the consuming SKILL.md** (when it lands) to confirm the
   skill is still reading fields that exist in the new shape. If the
   skill needs to change to read new fields, do that in the same PR.
5. **Run the tests** — `pytest skills/cio-letter-prep/scripts/test_mcp_contracts.py -v`.
   They should all pass.
6. **Commit mock + schema together.** The contract test is only a
   guard if it stays in sync with the live endpoint.

## How to add a new endpoint

1. Read the consuming SKILL.md and identify which fields the skill
   reads from the response.
2. Add a new mock JSON in this directory (one happy-path response).
3. Add a new schema constant in `test_mcp_contracts.py` listing the
   fields with required/optional markers and types.
4. Add two tests: `test_<endpoint>_mock_conforms_to_schema` and
   `test_<endpoint>_mock_has_realistic_values`.
5. Update the table above.

## Out of scope (v2)

- **Error-path mocks.** Each endpoint here gets one happy-path mock.
  Modeling error responses ("data unavailable", quota exceeded, partial
  coverage) is deferred — the skill's failure-handling contracts are
  documented in `_parallax/coverage-matrix.md` and exercised in the
  end-to-end integration test (Task 4).
- **Cross-endpoint consistency.** The mocks each pin a single endpoint
  in isolation; they are not jointly consistent (e.g., the price series
  here is for `AAPL.O` while `get_assessment` may reference different
  fundamentals). The integration test will use a coordinated fixture set.
