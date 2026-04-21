# Parallax House View — Shared Core

This directory holds the shared house-view infrastructure consumed by `parallax-load-house-view` (writer) and the portfolio / single-stock skills (readers).

## Files

- **`schema.yaml`** — Canonical YAML structure. Single source of truth for the view's shape, metadata, tilt vocabulary, and `view_hash` computation.
- **`loader.md`** — JIT-loaded by every consumer skill. Defines load-time validation, multiplier mapping, conflict resolution, output rendering, and audit logging.
- **`README.md`** — This file.

## Phase status

**Phase 0 (current):** Local filesystem storage at `~/.parallax/active-house-view/`. Single active view per machine. Internal/dogfood only.

**Phase 1:** Same shape promoted to Parallax MCP server tools (`set_house_view`, `get_active_house_view`, `clear_house_view`, `list_house_views`) backed by Supabase, keyed by `org_id`. Loader.md remains identical from the consumer's perspective; only the resolver mechanism changes.

**Phase 2:** Web upload form on chicago.global → optional self-hosted container.

## Why a shared subdir under `_parallax/`?

Mirrors the `AI-profiles/` pattern: a family of related files (schema + loader + README) lives together rather than scattered. Skills JIT-load specific files within the dir; the dir itself is never loaded as a unit.

## Reference

Full design rationale, adversarial review findings, and resolution decisions are in the design doc: `~/.claude/plans/logical-scribbling-kay.md` (working copy) — promote to repo `docs/` once Phase 0 stabilizes.
