# `--why <tilt-path>` — Provenance Resolution

JIT-loaded by `parallax-load-house-view` only when `--why` is invoked. Defines path parsing, derivation resolution order, and per-source output formats.

## Path parsing

- Takes a dotted path into the view: `tilts.factors.momentum`, `tilts.sectors.information_technology`, `tilts.macro_regime.growth`.
- If the caller omits the `tilts.` prefix (bare `factors.momentum`), prepend it automatically before lookup.
- The path MUST resolve to a leaf (a scalar value under `tilts`), not a parent map. If the caller passes a parent (e.g., `tilts.macro_regime` without a sub-field), emit:

  ```
  --why requires a leaf path; <path> is a parent. Try one of: tilts.macro_regime.growth, tilts.macro_regime.inflation, ...
  ```

  and exit.

## Provenance resolution order

### 1. Read `provenance.yaml` if present

Look up the leaf's `derivation` list. The LAST entry is the effective source — later entries supersede earlier ones (e.g., a `manual_edit` after a `prose_extraction`).

Branch on `type`:

| Type | Output |
|---|---|
| `prose_extraction` | Quote `source_span` verbatim and emit: `Source: CIO prose, span '<source_span>' (confidence <c>)` |
| `macro_regime_rule` | Emit: `Source: loader.md auto-mapping. Rule: <rule_ref>. Trigger: <trigger>. Confidence <c>.` |
| `manual_edit` | Emit: `Source: manual edit at confirmation gate. Prior value: <prior_value>. Notes: <edit_notes>.` Then recursively surface the entry BEFORE the edit so the auditor sees both the original derivation and the override. |

The `parallax_data_fill` branch is not produced at ingest scope — Parallax-derived values no longer appear in saved-view provenance. Legacy views from a deprecated ingest-time-augment design may carry `parallax_data_fill` entries; emit for back-compat reading:

```
Source: legacy Parallax gap-fill. Tool: <source_tool> with args <source_call_args>. Snippet: '<source_snippet>'. Data as of <data_as_of>. NOT from the uploaded document — captured at ingest, may have drifted.
```

### 2. Fallback: `prose.md` targeted re-read

If `provenance.yaml` is absent or the leaf has no entry (legacy view, or zero-tilt path), fall back to the `prose.md` targeted re-read: quote the spans of prose.md that support the tilt value, or note:

```
no explicit support in prose — may be auto-applied per loader.md §3 macro_regime mapping
```

Zero schema cost in the fallback path — runs against existing `prose.md`.

## Zero-tilt edge case

If the path is a valid leaf but the tilt value is zero (omitted or neutral), before exiting scan `extraction.extraction_notes` for any mention of the field name (e.g., "momentum" for `tilts.factors.momentum`; "information_technology" or "tech" for `tilts.sectors.information_technology`).

- If found:

  ```
  Tilt is currently zero but extraction_notes mentions this field — may reflect an edit at the confirmation gate or a re-extraction that changed the value. Run `--version-history` to inspect prior values.
  ```

- If not found:

  ```
  Tilt is zero (neutral) — no active tilt to explain.
  ```
