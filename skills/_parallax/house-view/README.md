# Parallax House View — Shared Core

The shared house-view infrastructure consumed by `parallax-load-house-view` (writer — bank CIO ingestion), `parallax-make-house-view` (writer — MCP-driven synthesis), `parallax-judge-house-view` (read-only consumer — drift monitor), and the portfolio / single-stock skills (readers).

This directory holds the canonical schema, the loader contract, the conflict-rendering helpers, the shared Step 3 confirmation gate, the provenance-class registry, the aggregator weighting table, the MCP capability inventory, the auto-on-load drift-gate protocol, and the Python modules that implement audit chaining, calibration-manifest verification, reasoning-chain emission, and gap detection. Skills JIT-load specific files within this directory; the directory itself is never loaded as a unit.

## Files

### Specification

| File | Purpose |
|---|---|
| `schema.yaml` | Canonical YAML structure. Single source of truth for the view's shape, metadata, tilt vocabulary, and `view_hash` computation. |
| `loader.md` | JIT-loaded by every consumer skill. Defines load-time validation, multiplier mapping, conflict resolution, output rendering, and audit logging. |
| `render_helpers.md` | Canonical templates for view-aware conflict banners (single-stock skills' §7.1/§7.2/§7.3 surfaces). |
| `auto-on-load-judge-pattern.md` | Single source of truth for the consumer-skill drift-gate protocol. JIT-loaded by `parallax-portfolio-builder`, `parallax-rebalance`, and `parallax-thematic-screen` to auto-fire `/parallax-judge-house-view --dry --json` when the active view is older than 30 days; one-line banner only on `drift_material` severity. |
| `MCP_FIELD_INVENTORY.md` | Phase A0 capability validation artifact. Documents which pillar inputs are available as structured MCP fields versus prose-extracted, anchoring the maker's pillar formulas to actual MCP coverage. |
| `aggregator_weights.yaml` | v0 MSCI ACWI weights for the 14 MCP-covered markets (sum 1.0). Consumed by `parallax-make-house-view` cross-country aggregation. |
| `signing/trusted_keys.json` | Pinned Ed25519 verification keys. The verifier rejects any manifest whose `signing_key_id` is not in this file. The test-only kid is deliberately included so auditors can run round-trip on a fresh clone; production deployments without that kid are unaffected. |
| `requirements.txt` | Exact pins for the verifier's deps (`pynacl==1.6.2`, `rfc8785==0.1.4`, `pyyaml==6.0.3`). The lockfile MUST be exact, not a range, for long-horizon replay determinism. |

### Python modules

All modules are pure functions with no MCP coupling. They import cleanly into any harness.

| Module | Public API | Purpose |
|---|---|---|
| `audit_chain.py` | `append_entry(audit_path, entry_data)` | Append-only hash-chained audit log. Each entry's `prev_entry_hash` links to the previous entry. RFC 8785 JCS canonicalization. Tampering with any entry breaks the chain on next verification. |
| `audit_export.py` | `create_bundle(view_id) -> Path` | Export a regulator-grade tarball: view + prose + provenance + full audit trail. Refuses to ship if the chain is broken. |
| `manifest_verify.py` | `verify_manifest(manifest_dict, trusted_keys_path)` | Pure function. Returns parsed dict + chain-anchor hash on valid Ed25519+JCS signature. Raises typed errors on failure: `ManifestMalformed`, `KeyIdUnknown`, `KeyIdNotYetValid`, `KeyIdExpired`, `SignatureInvalid`, `ManifestSignatureMissing`. |
| `manifest_cache.py` | `ManifestCache(...)`, `load_manifest(...)` | On-disk cache layer + load orchestrator. Persists verified manifests to `~/.parallax/calibration/<org_id>_<calibration_version>.json` with atomic `0600`/`0700` writes. Strict expiry boundary, monotonicity check, and dead-state guard (fresh manifest with unknown kid AND cached manifest expired raises `DeadStateNoFallback`). |
| `chain_emit.py` | `emit_chain(...)`, `emit_phase_0_chain(...)` | Reasoning chain emitter. Builds the chain envelope (spec_version, skill_version, run_id, org_id, manifest_ref, view, base_scores, final_portfolio, signature) and writes it to `~/.parallax/reasoning-chains/<YYYY-MM>/<run_id>.yaml` with atomic `0600`/`0700`. Refuses to overwrite existing run_id files unless explicitly opted in. |
| `chain_prune.py` | `parallax chain prune --before YYYY-MM-DD [--confirm]` | Retention CLI. Dry-run by default, `--confirm` to delete. Refuses symlinked chain_dir; declines files modified after process start; parses `--before` strictly. |
| `gap_detect.py` | `detect_gaps(draft_view, prose, extraction_notes, source_type) -> list[Gap]` | Identifies fillable gaps: silent (0/null AND name+aliases not mentioned in prose/notes via word-boundary regex match) or low-confidence non-zero (`extraction_confidence[dim] < 0.4`). Eligible dimensions: `macro_regime`, `factors`, `regions`, `sectors`. Pillars / themes / styles / excludes are never returned. Pure module, no I/O. |
| `gap_suggest.py` | `plan_calls(...)`, `report_skipped_leaves(...)`, `fold_responses(...)` | Pairs with `gap_detect`. Plans deduplicated MCP calls; reports per-dimension leaves silently dropped due to no MCP coverage; folds responses into Suggestions. The consuming skill makes the actual MCP calls and feeds responses back. Pure module. |
| `view_status.py` | `compute_status(view_dir=None, today=None) -> ViewStatus`; CLI `python -m view_status [--dir PATH] [--json] [--exit-code-by-state]` | Operator-agnostic status + banner helper. Single source of truth for expiry math across operator LLMs (loader.md §2.6 delegates to this). Returns `state` ∈ {`none`, `malformed`, `not_yet_effective`, `expired`, `critical`, `warning`, `active`}, plus `banner` (verbatim string to surface), `days_remaining`, and `tilts_apply` (false for `none`/`malformed`/`expired`/`not_yet_effective`). Thresholds: `CRITICAL_DAYS=10`, `WARNING_DAYS=14`. Resolution order for `view_dir`: explicit arg → `$PARALLAX_HOUSE_VIEW_DIR` → `~/.parallax/active-house-view/`. |
| `gate_present.py` | `GateContext`, `GateResult`, `run_gate_loop(...)` | Extracted Step 3 confirmation gate, shared by `parallax-load-house-view` and `parallax-make-house-view`. Drives the operator disposition loop (accept / edit / reject) and renders the canonical pre-save preview. Single source of truth for gate display + disposition handling across both writer skills. |
| `provenance_classes.py` | `validate_provenance_entry(entry, mode='read'\|'write')` + 6-class registry | Enforces the canonical provenance vocabulary: `prose_extraction`, `macro_regime_rule`, `manual_edit`, `generator_synthesis`, `judge_recommendation`, `parallax_data_fill` (write-deprecated, read-accepted for backward compat). Write mode rejects deprecated classes; read mode keeps legacy entries loadable. |

### Tests

Coverage is in the adjacent `tests/` directory. The test signing key + signed test fixture + fixture generator are deliberately public so auditors can run round-trip on a fresh clone.

| Suite | Coverage |
|---|---|
| `tests/test_view_hash.py` | Reference implementation of `view_hash` computation; round-trip determinism. |
| `tests/test_audit_chain.py` | Append, hash linkage, tamper detection, race-free file open, adaptive tail read. |
| `tests/test_audit_export.py` | Bundle creation, broken-chain refusal. |
| `tests/test_manifest_verify.py` | Round-trip + tamper coverage: valid signature, mutated values block, unknown kid, empty signature value, anti-collision guard. |
| `tests/test_manifest_cache.py` | Atomic-write perms, loose-perms warning, strict expiry boundary, monotonicity rollback rejection, dead-state guard, orchestrator new-version write, cache-only fallback, offline expired-cache warning. |
| `tests/test_chain_emit.py` | Envelope structure, anti-collision check, refuse-overwrite, atomic write. |
| `tests/test_gap_detect.py` | Silent-eligible, mentioned-via-prose-alias, ineligible-dimension, low-confidence non-zero, wizard-mode skip, macro_regime null tokens, word-boundary alias matching. |
| `tests/test_gap_suggest.py` | Planner dedup logic, regime-tag → factor-delta mapping, sector positioning across response shapes, end-to-end fold preserving `Gap.reason`. |
| `tests/test_gap_suggest_live.py` | Regression coverage against captured live MCP responses (`tests/fixtures/macro_analyst_*_live.json`). |
| `tests/test_skill_integration.py` | End-to-end SKILL.md write paths against fixture inputs. |
| `tests/test_view_status.py` | Boundary coverage for `view_status.compute_status`: 9/10/13/14-day tier transitions (`critical`/`warning`/`active`), plus `none`, `malformed`, `not_yet_effective`, and `expired` paths. |
| `tests/test_gate_present.py` | Confirmation-gate state machine: accept / edit / reject disposition loop, gate-context rendering, and re-prompt behavior on invalid input. |
| `tests/test_uninstall.py` | Paired-uninstall parity for `parallax-load-house-view` ↔ `parallax-make-house-view` and structural audit-row parity across writer skills. |
| `tests/test_integration_make_judge.py` | End-to-end maker → save → judge round-trip: synthesized view passes through gate, persists with `generator_synthesis` provenance, and is correctly classified by `/parallax-judge-house-view`. |
| `tests/test_e2e.py` | Maker / judge end-to-end happy path under default config. |
| `tests/test_e2e_versioning.py` | Multi-version archive + monotonic `version_id` invariants across maker and load writers. |
| `tests/test_e2e_calibration.py` | Calibration-manifest interactions: maker honors active manifest, judge surfaces stale-calibration warnings. |
| `tests/test_e2e_concurrency.py` | Sub-second concurrent runs: judge bundle nonce prevents silent overwrite; audit-chain append remains race-free. |
| `tests/test_e2e_multi_tenant.py` | Per-org isolation across `$PARALLAX_HOUSE_VIEW_DIR` overrides — no cross-tenant audit or bundle leakage. |
| `tests/test_e2e_rm_operator_workflow.py` | RM operator path: load → make → judge with shadow-diff and accept/reject branches. |
| `tests/test_e2e_view_status_countdown.py` | End-to-end status countdown across tier transitions (`active` → `warning` → `critical` → `expired`) under fast-forwarded clocks. |
| `tests/golden/pre_v2_house_view/` | Frozen pre-v2 view + audit/provenance baseline (`view.yaml`, `prose.md`, `provenance.yaml`, `audit.jsonl`). `generate_golden.py` regenerates it; the loader must continue to parse this snapshot byte-identically. |

Run the suite from the repo root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r skills/_parallax/house-view/requirements.txt pytest
pytest skills/_parallax/house-view/tests/
```

A temp venv is required because PEP 668 blocks Homebrew Python's pip from installing into the system environment.

## Storage

| Artifact | Path | Permissions |
|---|---|---|
| Active house view | `~/.parallax/active-house-view/` | dir `0700`, files `0600` |
| Archived versions | `~/.parallax/active-house-view/.archive/<view_id>-<version_id>/` | dir `0700`, files `0600` |
| Calibration cache | `~/.parallax/calibration/` | dir `0700`, files `0600` |
| Reasoning chains | `~/.parallax/reasoning-chains/<YYYY-MM>/` | dir `0700`, files `0600` |
| Judge report bundle | `~/.parallax/judge-reports/<judged_version_id>-<timestamp>-<6-char-nonce>/` (contains `report.md`, `report.json`, `mcp_responses.jsonl`, `audit_entry.json`) | dir `0700`, files `0600` |

Override the active-view location with `PARALLAX_HOUSE_VIEW_DIR` — both the loader and `view_status.py` honor this variable. `view_status` additionally accepts an explicit `view_dir=` kwarg or `--dir` CLI flag; resolution order is explicit arg → `$PARALLAX_HOUSE_VIEW_DIR` → default `~/.parallax/active-house-view/`. Override the calibration / chain locations via the corresponding constructor arguments to `ManifestCache` and `emit_chain`.

A managed, org-keyed backend (Supabase, accessed through the Parallax MCP server) is on the roadmap. Loader semantics carry forward unchanged; only the resolver mechanism changes.

## Why a shared subdir under `_parallax/`?

Mirrors the `AI-profiles/` pattern: a family of related files (schema + loader + Python modules + tests) lives together rather than scattered across consumer skills. Skills JIT-load specific files within this directory; the directory itself is never loaded as a unit.
