# Desk Book Format

## §1 Location and Precedence

Read `$PARALLAX_DESK_BOOK_PATH` when set, otherwise `~/.parallax/desk-book/book.yaml`.

Inline input replaces the saved book completely. Never merge inline clients with saved-book clients, because merging silently changes who appears on the desk call list. For saved-book subsets, filter by `client_name` or `client_ref`; report unmatched subset names explicitly.

## §2 Schema

```yaml
schema_version: 1
desk_name: "Equity Advisory"
updated_at: "2026-07-18T17:40:00Z"
default_threshold_pct: 5.0
default_min_impact_pp: 0.5
clients:
  - client_name: "Example Family Office"
    client_ref: "EX-001"
    holdings:
      - symbol: "AAPL.O"
        weight: 0.12
        asset_class: equity
      - symbol: "SPY"
        weight: 0.08
        asset_class: etf
```

`schema_version`, `clients[].client_name`, and non-empty holdings are required. `client_ref`, `default_threshold_pct`, `default_min_impact_pp`, and `asset_class` are optional. When present, `asset_class` must be exactly `equity` or `etf`, and a symbol must have the same classification in every client book.

## §3 Validation

Run validation before any Parallax tool call:

- `schema_version` must equal `1`; otherwise refuse to run and show the expected shape.
- Weights must be numeric, `> 0`, and `<= 1`.
- Per-client weights in `[0.95, 1.05]` are renormalised silently; outside that band, renormalise and flag the client.
- Duplicate client names are suffixed `#2`, `#3`, and flagged.
- Duplicate symbols within a client are summed and flagged.
- Symbols are trimmed and upper-cased. Bare ticker resolution follows `_parallax/parallax-conventions.md §1`; fund/OEIC-shaped identifiers use that not-covered fallback.

## §4 Staleness

Compute `age_days` from `updated_at`:

| Age | Tier | Rendering |
|---|---|---|
| `<= 30` | fresh | provenance line only |
| `31-90` | warn | visible warning near the top |
| `> 90` | stale | stronger visible warning near the top |
| missing/unparseable | unknown | treat as stale; say update date unknown |

The skill runs in every tier. Staleness changes trust in the weights, not whether the RM receives a report.

## §5 Privacy

The book lives in plaintext under the operator's OS account. Recommend `chmod 600` and keeping it outside cloud-sync folders.

Client names and weights stay local. Only the deduplicated symbol union is sent to Parallax MCP tools. `--redact-names` renders clients as `Client 1..N`; the mapping is not rendered. The skill never writes the desk book.

If `asset_class` is omitted, the skill may need `etf_profile` classification probes. Its cost is currently UNVERIFIED in `_parallax/token-costs.md`; populating `asset_class` avoids those probes.
