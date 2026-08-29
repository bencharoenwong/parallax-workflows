# Codex Review Plan: RM Brand Ingestion and Processing

## Planning status

This file is the mandatory planning handoff for `codex-review`.

No implementation, test, dependency, configuration, branch, or git-history change is authorized yet.

## Scope and assumptions

Repository: `/Users/bencharoenwong/parallax-workflows`

Current branch at inspection: `main`, tracking `origin/main`.

Dirty-worktree state before this planbook: clean.

The planbook itself is the only intended planning-phase change.

Scope assumption: “RM support related to brand ingesting and processing” means these paths:

- `skills/parallax-white-label-onboard/`
- `skills/_parallax/white-label/`
- RM-facing brand consumers in `skills/parallax-client-review/`
- RM-facing brand consumers in `skills/parallax-desk-call-list/`
- Generated plugin copies only as build outputs after source changes

The review covers brand input routing, folder classification, extraction, merging, validation, confirmation, persistence, loading, and RM-facing consumption.

The review includes the v1-to-v2 schema bridge and DESIGN.md generation.

The review includes URL and logo-download security boundaries.

### Explicit non-goals

- House-view scoring, calibration, attribution, and portfolio multipliers
- General financial logic in client-review or desk-call-list
- New white-label features or a new workflow
- Live Parallax MCP calls
- Live client collateral or client-identifying fixtures
- Uncontrolled website calls
- Network-enabled `npx` execution during the default sweep
- Translation-skill brand wiring from GitHub issue 79
- Changes to audit-chain semantics without a prior issue and security review
- Commits, pushes, pull requests, or GitHub mutations

GitHub issue 79 remains open. Its hardcoded white-label path defect is already fixed on current `main`.

The issue's house-view and attribution items are outside this review.

## Repository and governance evidence

The repository is public. Tests must use synthetic brand names and synthetic documents.

`CONTRIBUTING.md` requires one concern per pull request.

The generated `plugin/` tree must never receive hand edits.

Changes to general-release source files require a plugin bundle rebuild.

CI uses Python 3.13 on Ubuntu.

CI runs each test root in a separate pytest process.

The local gate auto-discovers top-level test roots.

The default local gate excludes tests marked `npx`.

The current CI coverage step is informational.

No enforced percentage threshold was discovered.

## Public behavior and invariants

1. Every input resolves to one supported mode or fails with a clear error.
2. Folder input is inventoried and classified before extraction.
3. Compliance material never enters the voice corpus by default.
4. Voice-only material never supplies visual tokens.
5. Ambiguous material requires an operator disposition.
6. Multi-source visual disagreements remain visible until operator resolution.
7. Merge output does not depend silently on input ordering.
8. Voice corpus text and reported word counts describe the same bounded content.
9. URL, redirect, stylesheet, and logo destinations stay on public HTTP(S) addresses.
10. Reads, archive expansion, subprocesses, and output sizes remain bounded.
11. Invalid or partial input degrades explicitly and preserves usable fields.
12. No active branding file changes before explicit confirmation.
13. A failed save leaves the prior active configuration intact.
14. Saved files and directories use the documented permissions.
15. Config, DESIGN.md, assets, and audit evidence describe one committed state.
16. v1 and v2 configurations load into stable public result shapes.
17. Visual RM consumers cannot access voice data.
18. Missing or corrupt branding never blocks an RM workflow.
19. Displayed source references never expose credentials, query values, or local paths.
20. Source files and generated plugin copies remain identical after a rebuild.

## Current test posture

The white-label suite has strong unit coverage for these areas:

- Color, font, logo, and voice validators
- URL destination checks, redirect checks, DNS pinning, and bounded asset downloads
- PPTX and DOCX theme extraction
- v1 and v2 loader normalization
- Visual-loader voice exclusion
- DESIGN.md emission
- Consumer sentinel and disclosure references

The main weak tests require focused inspection during implementation:

- `test_integration_full_workflow_happy_path` writes config directly.
- `test_integration_user_rejects_and_retries` overwrites config directly.
- `TestFolderModeIntegration` reproduces the documented F-4 algorithm inside the test.
- Those tests do not invoke a callable onboarding transaction.
- The semantic F-1 through F-3 folder path has no deterministic executable seam.
- The documented text helper is undefined and permits either BeautifulSoup or regex behavior.
- Multi-source corpus merging does not currently prove the 3,000-word bound.
- Persistence behavior lives mainly in SKILL.md code blocks.
- Client-review and desk-call-list brand use is mainly a structural prose contract.

These tests will not be deleted during the first pass.

They will be retained until replacement tests prove the same contracts with stronger evidence.

## Invariant-led risk matrix

| Risk class | High-risk cases | Invariant | Planned control |
| --- | --- | --- | --- |
| Inputs | Missing path, unsupported extension, empty folder, corrupt ZIP, malformed XML, invalid YAML, non-string URL | Clear typed or structured degradation | Synthetic files and table-driven cases |
| Inputs | HTML, EML, RTF, transcript, compliance, and ambiguous files | Classification controls visual and voice use | Deterministic classification records and operator-choice fake |
| Boundaries | 0, 1, and 2 sources | Single-source identity and multi-source provenance remain correct | Fixed drafts with exact assertions |
| Boundaries | 499, 500, 1,999, 2,000, 3,000, and 3,001 corpus words | Voice gates and stored counts match retained text | Generated word sequences with independent recount |
| Boundaries | PDF page 5, page 10, and page 11 | One documented page limit governs behavior | Fake PDF reader with page-access recording |
| Boundaries | Maximum HTML, stylesheet, asset, and OOXML member sizes | Processing stays bounded | In-memory bounded payloads; no large disk corpus |
| State | First save, update, edit, reject, re-extract, clear, regenerate | Only confirmed states become active | Temporary branding home and scripted dispositions |
| State | Corrupt active config and stale DESIGN.md | Prior state remains recoverable | Fault injection around each write boundary |
| State | v1, v2, and hybrid config | Stable loader shape; hybrid fails closed | Existing fixtures plus mutation cases |
| Concurrency | Two simultaneous confirmed saves | One complete state wins; files never mix | Barrier-controlled threads or processes |
| Concurrency | Save racing with status or clear | Readers see old or new complete state | Synchronization barriers; no sleeps |
| Resources | ZIP compression bomb, deep XML, huge corpus, many folder files | Bounded CPU, memory, and file count | Small compressed fixtures with declared caps |
| Resources | Slow linter or downloader | Timeout and cleanup hold | Fake subprocess and fake response objects |
| Integration | Extract to merge to validate to confirm to save to load | One callable path owns the workflow | Temporary-home end-to-end test |
| Integration | Brand loader to RM consumer | Brand errors preserve RM output | Consumer contract fixture and degraded loader fake |
| Integration | Source to plugin bundle | Generated copies match source | Existing bundle drift gate after rebuild |

## Proposed tests

Each test below protects a distinct failure mode.

| ID | Behavior | Unique failure mode | Fixture and control | Expected assertion | Why it is not redundant |
| --- | --- | --- | --- | --- | --- |
| T1 | Mixed folder classification drives extraction | Compliance prose enters voice or Office defaults overwrite brand tokens | Synthetic PPTX, DOCX, compliance TXT, transcript, logo, and skipped CSV | Each file follows its confirmed role; only allowed text and visuals survive | Existing folder test starts after classification and copies F-4 logic |
| T2 | Ambiguous file blocks continuation | Workflow silently guesses a file role | Fake classifier returns `ambiguous`; fake operator gives no answer | No extractor or writer call occurs | No current test pins the F-3 stop condition |
| T3 | Voice-only folder creates valid partial draft | Visual defaults leak from voice-only OOXML | One DOCX classified as voice-only | Empty visual maps; `source.type` is `folder-voice-only`; voice text survives | Existing folder test treats OOXML files as branded |
| T4 | Multi-source corpus cap is exact | Text truncates while `word_count` reports discarded words | Two fixed corpora totaling 3,001 words | Retained text has 3,000 words; reported count is 3,000; truncation is true | Existing merge test asserts an unbounded sum |
| T5 | Multi-source disagreement requires resolution | Higher confidence silently selects a disputed brand value | Two equal-valid drafts with conflicting primary colors | Save is refused until a source-attributed choice exists | Existing cross-validation test stops before persistence |
| T6 | Merge provenance is stable across input order | Source order changes selected values or audit provenance | Reverse the same drafts under a fixed resolution map | Resolved config and canonical hash match | Existing tests run one ordering only |
| T7 | Malformed and oversized OOXML degrade safely | Unbounded ZIP/XML read or uncaught parser error | Corrupt ZIP, missing theme, malformed XML, capped compressed member | Structured error or partial draft; no unbounded read | Existing tests cover missing files and valid OOXML |
| T8 | One PDF page limit governs code and instructions | Brand tokens after page 5 disappear despite a documented 10-page promise | Fake reader records page access and places a token at boundary pages | Access matches the settled limit; docs and code agree | Existing tests do not inspect page boundaries |
| T9 | Confirmation transaction is atomic | Config updates while DESIGN.md or audit append fails | Temporary branding root; injected failures after each staged artifact | Old live state remains complete; staging residue is removed | Current integration tests write live files directly |
| T10 | Reject and re-extract never activate a draft | Rejected extraction overwrites active branding | Scripted disposition sequence and prior active config | Active bytes remain unchanged; extraction audit records the outcome | Existing retry test first writes the rejected config live |
| T11 | Concurrent saves cannot mix artifacts | Config from one save pairs with DESIGN.md from another | Two barrier-controlled writers with distinct hashes | Final files share one transaction identity; audit chain verifies | No white-label save-concurrency test exists |
| T12 | Source display stays secret-free through RM output | Query values, credentials, or local paths reach client-facing text | URL and local-path source fixtures; RM rendering fake | Output uses only the safe source reference | Loader redaction exists; RM propagation is not proved end-to-end |
| T13 | RM visual consumers remain voice-isolated | Client-review or desk-call-list reads `voice` accidentally | Visual-loader proxy that raises on excluded keys | RM output completes without voice access | Current subset test checks loader keys, not RM consumption |
| T14 | RM workflows degrade when branding is corrupt | Branding failure aborts an otherwise valid client workflow | Valid RM input plus corrupt YAML branding fake | Default branding renders; workflow result remains available | Existing loader degradation tests stop before RM output |
| T15 | Package-mode imports work outside test CWD | Hyphenated sibling imports pass only because tests modify `sys.path` | Fresh subprocess import from a temporary working directory | Public white-label modules import and execute a smoke path | One emitter regression exists; the package surface is broader |
| T16 | Linter cleanup survives timeout and unlink failure | Temporary DESIGN.md files leak | Fake subprocess timeout and controlled temporary directory | Timeout is structured; all removable temp files disappear | Existing timeout test does not verify directory residue independently |

## Red-before-green requirement

Each accepted defect needs an independent failing test before its fix.

The failure must exercise repository code.

The test must not reproduce the proposed implementation inline.

For T4, the independent oracle is `len(result["text"].split())`.

For T9 and T11, the independent oracle reads every live artifact after fault injection.

For T12, the independent oracle scans rendered output for source secrets.

## Planned verification order

No command below runs until implementation authorization.

1. Run the smallest new regression test with cache disabled.

   ```bash
   /usr/local/bin/python3 -m pytest /Users/bencharoenwong/parallax-workflows/skills/_parallax/white-label/tests/<target_test.py> -q -p no:cacheprovider
   ```

2. Run the full white-label root offline.

   ```bash
   /usr/local/bin/python3 -m pytest /Users/bencharoenwong/parallax-workflows/skills/_parallax/white-label/tests -q -p no:cacheprovider -m "not npx"
   ```

3. Run the two RM-facing roots in separate processes.

   ```bash
   /usr/local/bin/python3 -m pytest /Users/bencharoenwong/parallax-workflows/skills/parallax-desk-call-list/tests -q -p no:cacheprovider
   ```

   Client-review has no Python test root. Its contract is covered by white-label structural tests.

4. Run the shared render and bundle gates.

   ```bash
   /usr/local/bin/python3 -m pytest /Users/bencharoenwong/parallax-workflows/skills/_parallax/test_render_gate.py -q -p no:cacheprovider
   ```

   ```bash
   /usr/local/bin/python3 -m pytest /Users/bencharoenwong/parallax-workflows/skills/_parallax/scripts -q -p no:cacheprovider
   ```

5. Rebuild the plugin only if a general-release source changes.

   ```bash
   /usr/local/bin/python3 /Users/bencharoenwong/parallax-workflows/skills/_parallax/scripts/build_bundle.py plugin
   ```

6. Run the full offline gate from the repository root.

   ```bash
   /bin/bash /Users/bencharoenwong/parallax-workflows/skills/_parallax/scripts/run-gate-tests.sh
   ```

7. Run the tracked-term scan before any public commit or push request.

   ```bash
   /usr/local/bin/python3 /Users/bencharoenwong/parallax-workflows/skills/_parallax/scripts/scan_tracked_terms.py
   ```

8. Perform a fresh Claude Code session test for SKILL.md behavior.

Codex cannot claim this step passed without a real Claude Code invocation.

## Execution risks and safe caps

- Use only synthetic documents and synthetic brand names.
- Use `tmp_path` for all brand state.
- Patch home and config paths before any persistence test.
- Keep every corpus fixture at or below 3,001 words.
- Keep folder fixtures below 20 files.
- Keep decompressed OOXML test content below 2 MiB.
- Set any proposed production OOXML member cap explicitly before testing it.
- Use barriers for concurrency tests.
- Do not use sleeps.
- Limit concurrency tests to two writers and ten repeated runs.
- Keep each focused test timeout below 10 seconds.
- Keep the full offline gate free of network and MCP calls.
- Continue to deselect `npx` by default.
- Use fake URL responses and fake DNS results.
- Verify temporary files and staging directories after every failure case.
- Run test roots separately to avoid conftest collisions.

## Proposed change list

Changes remain contingent on failing evidence.

1. Add regression tests under `skills/_parallax/white-label/tests/`.
2. Replace copied workflow simulations with calls into repository code.
3. Add the smallest callable orchestration seam needed for folder processing.
4. Add the smallest callable transaction seam needed for confirmed saves.
5. Fix only defects exposed by the new tests.
6. Update SKILL.md and references when executable behavior settles a contradiction.
7. Update RM consumer contract tests only where propagation is unproved.
8. Rebuild `plugin/` from source when required.
9. Preserve unrelated files and existing tests.

Likely production files include:

- `skills/_parallax/white-label/extract/merge.py`
- `skills/_parallax/white-label/extract/ooxml.py`
- `skills/_parallax/white-label/loader.py`
- A narrowly scoped new white-label orchestration module, if tests require it
- `skills/parallax-white-label-onboard/SKILL.md`
- Relevant files under `skills/parallax-white-label-onboard/references/`

## Test consolidation policy

No test will be removed because it is old or broad.

After stronger tests pass, inspect these simulations for consolidation:

- `test_integration_full_workflow_happy_path`
- `test_integration_user_rejects_and_retries`
- `TestFolderModeIntegration.test_mixed_folder_extracts_and_merges`

Retain any test that still provides distinct diagnostics.

Remove copied-algorithm tests only when a repository-code test proves the same behavior.

## Branch and rollback proposal

Proposed branch: `review/rm-brand-ingest-hardening`

Branch creation requires explicit approval.

The branch should start from the current `main` commit.

Rollback uses ordinary file-level reverts on the dedicated branch.

No reset, force-push, or destructive workspace command is planned.

Generated plugin changes can be regenerated from the source tree.

Temporary test artifacts remain under pytest temporary directories.

## Authorization gate

Implementation requires explicit user authorization.

Authorization must separately state whether branch creation is approved.
