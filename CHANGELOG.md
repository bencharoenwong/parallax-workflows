# Changelog

All notable changes to `parallax-workflows`. Dates in YYYY-MM-DD.

> This file is the **shipping summary** — what landed and when. For the **reasoning** behind each decision (why this approach, what alternatives were rejected, when to revisit), see [DECISIONS.md](DECISIONS.md). Each shipping entry below has a corresponding decision-log entry under the same date.

## 2026-05-25

### Added
- **§9.2 AI-interaction disclosure** wired into 10 previously-unwired analysis skills (`watchlist-monitor`, `score-explainer`, `earnings-quality`, `AI-buffett`, `AI-soros`, `AI-klarman`, `AI-greenblatt`, `AI-consensus`, `credit-lens`, `halal-screen`) plus `AI-ptj`. Closes the follow-up flagged under the 2026-05-18 DECISIONS entry; all 11 now reference `parallax-conventions.md §9.2` immediately above the standard disclaimer.
- **`docs/security/audit-2026-05-25.md`** — pre-launch security audit baseline (machine-greppable SUMMARY line) consumed by the pre-push security gate.
- **`/parallax-judge-house-view --mock-mcp <path>`** — new orthogonal flag documented in README and `skills/judge-house-view/SKILL.md`; replaces live MCP fan-out with a canned JSON payload (CI / testing). Combinable with `--dry`.

### Changed
- **`/parallax-judge-house-view --dry`** decoupled from MCP mocking. `--dry` now only suppresses the Phase 5 LLM recommendation step and returns deterministic drift severity from MCP signals; mock injection is `--mock-mcp <path>`. README §"House View" table and `skills/judge-house-view/SKILL.md` Phase 1 prose updated to match.
- **`CLAUDE.md`** now carries `**Project Type:** MCP` and `**Security Gate:** required` markers so the pre-push hook treats this repo as production-scope rather than mis-classifying it as academic from the presence of `notes/HANDOFF.md`.

### Fixed
- **`judge.schema_key`** switched to the canonical `MARKET_TO_SCHEMA_KEY` map (single source of truth) and 3 LOW gate-review findings on that change cleared.

---

## 2026-05-24

### Added
- **`/parallax-make-house-view`** — new skill that synthesizes a draft house view from Parallax MCP signals (`macro_analyst` × 14 markets × 5 components + `get_telemetry`). Routes through the shared confirmation gate, saves through `/parallax-load-house-view`'s Step 4 path with `generator_synthesis` provenance class. Includes `--shadow-diff` flag (synthesize-but-don't-save; renders an additive diff against the active bank view), `--markets` scope restrictor, and `--basis` hint flag. 8 modules + 55 unit tests.
- **`/parallax-judge-house-view`** — new read-only skill: LLM-as-judge that compares the saved view against current Parallax signals, classifies drift severity (minor/moderate/material), emits structured per-cell recommendations with a citation validator that drops hallucinated rationales. Writes a self-contained report bundle (`report.md`, `report.json`, `mcp_responses.jsonl`, `audit_entry.json`) + appends single `action="judge"` audit row (`applied=false` always) + emits reasoning chain. 7 modules + 46 unit tests.
- **Shared infra**: `skills/_parallax/house-view/gate_present.py` (`GateContext` / `GateResult` / `run_gate_loop` extracted from `load-house-view` Step 3 for reuse by maker), `provenance_classes.py` (6-class registry + `validate_provenance_entry(mode="read"|"write")` with `parallax_data_fill` deprecation enforcement), `aggregator_weights.yaml` (v0 MSCI ACWI shares aligned to the 14 MCP-covered markets, sum 1.0), `auto-on-load-judge-pattern.md` (single source of truth for the consumer-skill drift-gate protocol), `MCP_FIELD_INVENTORY.md` (Phase A0 capability validation artifact).
- **Consumer integration**: `portfolio-builder`, `rebalance`, `thematic-screen` JIT-load the auto-on-load pattern (fires when view_age > 30d; banner only on `drift_material`). `morning-brief` gets a conditional one-liner suggesting the judge when its existing Batch B alignment check detects ≥3 misaligned holdings.
- **`loader.md §6.1/§6.2`** extended: `action` enum gains `generate` (maker save) and `judge` (judge run) with full conditional field tables. `schema.yaml` gets a structured `classification_taxonomy:` section enumerating all 6 provenance classes.
- **`stress.build_recommended_deltas`** gains `include_fresh: bool = False` parameter (default preserves existing behavior; judge passes True to also emit `DIVERGENT_FRESH` cells with `kind="informational_fresh"`); `validate_recommended_deltas` allowlist extended accordingly.
- **24 new E2E tests** across `test_e2e.py` (8 happy-path + failure-mode), `test_e2e_versioning.py` (3), `test_e2e_calibration.py` (2 + 1 xfail-strict tripwire), `test_e2e_concurrency.py` (3), `test_e2e_multi_tenant.py` (3), `test_e2e_view_status_countdown.py` (14 parametric), `test_e2e_rm_operator_workflow.py` (3), `test_integration_make_judge.py` (3) — exercising the maker↔judge cycle, multi-version evolution, calibration phase flip simulation, concurrent runs, multi-tenant isolation, view_status countdown boundaries, and full operator lifecycle.

### Changed
- `skills/load-house-view/SKILL.md` Step 3 refactored to call into shared `gate_present.run_gate_loop`. Steps 3a (pre-edit snapshot) and 3b (extraction_attempt audit logging) retained verbatim. Backward-compat locked in by `tests/test_uninstall.py::test_disable_both_yields_structural_audit_parity`.
- Judge bundle directory naming now appends a 6-char `uuid.uuid4().hex[:6]` nonce — `{version_id}-{ts}-{nonce}` — to prevent silent overwrite when two judge runs against the same view fire within one wall-clock second (caught by `test_e2e_concurrency.py`).
- `skills/stress-house-view/stress.py:build_recommended_deltas` hardened against malformed resolution dicts (bare `r['dim']` access now guarded with `.get('dim', '')` + early-continue, surfaced by code-reviewer pass).

### Fixed
- 8 production bugs discovered during E2E development + code-review rounds — all fixed in this changeset. See [DECISIONS.md](DECISIONS.md) entry "Make + judge as paired peer skills" for the full enumeration; the most impactful were the judge `chain_emit` silent failure (PyYAML couldn't represent `MarketResponse` dataclass instances; phase_8 try/except swallowed every reasoning chain on every real run) and the judge bundle-name collision (silent overwrite of report files for two same-second runs).
- `skills/_parallax/house-view/tests/golden/generate_golden.py` REPO path no longer hardcoded to the author's `~` — uses `Path(__file__)` relative resolution so any contributor can regenerate the golden baseline.

### Deferred (with explicit decision)
- **Server-side `house_view_judge` MCP tool** — **CANCELLED**, not deferred. Judge stays client-side permanently; bank clients run the CLI on their side. Rationale: methodology transparency for model-validation review, zero cross-tenant blast radius, no cross-org auth plumbing. See DECISIONS.md.
- **Maker `calibration_status` wiring** — hardcoded to `heuristic_phase0` until the calibration manifest is signed. Tripwire `xfail(strict=True)` in `test_e2e_calibration.py` will XPASS-as-failure when the wiring lands. ~1-2h to fix; gated on the calibration manifest itself being available. See DECISIONS.md.

---

## 2026-05-17

### Added
- `skills/_parallax/white-label/integration-pattern.md` — shared §1–§9 contract that visual-rendering consumer skills JIT-load to apply branding (header, provenance line, color substitution, logo placement, fallback behavior). Single source of truth for the consumer side of the contract.
- `load_visual_branding()` in `skills/_parallax/white-label/loader.py` — public wrapper returning the 6-key visual subset (`client_name`, `colors`, `logos`, `fonts`, `source`, `error`). Structurally excludes `voice`/typography keys so a misuse raises `KeyError` instead of silently inheriting voice data.
- Branding Header + Provenance line wired into 16 consumer SKILL.md files via the `<!-- white-label: integration-pattern.md -->` sentinel: Tier 1 (`client-review`, `due-diligence`, `deep-dive`, `cio-letter-prep`) and Tier 2 (`should-i-buy`, `thematic-screen`, `portfolio-checkup`, `portfolio-builder`, `rebalance`, `morning-brief`, `explain-portfolio`, `scenario-analysis`, `country-deep-dive`, `pair-finder`, `peer-comparison`, `macro-outlook`).
- `tests/test_integration_pattern_referenced.py` — drift gate enforcing that every SKILL.md carrying the sentinel pairs it with a load directive (and vice versa). Prevents silent decoupling between consumers and the shared contract.
- `tests/test_loader.py` — loader contract gate covering `_empty_result()` / `_build_result()` shape parity (always 13 top-level keys) and `load_visual_branding()` voice-exclusion guardrail.
- `scripts/compare_docx.py` — retrofit-gate helper used to confirm the `cio-letter-prep` move from inline branding to the JIT-loaded pattern produces byte-equivalent output.
- `is_white_label_active(branding) -> bool` in `loader.py` — single source of truth for the rendering predicate. Consumer SKILL.md files (16) and `integration-pattern.md` §2/§4/§8 call this instead of re-implementing the active-flag check inline.
- `safe_source_reference(branding) -> str` in `loader.py` — display-safe Provenance source ref that collapses URLs to scheme+hostname and paths to basename. Used by `integration-pattern.md` §7 and the 16 consumer SKILL.md files.

### Changed
- `cio-letter-prep` retrofitted from inline branding instructions to consume `integration-pattern.md` JIT — eliminates duplicated branding prose across SKILL.md files.
- `_empty_result()` and `_build_result()` in `loader.py` now unconditionally return all 13 top-level keys (the four v2 token-tree bonus keys — `typography`, `rounded`, `spacing`, `components` — are populated as empty dicts on v1 and error paths). Consumers can read them with `[]` without `KeyError`.
- `loader.py` log namespace stabilized to `parallax.white_label.loader` (was a module-relative logger).

### Security
- Logo path hardening: `_resolve_logo_paths()` now enforces an extension allowlist (`_LOGO_ALLOWED_EXTS`) rejecting non-image paths (`/etc/passwd`, `id_rsa`, `.env`, etc.), resolves paths via `Path.resolve()`, and requires `is_file()` — blocks path traversal and symlink-to-secret attacks against the loader.
- PII redaction in logo warnings and log lines: raw filesystem paths no longer leak into Provenance footers or logger output; the displayable form is the basename only.
- `scripts/compare_docx.py` gained a `MAX_THEME_BYTES` zip-bomb guard so retrofit comparisons cannot be weaponized against the linter via a crafted `.docx`.

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
