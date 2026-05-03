# Changelog

All notable changes to `parallax-workflows`. Dates in YYYY-MM-DD.

> This file is the **shipping summary** — what landed and when. For the **reasoning** behind each decision (why this approach, what alternatives were rejected, when to revisit), see [DECISIONS.md](DECISIONS.md). Each shipping entry below has a corresponding decision-log entry under the same date.

## 2026-05-03

### Added
- `/parallax-pair-finder` — long/short equity pair builder with three modes: find-short for a long thesis, find-long for a short thesis, and evaluate-pair for an existing pair. Reports residual factor, sector, macro, dollar, and beta exposure. Suggestion mode uses a single `export_peer_comparison` call to keep cross-sectional factor scores comparable across all candidates.
- HARD-HALT output gate: refuses to render hedge ratios when the benchmark price series is missing or has fewer than 60 observations. The skill emits a named failure reason and operator-action options instead of falling back to pair-relative regression with a footnote — partial sizing is treated as a confidence-building lie, not a graceful degradation.
- `skills/_parallax/coverage-matrix.md` documenting the asset-class × tool routing table, verified benchmark ETF coverage as of 2026-05-02, known API quirks (multi-symbol fail-empty, `etf_profile` as asset-class oracle), and atomic-vs-aggregation failure contracts by skill type.
- `skills/_parallax/scripts/coverage-lint.sh` — pre-commit lint that flags `export_price_series` call sites lacking an asset-class pre-classification step. Wired into `build-skills.sh`; gates merges. 32/32 skills currently pass.
- `evals/` benchmark harness (`bench.sh`, `compare.sh`, sample portfolios) for reproducible fresh-session timing of skill changes. Required because SKILL.md content is cached at session start, so on-the-fly edits cannot be honestly benchmarked in-session.

### Changed
- Asset-class hardening on three at-risk skills: `explain-portfolio`, `client-review`, and `peer-comparison` now branch on `etf_profile` before fanning out to `export_price_series`. Prevents silent attribution drops when portfolios contain ETFs (SPY, QQQ, country MSCI funds).
- `morning-brief`, `portfolio-builder`, and `scenario-analysis` SKILL.md files made the per-holding parallel-batching contract explicit. Per-holding serial loops were the dominant latency leak; the new wording instructs all N independent calls to dispatch in a single tool-call turn.
- `client-review` no longer shows `benchmark=SPY.O` as a usage example — the trailing `.O` suffix routes to the equity endpoint and silently returns empty.
- README quick-start section, DECISIONS.md index, and CONTRIBUTING.md reference-template guidance added.

### Removed
- Stale internal references in `skills/_parallax/coverage-matrix.md` (gitignored notes-path pointer, named external-tool attributions). Public copy now stands on its own; internal review context retained in (gitignored) `notes/`.



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
