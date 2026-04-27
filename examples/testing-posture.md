# Testing Posture

These skills carry automated test coverage for their core modules and reproducible end-to-end examples. For operator verification post-install, the smoke-test patterns below establish that the skill is live and correctly wired against your Parallax MCP.

## Smoke tests (per skill)

Run in a fresh Claude Code session after install. Each is 2–5 minutes.

### Ingest a house view

```
/parallax-load-house-view <path-to-CIO-doc.pdf>
```

Pass criteria: walks through extraction → confirmation → save; `~/.parallax/active-house-view/` populated; audit log entry appended.

### Build a portfolio against an active view

```
/parallax-portfolio-builder "<your investment thesis>"
```

Pass criteria: output leads with a view-status banner; per-holding tilt source visible; saved view unchanged.

### Other consumer skills

`/parallax-rebalance`, `/parallax-thematic-screen`, `/parallax-morning-brief`, `/parallax-client-review`, `/parallax-explain-portfolio` follow the same shape: invoke with their documented inputs, confirm leading view-status banner (when view active), confirm audit chain extends.

## Compliance verification

Three claims an operator can verify against the audit chain:

1. **Determinism.** Same inputs to a consumer skill produce the same outputs.
2. **Provenance.** Every multiplier in any consumer artifact traces to a named source.
3. **Trust contract.** The saved house view never mutates from a consumer skill.

Inspect `~/.parallax/active-house-view/audit.jsonl` and the corresponding skill output to verify each.
