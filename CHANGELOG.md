# Changelog

All notable changes to `parallax-workflows`. Dates in YYYY-MM-DD.

> This file is the **shipping summary** — what landed and when. For the **reasoning** behind each decision (why this approach, what alternatives were rejected, when to revisit), see [DECISIONS.md](DECISIONS.md). Each shipping entry below has a corresponding decision-log entry under the same date.

## 2026-06-10

### Fixed
- **`analyze_portfolio` call shape corrected** across `parallax-client-review`, `parallax-rebalance`, and `parallax-scenario-analysis` — skills were passing `holdings=[...]` / `lens="..."` parameters that do not exist in the MCP schema. Corrected to `portfolio=[{date, symbol, weight}]` + `fields=[...]` (the documented schema). Skills were silently no-oping on every portfolio analysis call.
- **`parallax-cio-letter-prep` stale paths** — Batch B JIT-load directives and test imports referenced `skills/cio-letter-prep/` (pre-rename path). Updated to `skills/parallax-cio-letter-prep/` throughout.
- **`parallax-cio-letter-prep` retrospective window formula** — the `days` argument passed to `export_price_series` used `period_days` directly, producing an incorrect series window for retrospective periods. Fixed to `(today - period_start).days + 5` (capped at 365) so the series span is anchored to the period start date relative to today.
- **`analyze_portfolio` contract schema extended** — `contract_schemas.py` now covers the seven additional response fields consumed by `cio-letter-prep` Batch B: `company_contribution`, `portfolio_summary`, `drawdown_analysis`, `performance_metrics`, `latest_holdings`, `sector_allocation`, `time_period_returns`. Mock updated to match.

### Added
- **`/parallax-make-house-view --compare <a> <b>`** — neutral view-level diff of two saved house-view bundles (bundle dir or bare `view.yaml`), e.g. two different ingested firm views. Renders per-cell tilt divergence plus an excludes diff with symmetric left/right naming; reuses the existing `diff_views` core unchanged and needs no Parallax connection at runtime (pure local file diff). 22 new tests + a second fixture view. Also fixes the SKILL.md routing note that mis-pointed per-cell view diffs at `/parallax-house-view-diff` (that skill compares portfolio *outputs* under a view, not views themselves).

---

## 2026-06-07

### Added
- **`build-skills.sh --normalize`** — folds client-convention frontmatter (`user-invocable`, `argument-hint`, `negative-triggers`) into agentskills.io spec-clean form via the new idempotent `_parallax/scripts/spec-normalize.py` (negative-trigger items move into a `## When not to use` body section; nothing silently dropped; spec-clean files left byte-identical; 7 tests). The build flag loop also gains `--no-lint`, and spec-validate failures now print an actionable hint pointing at `--normalize`.
- **agentskills.io spec validator in the build** (PR #35) — new `_parallax/scripts/spec-validate.py` checks every skill's frontmatter against the spec (allowed keys, name format and directory match, description/compatibility length, metadata shape); wired into `build-skills.sh` ahead of coverage-lint and fails the build on any violation.

### Changed
- **Skill directories renamed to match frontmatter names** (PR #35) — the spec requires the skill name to equal its parent directory name; repo dirs were short aliases (`AI-buffett`, `should-i-buy`) registered under prefixed symlinks. Now the directory IS the skill name (`parallax-ai-buffett`, `parallax-should-i-buy`), so a clone of this repo is a valid skills collection as-is. `install.sh` and `check-registration.sh` drop the prefixing logic; build lint, eval configs, cross-skill references, and docs updated to the new paths.

### Fixed
- **Frontmatter YAML repaired across 10 skills** (PR #35) — frontmatter now carries only spec keys; house-convention `negative-triggers`/`gotchas` content moved verbatim into `## When not to use` / `## Gotchas` body sections. Previously the YAML was unparseable in 10 skills (markdown prose inside YAML lists) and body fragments surfaced as live skill descriptions. `coverage-lint.sh` now forbids the old top-level keys and requires the body sections.

---

## 2026-06-04

### Added
- **Two build guards that make registration drift visible** (PR #33): a JIT-load directive lint in `build-skills.sh` (hard-fails on dangling `references/` paths; resolves both local and cross-skill forms) and `check-registration.sh` (flags registered skills that have drifted from a symlink into a diverging copy).

### Fixed
- **AI-profile slug casing normalized to lowercase `parallax-ai-*`** across the 6 AI-* skills, concierge routing, thematic-screen, and shared references (PR #33) — frontmatter names now match the registered/invocable slugs; previously 6 concierge routes dispatched to nothing. README follow-up in PR #34: lowercase slugs in the AI-profile table, missing `parallax-ai-ptj` row added, consensus meta-skill corrected to "all 5 profiles".
- **Stale citations and count drift batch** (PR #33): conventions §0.1→§0.2 references, due-diligence `applied_reason` citation, client-review + peer-comparison cross-skill paths, scenario-analysis step→phase wording, AI-consensus profile count 4→5, morning-brief now surfaces the 5th health flag (macro misalignment), translate-thai validator catches no-space doubled-word forms it previously missed, credit-lens reference renderer marked test-only.

---

## 2026-05-31

### Added
- **v2 eval substrate under `evals/`** — a two-tier quality-eval harness (deterministic Tier-1 structural checks + pinned-Anthropic Tier-2 rubric judge) on a spec-driven, skill-agnostic grading engine. New `evals/graders/` (engine + CI-safe pure-function tests), `evals/skills/<skill>/eval_config.py` (per-skill `EvalSpec`), `evals/tasks/<skill>/core.jsonl` (task inputs), and `evals/fixtures/<skill>/` (golden + broken stream-json transcripts for offline tests). Skills covered: `should-i-buy` (reference baseline), `AI-buffett` (different output family), and `portfolio-checkup` (DRAFT spec only, never run). CI runs only `cd evals && python3 -m pytest graders -q` — never a live rollout. `evals/README.md` and `CONTRIBUTING.md` updated. Design doc is local-only (`notes/`, gitignored).
- **`docs/security/audit-2026-06-01.md`** — refreshed pre-launch security audit covering the eval substrate (`CRITICAL_FAILS=0`); `audit-latest.md` symlink repointed. Consumed by the pre-push security gate.

### Changed
- **`/parallax-should-i-buy` two-lens upgrade** — output now splits into a **Fundamentals** lens (Scores + House View Note + Financial Health) and a distinct **Technicals** lens fed by a new parallel `get_technical_analysis` call (trend direction, momentum, support/resistance). The Technicals read cites price/trend/momentum only; on tool timeout it falls back to the Momentum-factor proxy and never silently disappears. Bottom Line now states each lens's directional read and names any Fundamentals↔Technicals divergence instead of blending it. Token budget rises ~24 → ~29 (`+5` for technicals); see `skills/_parallax/token-costs.md`.

### Fixed
- **`AI-buffett` BKP-2018 momentum mischaracterization** — the profile, output template, and SKILL example previously described "slight negative Momentum" as a documented Buffett factor loading. Corrected across `skills/_parallax/AI-profiles/profiles/buffett.md`, `output-template.md`, and `skills/AI-buffett/SKILL.md`: BKP-2018 document no meaningful momentum tilt; the `<=6` Momentum criterion is a *design screen* against momentum-chasing names, not a paper-documented loading.
- **`AI-buffett` output discipline** — Steps 1–6 are now explicitly silent (entire visible response is the rendered template, first character to last; no `**Step N**` labels or narration leak), and a **Synthesis** section is now REQUIRED for every verdict including `match` (a bare table is no longer acceptable).

---

## 2026-05-25

### Added
- **§9.2 AI-interaction disclosure** wired into 10 previously-unwired analysis skills (`watchlist-monitor`, `score-explainer`, `earnings-quality`, `AI-buffett`, `AI-soros`, `AI-klarman`, `AI-greenblatt`, `AI-consensus`, `credit-lens`, `halal-screen`) plus `AI-ptj`. Closes the follow-up flagged under the 2026-05-18 DECISIONS entry; all 11 now reference `parallax-conventions.md §9.2` immediately above the standard disclaimer.
- **`docs/security/audit-2026-05-25.md`** — pre-launch security audit baseline (machine-greppable SUMMARY line) consumed by the pre-push security gate.
- **`/parallax-judge-house-view --mock-mcp <path>`** — new orthogonal flag documented in README and `skills/judge-house-view/SKILL.md`; replaces live MCP fan-out with a canned JSON payload (CI / testing). Combinable with `--dry`.
- **`/parallax-thematic-screen` trade-idea generation** — Phase A now fires `list_macro_countries` + `macro_analyst` (× up to 3 inferred markets, `component="tactical"`) + `get_telemetry` alongside universe build. New "Macro Context" output section renders per-market tactical takeaways and a basket-level Regime Signal sub-line; Top Picks gain a "Macro Tag" column (`with-regime` / `against-regime` / `orthogonal`) computed from `get_company_info.country` against `macro_context`. Top Picks rank stays composite-driven — Macro Tag is a read-only annotation, never a filter or sort. New `--no-macro` flag reverts to the prior universe-only path. Telemetry failure is safe-skip (no `--no-telemetry` flag exposed). AI-soros gains a negative-trigger entry pointing regime-first/reflexivity invocations there instead. Token budget shifts from ~14 to ~19 (default) / ~14 (`--no-macro`); see `skills/_parallax/token-costs.md`.
- **`skills/_parallax/parallax-conventions.md §3.1` — Concurrent Annotation Pattern** — new convention codifying the rank-vs-annotation separation: annotation steps that derive from data already known at rank time MUST run concurrently with downstream rank-consumers and MUST NOT change rank order, alter membership, or be used as a filter predicate by downstream consumers. Reference implementation is `thematic-screen` Phase C1.5.
- **`skills/_parallax/skill-structure-conventions.md` — Description / Trigger Completeness** — new forward-only rule: any skill that exposes a flag or mode materially changing its output workflow (2026-05-25 onward) must include at least one natural-language trigger phrase for that mode in the frontmatter `description`. Backlog of 10+ existing skills lacking trigger phrases is accepted debt with no scheduled cleanup. Enforcement is author discipline + PR review until `build-skills.sh` grows a lint.
- **`skills/_parallax/scripts/mcp_mocks/check_portfolio_redundancy_silent_fail.json`** — new failure-mode mock fixture that models the documented empty-payload silent-failure on sector-concentrated portfolios. Pairs with the happy-path mock for skills with sanity-check gates against this mode (`portfolio-builder` Step 4 + Step 6 fallback, `halal-screen` Step 2). `analyze_portfolio.json` flagged in the README table as **minimal** — full response includes additional fields (rolling metrics, drawdown analysis, contribution attribution, performance time series) referenced by `portfolio-builder` Step 6 but not yet captured in the mock.

### Changed
- **`/parallax-judge-house-view --dry`** decoupled from MCP mocking. `--dry` now only suppresses the Phase 5 LLM recommendation step and returns deterministic drift severity from MCP signals; mock injection is `--mock-mcp <path>`. README §"House View" table and `skills/judge-house-view/SKILL.md` Phase 1 prose updated to match.
- **`CLAUDE.md`** now carries `**Project Type:** MCP` and `**Security Gate:** required` markers so the pre-push hook treats this repo as production-scope rather than mis-classifying it as academic from the presence of `notes/HANDOFF.md`.
- **`skills/portfolio-builder/SKILL.md`** Phase B gains a REQUIRED empty-universe gate ahead of Steps 3-6: if Step 1 sets `universe_status = "unavailable"`, the skill skips redundancy/analyze/quick-scores entirely (those tools require holdings input). Step 6 fallback path now mirrors Step 4's `check_portfolio_redundancy` sanity-check, documents the symbol-mapping caveat for `quick_portfolio_scores` (per parallax-conventions.md §2), and discloses the scope of what the fallback does NOT cover (rolling metrics, drawdown analysis, contribution attribution, performance time series — flagged "unavailable in fallback path"). Frontmatter `description` gains the `--augment-silent` trigger phrase ("fill house view gaps from Parallax data for this portfolio") per the new Trigger Completeness rule.
- **`skills/halal-screen/SKILL.md`** Step 2 portfolio screening — `check_portfolio_redundancy` sanity-check is now gated on N≥8 compliant holdings. For N<8 the sanity-check is skipped because small concentrated halal subsets are an expected screening outcome, not a tool defect; the entry explains the residual-sector reasoning for the N=8 cutoff and the flip condition for re-tuning.
- **`skills/AI-soros/SKILL.md`** frontmatter `description` gains regime/reflexivity trigger phrases (per the new Trigger Completeness rule) so basket-mode invocations don't silently miss the matcher. New gotcha documents that ticker-to-basket resolution in single-ticker mode (Channel B) is best-effort via name-match against `divergences[*].basket_name` — per-ticker basket lookup is not a schema-documented field.
- **Partner-visible vocabulary scrub** across spec docs and human-readable display strings. The four house-view pillars (`econometrics_phase`, `valuation_state`, `market_entropy`, `psychological_wavelength`) are now framed in neutral finance terms (macro backdrop / valuation / market state / sentiment) wherever they appear in prose, comments, gate display strings, or skill-spec descriptions. Files touched: `_parallax/house-view/schema.yaml`, `_parallax/house-view/loader.md`, `_parallax/house-view/gate_present.py` (display strings only), `load-house-view/SKILL.md`, `make-house-view/SKILL.md`, `thematic-screen/SKILL.md`, plus residual prose in `_parallax/house-view/stress-test-design.md`, `_parallax/house-view/MCP_FIELD_INVENTORY.md`, and `stress-house-view/internal_rules.yaml`. The white-label-onboard README no longer asserts attribution to upstream infrastructure on the partner-facing side. Field identifiers (schema keys, Python attribute / function / class / variable names, audit-row keys, rule IDs referenced from tests) are preserved unchanged for data-contract stability. See DECISIONS.md for scope rationale and the going-forward hygiene rule on sensitive cleanups.

### Fixed
- **`judge.schema_key`** switched to the canonical `MARKET_TO_SCHEMA_KEY` map (single source of truth) and 3 LOW gate-review findings on that change cleared.
- **`portfolio-builder` Step 1 timeout fallback** — previously instructed the skill to "use `check_portfolio_redundancy` placeholder and flag output", which would fail or return nonsense (the tool requires a `holdings` parameter that does not exist in this branch). Replaced with the explicit empty-universe abort flow.

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
