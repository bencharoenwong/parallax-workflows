# Parallax House View — Shared Core

This directory holds the shared house-view infrastructure consumed by `parallax-load-house-view` (writer) and the portfolio / single-stock skills (readers).

## Files

- **`schema.yaml`** — Canonical YAML structure. Single source of truth for the view's shape, metadata, tilt vocabulary, and `view_hash` computation.
- **`loader.md`** — JIT-loaded by every consumer skill. Defines load-time validation, multiplier mapping, conflict resolution, output rendering, and audit logging.
- **`render_helpers.md`** — Canonical templates for view-aware conflict banners (single-stock skills' §7.1/§7.2/§7.3 surfaces).
- **`manifest_verify.py`** *(Batch 3 minimal slice — added 2026-04-25)* — Calibration manifest verifier. Pure function: takes a manifest dict + path to `signing/trusted_keys.json`, returns parsed dict + chain-anchor hash on valid Ed25519+JCS signature, raises typed errors on failure (`KeyIdUnknown`, `SignatureInvalid`, `ManifestSignatureMissing`, etc.). Implements anti-collision guard from chain spec §3.2 (security audit A-1).
- **`manifest_cache.py`** *(Batch 3.5 — added 2026-04-25)* — On-disk cache layer + load orchestrator. `ManifestCache` class persists verified manifests to `~/.parallax/calibration/<org_id>_<calibration_version>.json` with atomic 0600/0700 writes (security audit B-1) and emits `cache_permissions_unsafe` warnings on read if perms drift. Includes strict expiry boundary (`manifest_expires_at <= now()`, schema spec §6.2 step 5), rollback-blocking monotonicity check on `calibration_version`, and the **A-3 dead-state guard** (fresh manifest with unknown kid + cached manifest expired → `DeadStateNoFallback`, schema spec §6.2 step 2). The `load_manifest()` orchestrator composes verify + expiry + monotonicity + cache fallback. HTTP fetch + 304/ETag handling + session pinning of `version=latest` deferred until Batch 2 endpoint is live.
- **`signing/trusted_keys.json`** — Pinned Ed25519 verification keys. Trust anchor: the verifier rejects any manifest whose `signing_key_id` is not in this file. Long-horizon-replay note inside the file documents the version-pin rule (chain spec §8.2).
- **`requirements.txt`** — Exact pins for the verifier's deps (`pynacl==1.6.2`, `rfc8785==0.1.4`). Per chain spec §5 + security audit A-7, the lockfile MUST be exact, not a range, for 7yr replay determinism.
- **`tests/test_manifest_verify.py`** — Round-trip + tamper coverage: valid signature, mutated values block, unknown kid, empty signature value, and a synthetic anti-collision-guard trip. **5/5 pass.**
- **`tests/test_manifest_cache.py`** — Cache layer coverage: round-trip, atomic-write perms, loose-perms warning, strict expiry boundary, monotonicity rollback rejection, dead-state guard, orchestrator new-version write, orchestrator cache-only fallback, offline expired-cache warning. **9/9 pass.**
- **`README.md`** — This file.

## Phase status

**Phase 0 (current):** Local filesystem storage at `~/.parallax/active-house-view/`. Single active view per machine. Internal/dogfood only.

**Phase 1:** Same shape promoted to Parallax MCP server tools (`set_house_view`, `get_active_house_view`, `clear_house_view`, `list_house_views`) backed by Supabase, keyed by `org_id`. Loader.md remains identical from the consumer's perspective; only the resolver mechanism changes.

**Phase 2:** Web upload form on chicago.global → optional self-hosted container.

## Why a shared subdir under `_parallax/`?

Mirrors the `AI-profiles/` pattern: a family of related files (schema + loader + README) lives together rather than scattered. Skills JIT-load specific files within the dir; the dir itself is never loaded as a unit.

## Reference

Full design rationale, adversarial review findings, and resolution decisions are in the design doc: `~/.claude/plans/logical-scribbling-kay.md` (working copy) — promote to repo `docs/` once Phase 0 stabilizes.
