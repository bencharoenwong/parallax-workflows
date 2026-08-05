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
| `signing/trusted_keys.json` | Pinned Ed25519 verification keys. The verifier rejects any manifest whose `signing_key_id` is not in this file. The test-only kid is deliberately included so auditors can run round-trip on a fresh clone; keys marked `use: "test-only"` are rejected at verify time (`key_test_only`) unless the caller opts in with `allow_test_keys=True` (CLI: `--allow-test-keys`), so its presence carries no production trust. |
| `requirements.txt` | Exact pins for the verifier's deps (`pynacl==1.6.2`, `rfc8785==0.1.4`, `pyyaml==6.0.3`). The lockfile MUST be exact, not a range, for long-horizon replay determinism. |

### Python modules

Every module below is pure functions with no MCP coupling and imports cleanly into any harness — with one exception: `view_commit.py` is the module that actually touches the filesystem. It is the sanctioned writer of `view.yaml`, `prose.md`, and `provenance.yaml` **for `parallax-load-house-view`'s commit paths** — not repo-wide: `parallax-make-house-view`'s `maker.py` still writes all three directly with `write_text()`, and its migration is deferred (see DECISIONS.md 2026-08-05). Maker is not unlocked — its `save_view` wraps `_save_view_locked` in the same `audit_chain.view_transaction` on the same `.house-view.lock`, and re-reads `parent_version_id` under it, raising `ViewChangedMidRun` on drift. It is *unstaged*: it writes each artifact in place, with no `.tmp` sibling and no atomic rename, and `chmod`s to `0600` after the write rather than creating at that mode. The practical consequence is a torn-artifact risk, not a lost update — a crash or `ENOSPC` mid-write leaves a truncated, unparseable `view.yaml` where a staged rename would have left the previous version intact, and consumers that read the view without taking the transaction (`view_status.py`, for one) can observe a partially written or briefly umask-permissive file. Maker's guard also covers `parent_version_id` only; it has no row-vs-bytes assertion equivalent to `_validate_row_matches_bytes`. `audit.jsonl` is never staged, renamed, or removed by anything, `view_commit.py` included — only appended, via `audit_chain.append_entry`. `commit_view` is impure top to bottom (it acquires the view transaction itself); `commit_view_locked` is impure but requires the caller to already hold a `TransactionToken` from `view_transaction`, because `view_transaction` is not re-entrant and a nested acquire deadlocks rather than erroring.

| Module | Public API | Purpose |
|---|---|---|
| `audit_chain.py` | `append_entry(audit_path, entry_data)`, `view_transaction(view_dir)`, `identity_diff(captured, committed)`, `ViewChangedMidRun`, `TransactionToken` | Append-only hash-chained audit log. Each entry's `prev_entry_hash` links to the previous entry. RFC 8785 JCS canonicalization. Tampering with any entry breaks the chain on next verification. `view_transaction` is a `flock`-based context manager serializing a view read + audit append across threads and processes (used by stress and judge race guards, and by `view_commit.commit_view`); it now yields a frozen `TransactionToken` (view_dir-scoped proof of the held lock) rather than nothing, so a callee can be handed proof it is already inside the transaction instead of re-acquiring it. `identity_diff` single-sources the compare-and-format half of those guards and `ViewChangedMidRun` (a `RuntimeError` subclass, so pre-existing handlers hold) is the base both raise; which identity fields each guard cites, and how it reloads the committed view, stay at the call site because they legitimately differ. |
| `view_commit.py` | `commit_view(view_dir, *, write, remove, audit_entry, expected_identity)`, `commit_view_locked(view_dir, *, token, write, remove, audit_entry, expected_identity)`, `compute_view_hash`, `compute_prose_body_hash`, CLI `python3 -m view_commit --mode {save,extend,re-pair,clear}` | The sanctioned writer of `view.yaml` / `prose.md` / `provenance.yaml` for the loader's commit paths (`maker.py` remains an unmigrated direct writer — see the paragraph above). `commit_view` acquires the `view_transaction` lock and commits; `commit_view_locked` requires a caller-held `TransactionToken` and is how `commit_view` itself commits under the lock it just took — call it directly only if you already hold the transaction for another reason. Validation order is the contract, nothing touches disk until all of it passes: token identity → write/remove key whitelist (`audit.jsonl` is rejected outright, by name, from every set) → audit-entry shape (`action`, `version_id` when writing, `view_hash` when `view.yaml` is written, `destination`+`reason` for `clear`) → identity guard (`expected_identity` re-checked against on-disk state, raising `ViewChangedMidRun` on drift) → row-vs-bytes assertion (the audit row's `view_hash`/`version_id` must match the bytes actually being written) → stage-and-rename (`O_CREAT\|O_EXCL\|O_WRONLY` at `0600`, `fsync` before rename) → remove → append the audit row. Raises `CommitRejected` (nothing written), `CommitPartiallyApplied` (a rename landed and cannot be undone), or `CommitWitnessLost` (artifacts committed but the audit row failed to append — recover by hand-appending the row, not by re-running the commit). The CLI reads a JSON plan from stdin so a driving skill can invoke the whole commit in one process instead of open-coding staging itself. A plan supplies each artifact as `{"inline": ...}` or `{"path": ...}`; the path form is contained, not trusted — it is read only when it resolves to a file directly inside the directory named by `--staging-dir`, compared after `resolve()` so a `..` traversal or an out-of-directory symlink is rejected rather than followed, refused before the open, and refused outright when no staging directory was declared. The staging directory may not be, contain, or sit inside the view directory. The plan is composed downstream of an untrusted CIO document, so an injected path is realistic input and whatever it named would land in the retained record `audit_export.py` bundles. |
| `audit_export.py` | `create_bundle(view_id) -> Path` | Export a regulator-grade tarball: view + prose + provenance + full audit trail. Refuses to ship if the chain is broken. |
| `manifest_verify.py` | `verify_manifest(manifest_dict, trusted_keys_path)` | Pure function. Returns parsed dict + chain-anchor hash on valid Ed25519+JCS signature. Raises typed errors on failure: `ManifestMalformed`, `KeyIdUnknown`, `KeyIdNotYetValid`, `KeyIdExpired`, `KeyTestOnly`, `SignatureInvalid`, `ManifestSignatureMissing`. Keys marked `use: "test-only"` are default-denied; test harnesses pass `allow_test_keys=True`. |
| `manifest_cache.py` | `ManifestCache(...)`, `load_manifest(...)` | On-disk cache layer + load orchestrator. Persists verified manifests to `~/.parallax/calibration/<org_id>_<calibration_version>.json` with atomic `0600`/`0700` writes. Strict expiry boundary, monotonicity check, and dead-state guard (fresh manifest with unknown kid AND cached manifest expired raises `DeadStateNoFallback`). |
| `chain_emit.py` | `emit_chain(...)`, `emit_phase_0_chain(...)` | Reasoning chain emitter. Builds the chain envelope (spec_version, skill_version, run_id, org_id, manifest_ref, view, base_scores, final_portfolio, signature) and writes it to `~/.parallax/reasoning-chains/<YYYY-MM>/<run_id>.yaml` with atomic `0600`/`0700`. Refuses to overwrite existing run_id files unless explicitly opted in. |
| `chain_prune.py` | `parallax chain prune --before YYYY-MM-DD [--confirm]` | Retention CLI. Dry-run by default, `--confirm` to delete. Refuses symlinked chain_dir; declines files modified after process start; parses `--before` strictly. |
| `gap_detect.py` | `detect_gaps(draft_view, prose, extraction_notes, source_type) -> list[Gap]` | Identifies fillable gaps: silent (0/null AND name+aliases not mentioned in prose/notes via word-boundary regex match) or low-confidence non-zero (`extraction_confidence[dim] < 0.4`). Eligible dimensions: `macro_regime`, `factors`, `regions`, `sectors`. Pillars / themes / styles / excludes are never returned. Pure module, no I/O. |
| `gap_suggest.py` | `plan_calls(...)`, `report_skipped_leaves(...)`, `fold_responses(...)` | Pairs with `gap_detect`. Plans deduplicated MCP calls; reports per-dimension leaves silently dropped due to no MCP coverage; folds responses into Suggestions. The consuming skill makes the actual MCP calls and feeds responses back. Pure module. |
| `mcp_meta.py` | `carries_data(response) -> bool`, `shape_unreachable_reason(response) -> str \| None` | Fail-closed shape rule for whether a Parallax MCP response is interpretable at all. Absent, non-mapping, or carrying neither a `success` nor an `error` key → unusable; an explicit `success: false` is usable (the server answered). Backs both `parallax-make-house-view`'s reachability test and `stress.classify_mcp_meta_state`'s UNREACHABLE branch so the two cannot disagree about what counts as a dead market. The meta-state vocabulary itself stays in `stress.py`. |
| `view_status.py` | `compute_status(view_dir=None, today=None) -> ViewStatus`; CLI `python -m view_status [--dir PATH] [--json] [--exit-code-by-state]` | Operator-agnostic status + banner helper. Single source of truth for expiry math across operator LLMs (loader.md §2 delegates to this). Returns `state` ∈ {`none`, `malformed`, `not_yet_effective`, `expired`, `critical`, `warning`, `active`}, plus `banner` (verbatim string to surface), `days_remaining`, and `tilts_apply` (false for `none`/`malformed`/`expired`/`not_yet_effective`). Thresholds: `CRITICAL_DAYS=10`, `WARNING_DAYS=14`. Resolution order for `view_dir`: explicit arg → `$PARALLAX_HOUSE_VIEW_DIR` → `~/.parallax/active-house-view/`. |
| `gate_present.py` | `GateContext`, `GateResult`, `run_gate_loop(...)` | Extracted Step 3 confirmation gate, shared by `parallax-load-house-view` and `parallax-make-house-view`. Drives the operator disposition loop (accept / edit / reject) and renders the canonical pre-save preview. Single source of truth for gate display + disposition handling across both writer skills. |
| `provenance_classes.py` | `validate_provenance_entry(entry, mode='read'\|'write')` + 6-class registry | Enforces the canonical provenance vocabulary: `prose_extraction`, `macro_regime_rule`, `manual_edit`, `generator_synthesis`, `judge_recommendation`, `parallax_data_fill` (write-deprecated, read-accepted for backward compat). Write mode rejects deprecated classes; read mode keeps legacy entries loadable. |

### Tests

Coverage is in the adjacent `tests/` directory. The test signing key + signed test fixture + fixture generator are deliberately public so auditors can run round-trip on a fresh clone.

| Suite | Coverage |
|---|---|
| `tests/test_view_hash.py` | Reference implementation of `view_hash` computation; round-trip determinism. |
| `tests/test_audit_chain.py` | Append, hash linkage, tamper detection, race-free file open, adaptive tail read. |
| `tests/test_view_commit.py` | Full validation-order contract: key whitelist (`audit.jsonl` rejected from write/remove), audit-entry shape, identity-guard drift, row-vs-bytes mismatch, staged-and-renamed writes with `O_EXCL`/`fsync`, partial-rename vs witness-lost failure classification, `commit_view` vs `commit_view_locked` token enforcement, the `--mode` table (including the `re-pair` hyphen), the stdin-JSON CLI, and staging-directory containment for `{"path": ...}` refs (out-of-directory path, `..` traversal, out-of-directory symlink, a staging dir entangled with the view dir, and a path ref with no staging dir declared — each rejected with the audit log byte-identical and no staging file created). |
| `tests/test_audit_export.py` | Bundle creation, broken-chain refusal. |
| `tests/test_manifest_verify.py` | Round-trip + tamper coverage: valid signature, mutated values block, unknown kid, empty signature value, anti-collision guard, test-only-key default-deny. |
| `tests/test_manifest_cache.py` | Atomic-write perms, loose-perms warning, strict expiry boundary, monotonicity rollback rejection, dead-state guard, orchestrator new-version write, cache-only fallback, offline expired-cache warning. |
| `tests/test_chain_emit.py` | Envelope structure, anti-collision check, refuse-overwrite, atomic write. |
| `tests/test_gap_detect.py` | Silent-eligible, mentioned-via-prose-alias, ineligible-dimension, low-confidence non-zero, wizard-mode skip, macro_regime null tokens, word-boundary alias matching. |
| `tests/test_mcp_meta.py` | Shape rules: live `macro_analyst` envelope reads as data, explicit `success: false` / `error` is silent rather than unreachable, uninterpretable shapes fail closed. |
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
