# Changelog

All notable changes to `parallax-workflows`. Dates in YYYY-MM-DD.

> This file is the **shipping summary** — what landed and when. For the **reasoning** behind each decision (why this approach, what alternatives were rejected, when to revisit), see [DECISIONS.md](DECISIONS.md). Each shipping entry below has a corresponding decision-log entry under the same date.

## 2026-04-28

### Added
- **House View loader** (`/parallax-load-house-view`) released for external use. Ingest CIO investment views from PDF, URL, prose, or wizard. Extract structured tilts across pillars, sectors, regions, factors, and styles. Confirm with the uploader, then save to `~/.parallax/active-house-view/`.
- Per-tilt provenance: every non-neutral tilt carries a derivation record (prose extraction with source span, macro-regime rule with reference, or manual edit with prior value). `--why <tilt-path>` reconstructs the answer.
- Hash-chained audit log at `~/.parallax/active-house-view/audit.jsonl`. Each entry's `prev_entry_hash` links to the previous entry; tampering breaks the chain on next verification.
- Ed25519-signed reasoning chains written to `~/.parallax/reasoning-chains/<YYYY-MM>/<run_id>.yaml`. Designed for long-horizon replay against pinned tool versions.
- Calibration manifest verifier with on-disk cache, strict expiry, monotonicity-rollback rejection, and dead-state guard.
- `--export <view_id>` flag: produces a regulator-grade tarball (view + prose + provenance + full audit trail). Refuses to ship if the chain is broken.
- `--version-history` flag: renders the parent chain with per-version diffs.
- Six consumer skills auto-load the active view: `portfolio-builder`, `rebalance`, `thematic-screen`, `morning-brief`, `client-review`, `explain-portfolio`. Single-stock skills (`should-i-buy`, `deep-dive`) surface conflict flags but do not apply tilts.
- Sample CIO views in `skills/load-house-view/samples/` (reflationary, China-skeptic, AI-concentrated, ESG-screened, recession-defensive).
- `translate-chinese-finance` skill (zh-CN + zh-TW).

### Changed
- README restructured around the open-source release: dedicated House View section, Forking and Customizing guide, Audit & Compliance section, engineering-team audience added.
- `_parallax/house-view/README.md` rewritten as a public module reference.
- Repository-wide scrub of internal-roadmap language (Phase 0 / Phase 1 / Batch numbering) from public files.

### Security
- Audit log files (`audit.jsonl`) and provenance files (`provenance.yaml`) are written `0600` on creation; parent directories are `0700`. The `audit_chain` module re-enforces `0600` on every append as defense in depth.
- `audit_chain` now opens files race-free to prevent first-write truncation, uses adaptive tail reads to prevent large-entry chain poisoning, and warns when entries approach the tail-read ceiling.
- Calibration manifest verifier implements an anti-collision guard: emitter MUST compute both `manifest_ref.hash` and signing-payload hash and assert they differ.
- `parallax chain prune` retention CLI: dry-run default, `--confirm` required to delete, refuses symlinked chain_dir, declines files modified after process start.

## Earlier

The repo originated as a private set of Parallax MCP orchestration prompts. Earlier commits live in git history; this changelog begins with the public-facing house-view release.
