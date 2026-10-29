# Security Audit — parallax-workflows

AUDIT_DATE: 2026-10-23
AUDIT_COMMIT: 8a4d5cb843891ad700cf9c1de00860857d618133
PROJECT_TYPE: MCP
THREAT_MODEL: absent

## Scope Note

This is a post-rebase revision of this audit. `feat/client-guard` was
rebased onto `origin/main` at `bda5bf4` (the merge of
`fix/port-2026-10-20-fixes` into the public release). AUDIT_COMMIT above is
the branch's current tip, `8a4d5cb`, built on that base. The branch
previously carried one commit, `020dc95`, built on the pre-rebase base
`3cce236` ("Initial public release"); `020dc95` was superseded by a
same-day squash with a follow-up fix commit and then by this rebase, and is
a pre-rebase local commit, not part of this branch's current,
pushed-reachable history. Narrative mentions of `020dc95` below describe
what the first-pass commit's code did, before the same-day fix commit was
squashed in — they are history, not an independently checkable diff
target.

The rebase had one content conflict, in `CHANGELOG.md`: both sides added a
Security bullet at the same place, and both bullets were kept. Two other
files this commit also changes picked up `bda5bf4`'s own edits through a
clean automatic merge: `CONTRIBUTING.md` (that base's DESIGN.md-lint
wording) and `test_install_git_hooks.py` (that base's change to
`test_a_usable_temp_dir_does_not_block_a_clean_scan`, which now checks only
the hook's own temp files in `TMPDIR`). Neither is a change made by this
branch. Every other file this commit adds or touches is content-identical
to the pre-rebase squashed commit.

This audit covers commit `8a4d5cb` plus the staged changes committed
alongside it: `.client-guard/allow-binary.txt` (new) and the removal of
the superseded `docs/security/audit-2026-10-22.md`. Every "unchanged
since" and "diff against" claim below is now measured against `bda5bf4`,
not `3cce236`; each was re-run this pass (see Verification). `git diff
bda5bf4 --cached --stat` shows 13 files changed at the time of this
revision. Line counts are not recorded here because this file is part of
the diff they measure.

**Cross-reference.** `docs/security/audit-latest.md` points at this file,
so this is where coverage of the client guard lives; coverage of the rest
of the rebase's new base lives in `origin/main`'s own
`docs/security/audit-2026-10-23.md` (`AUDIT_COMMIT: 4d6debf`), which
reviewed `fix/port-2026-10-20-fixes` through that commit, headlined by
replacing a package-manager network-fetch-and-execute call in an optional
lint integration with an operator-configured, checksum-verified local
executable, plus narrowing a report-footer sanitizer and a coverage
date-contract helper, and hardening an eval shell script's argument
handling. That audit found 0 Critical findings and one pre-existing,
documented, deliberately-unpinned test-dependency item carried forward
from an earlier audit, not introduced by that work; its summary line reads
`PASS_COUNT=4 FAIL_COUNT=0 NA_COUNT=8 CRITICAL_FAILS=0`. This revision
treats those findings as current and does not re-derive them. Two commits
landed on `fix/port-2026-10-20-fixes` after that audit's `4d6debf` and
before the `bda5bf4` merge: the commit that added that audit file itself,
and a four-line Python 3.9 compatibility fix to two unrelated skills'
arithmetic/string-formatting (f-string quoting, a manual correlation
computation) made during gate review. Neither is analyzed by that audit or
by this one; both are read-confirmed as mechanical, with no
security-relevant content, but not independently audited.

## Security-relevant change (re-verified this pass)

**Key-file permission-mode check.** `load_key()` rejects a key file with
`stat().st_mode & 0o077` set — i.e. any group- or world-readable permission
bit — before reading its contents, raising the same fail-closed `GuardError`
the missing-key path uses. Read directly in the source.

**Tag-to-blob/tree content scanned.** `_scan_tags` now branches when peeling a
tag reaches a blob (its bytes are scanned directly) or a tree (the existing
recursive tree scanner is invoked on it), closing a gap where an annotated tag
pointing directly at a blob or tree published that object's content with
nothing in the guard having read it. `run_ci` skips the redundant
`scan_tree(scanner, after)` call only when `after^{tree}` does not resolve (a
tag-on-blob push); a missing pushed object is never silently skipped —
`run_ci` raises `GuardError` if `after` itself does not resolve, which the
`main()` entry point maps to exit 2 (`except GuardError` handler). This is a
coverage fix, not a response to an exploited gap: read directly, no existing
tag in this repository points at a bare blob or tree.

**Pre-push layer — re-derived against the current script (second
correction).** Read directly in `install_git_hooks.sh`, replacing the prior
same-day revision's description of this logic where it no longer matches the
current working-tree file:

- **New-branch range has no merge-base of any kind.** A new-branch push gets
  the bare tip SHA as its scan range (`_PARALLAX_RANGE="$_l_sha"` in the per-ref loop). `^refs/remotes/origin/main` is
  then appended as a *separate, second* argument to both the message scanner
  and the guard call — the identical two-argument construction used for an
  existing branch's range (the per-ref scanner and guard calls) — and only when (a) the push
  targets the same URL `origin` was fetched from, per
  `_parallax_targets_origin`, and (b) the best-effort `origin/main` fetch
  immediately beforehand succeeded. Neither condition met: nothing is
  appended, and the bare tip is scanned whole. **No base is ever computed
  from `origin/master`, local `main`, or local `master`.** This replaces a
  prior mechanism (present through commit `020dc95`, now removed from the
  working tree) that picked a merge-base by searching `origin/main
  origin/master main master` in order and using `git merge-base` against the
  first ref found — a mechanism that could pick a stale local `main`/`master`
  as the base and leave unpublished ancestors of the pushed branch
  unscanned. A reviewer traced exactly this path as contradicting this
  audit's own SEC-12 "fails toward scanning more" claim; removing the
  local-ref fallback entirely (rather than only reordering it) is what makes
  that claim hold for new-branch pushes too. Confirmed by
  `test_a_new_branch_scans_only_what_it_adds_over_the_default_branch` (asserts
  the scanner receives exactly `[head, "^refs/remotes/origin/main"]`, not a
  merge-base),
  `test_unrelated_history_is_scanned_whole_not_from_a_local_base` (a new
  branch sharing no history with a freshly re-created `origin/main` is
  scanned from its own tip with no `..` range anywhere in the arguments, not
  from a local base), and
  `test_the_guard_does_not_base_a_new_branch_on_local_main`.
- **The enclosing block always runs; the message-scan step inside it does
  not always scan.** Through `020dc95`, the entire block (message scanner
  and guard both) was gated behind an outer presence test —
  `[ -f scanner ] || [ -f guard ] || [ -f registry ] || git cat-file -e
  origin/main:client_guard.py` — so a clone with none of those anywhere
  skipped the whole layer silently, on every push, to any remote. The
  working-tree version removes that outer gate; the block now always runs.
  Within it, the message-scan step is skipped only when **neither** the
  checkout **nor** `refs/remotes/origin/main` has
  `scan_commit_messages.py`, and then it prints a warning that commit
  messages were not scanned. When the script is missing in the checkout but
  present on `refs/remotes/origin/main`, the push **blocks** (exit 2,
  "scan_commit_messages.py is missing here but present on origin/main") —
  a branch cannot evade the scan by deleting the script locally. This
  missing-vs-present check runs on the per-ref path only (the per-ref missing-scanner check,
  inside the `while read` loop); the no-ref-info fallback used only for a
  by-hand invocation with nothing on stdin (the no-ref-info fallback) runs the scanner
  directly if present in the checkout, with no equivalent origin/main
  cross-check — a narrower case than the per-push path, and not reachable
  from an actual `git push`. Confirmed by
  `test_a_branch_that_deletes_the_message_scanner_is_blocked`.
- **A push to `origin` with no client guard found anywhere now warns instead
  of passing silently.** Through `020dc95`, `_parallax_guard`'s only
  non-blocking path was a fetch-failure branch
  (`elif [ -n "$_PARALLAX_FETCH_FAILED" ]`) that no longer exists in the
  function; combined with the outer presence gate above, a clone with no
  scanner, no guard, no registry anywhere skipped the entire layer with no
  message printed at all. The working-tree version's final `else` branch
  prints `WARNING: no client guard was found; client names were NOT scanned`
  and lets the push proceed, for a push that targets `origin`. A push to any
  *other* remote under the same no-guard-anywhere condition still blocks
  outright (exit 2) — unchanged from the prior revision's description.
  Confirmed by `test_a_push_to_origin_with_no_guard_anywhere_warns`.
- The now-separate fetch-failure warning (`could not refresh origin/main...
  scanning the whole pushed history`) is printed once, unconditionally,
  immediately after the fetch attempt (the refresh-failure warning) — independent of
  whether a guard can later be resolved. It is no longer a branch inside
  `_parallax_guard`.
- All `origin/main`/`origin/master` references use the full ref name
  (`refs/remotes/origin/main`, `refs/remotes/origin/master`), so a local
  branch or tag named `origin/main` cannot shadow it
  (`test_a_local_ref_named_origin_main_does_not_pose_as_main`).
- **There is no gate-repo forwarding check**, unchanged from the prior
  revision: a push through a local `no-mistakes` gate repository is not
  detected or special-cased; it counts as "elsewhere" like any other
  non-origin target, even when that gate repo's own `remote.origin.url`
  happens to match
  (`test_a_gate_repo_never_gets_the_exclusion`).
- A repointed `origin` push URL is not independently checked; it falls out of
  the same URL comparison, because a differing pushurl makes `$2` differ from
  `origin`'s fetch URL and the push is treated as elsewhere
  (`test_a_pushurl_elsewhere_is_not_origin`).
- The fetch's SSH timeout override (`ConnectTimeout=15`,
  `ServerAliveInterval=5`/`ServerAliveCountMax=3`) is applied only when none of
  `GIT_SSH_COMMAND`, `GIT_SSH`, `GIT_SSH_VARIANT`, `core.sshCommand`, or
  `ssh.variant` is already set, and does not set `BatchMode`: a passphrase key
  without an agent may still prompt, as the hook's own comment discloses.
  Unchanged from the prior revision.
- Tests covering this logic, read directly against the current working-tree
  file: `test_no_exclusion_when_pushing_somewhere_other_than_origin`,
  `test_a_pushurl_elsewhere_is_not_origin`,
  `test_a_gate_repo_never_gets_the_exclusion`,
  `test_a_local_ref_named_origin_main_does_not_pose_as_main`,
  `test_a_failed_fetch_warns_and_drops_the_exclusion`,
  `test_a_push_elsewhere_without_any_guard_blocks`,
  `test_a_new_branch_scans_only_what_it_adds_over_the_default_branch`,
  `test_unrelated_history_is_scanned_whole_not_from_a_local_base`,
  `test_the_guard_does_not_base_a_new_branch_on_local_main`,
  `test_a_branch_that_deletes_the_message_scanner_is_blocked`,
  `test_a_push_to_origin_with_no_guard_anywhere_warns`.

**`client_guard.py` changes this revision are narrower than the pre-push
layer's.** Relative to the first-pass code, the change is narrow: only two
functions, `_scan_tags` and `run_ci` (the tag-to-blob/tree fix described
above), differ; key handling, registry parsing, and the reporting paths are
unchanged from the first pass, not re-read this pass beyond confirming
that. Everything else in the prior revisions' description of
`client_guard.py` still holds on that basis: HMAC-SHA256-keyed registry
holding only digests (no plaintext match forms); key consumed in-process
only, never passed to a subprocess argument list, never logged; CI secret
delivered via `env:` only; the required CI check prefers the trusted copy
committed on the base branch over the copy under test; the local hook is
explicitly best-effort/bypassable while the CI check is the non-bypassable
gate; and every reporting path prints a rule id and location only, with a
location that itself contains a registered form replaced by a
withheld-location placeholder in CI mode.

**New this revision — the staged `.client-guard/allow-binary.txt`.**
Holds one signed entry, `<sha> <mac>` per `parse_allowlist`'s format, for a
single JPEG blob, `d0c4f1f5...`: the `docProps/thumbnail.jpeg` member of
`skills/parallax-cio-letter-prep/fixtures/golden_pack_2026-04.docx` as that
file existed at the root commit (`3cce236`, docx blob `48b065aa...`). HEAD's
version of that path is a different blob (`3a8a71b1...`) with no thumbnail,
so it needs no entry. The root-commit docx has 17 members: 16 XML/`.rels`
parts and the thumbnail. A reviewer checked the thumbnail at the pixel
level: 395x512, every pixel white, no comment segment, EXIF holding only
resolution, pixel-dimension and offset tags, and a generic RGB ICC profile
whose only text is its description and a vendor copyright string. Without the entry, that member hits
`unscanned/opaque-file` (`.jpeg` is an opaque suffix) on any scan that
walks the root commit; a reviewer confirmed this by scanning with an empty
allowlist. The entry names the thumbnail, not the whole docx: `scan_bytes`
checks the allowlist before archive descent, so a container-level entry
would also have stopped scanning the 16 XML parts. With the thumbnail-only
entry those parts stay under the guard, and the allowlist applies again to
each member at depth 1. The MAC binds the entry to that sha; a reviewer
confirmed the same MAC is rejected for another sha. `python3
skills/_parallax/scripts/client_guard.py scan-range HEAD` (every commit in
the branch history, including the root) exits 0 clean. Where full-history scans happen: the
pre-push layer scans a whole branch when the push does not target origin's
fetch URL (for example through the no-mistakes gate) or the refresh failed;
in CI, every new-ref push run (and a force push whose old tip is gone)
walks the root until the guard is on main, because until then no trusted
revision is exported to exclude it. CI reads the allowlist from the pushed
tree, so the entry must be committed before the branch is pushed. CI merges
the allowlist from the checked-out change with the trusted revision's copy,
so a pull request can add entries, but each needs a MAC from the key, and
fork pull requests get no key and fail closed.

## Verification performed this pass

- `python3 -m pytest -q skills/_parallax/scripts/test_client_guard.py
  skills/_parallax/scripts/test_install_git_hooks.py` — **193 passed**,
  run fresh against the current working tree, at the time of this revision
  (up from 186 in the prior same-day revision; both test files grew, so the
  increase is not attributed to any single behavior above). Re-run this
  pass against the rebased working tree (base `bda5bf4`); the count is
  unchanged, consistent with these files being content-identical to the
  pre-rebase squashed commit except the one test-assertion change noted in
  the Scope Note above.
- `git ls-files | wc -l` — **707** tracked files, at the time of this
  revision (the new audit file itself is tracked and counted). Up from the
  prior revision's 699 because the rebase moved the base: `git ls-tree -r
  bda5bf4 --name-only | wc -l` is 701 against the old base's 693 (+8 files
  merged in from `fix/port-2026-10-20-fixes`, audited in
  `audit-2026-10-23.md`, not by this delta); commit `8a4d5cb` itself adds 6
  tracked files on top of either base (the registry, the CI workflow, the
  two `docs/security` audit files, `client_guard.py`,
  `test_client_guard.py`); the staged allow-binary addition and the staged
  removal of the superseded audit file net to zero.
- `git diff bda5bf4 --cached --stat | tail -1`, measured after this file
  was written — **13 files changed**, at the time of this revision (line
  counts omitted: this file is part of the diff). This
  is measured against the rebase's new base (`bda5bf4`) and includes the
  staged allow-binary addition and the staged removal of the superseded
  audit file alongside commit `8a4d5cb`'s own changes, so it is not
  comparable to the prior revision's 2854/55 figure (measured against
  `3cce236`, before the rebase); it includes this audit file itself, which
  is why the count is only stable once the file stops growing.
- `python3 skills/_parallax/scripts/scan_commit_messages.py` — re-run this
  pass: 1 outgoing commit in `origin/main..HEAD` scanned, clean.
- `python3 skills/_parallax/scripts/scan_tracked_terms.py` — re-run this pass:
  707 tracked files scanned, no restricted terms (consistent with the
  `git ls-files` count above).
- Secret-prefix / `password=` / `api_key=` / `secret=` grep across the repo's
  Python/shell/workflow files (excluding test/env/CI-secret-reference noise)
  — re-run this pass: 0 hits attributable to this delta. Private-key-block
  grep — re-run this pass: 2 hits, both pre-existing synthetic test fixtures
  in `white-label` test files, outside this diff and unchanged by `git diff
  bda5bf4 --stat`. `find . -name ".env*"` — re-run this pass: 0 hits.
- `.client-guard/registry.json` schema check — re-run this pass (direct
  Python read): keys are
  `version`, `algorithm`, `normalization`, `prefix_length`, `verifier`,
  `lengths`, `prefixes`, `digests` — 12 digests and 11 prefixes, every entry
  exactly 64 lowercase-hex characters; the `verifier` field is also 64
  lowercase-hex characters; `lengths` is `[6, 7, 9, 11, 12, 14, 16, 25]`. No
  plaintext name or other sensitive value present. Same generic,
  deliberate-tradeoff disclosure (counts and normalized lengths only) noted in
  the prior passes.
- Diffed `CLAUDE.md`, `CONTRIBUTING.md`, `CHANGELOG.md` against `bda5bf4`
  directly (3 files changed, 46 insertions(+), 1 deletion(-)): all three
  changes are prose describing the narrowed `origin/main`
  exclusion, the tag-content fix above, the no-local-base rule for new
  branches, the missing-scanner block, and the no-guard warning; no internal
  identifier, partner name, or sensitive value introduced in any of the
  three.
- Re-ran this pass: `git diff bda5bf4 --stat -- skills/_parallax/render_gate.py
  skills/_parallax/scripts/release.py` — empty (no changes); both files
  confirmed present on disk. The client-policy input readers cited in prior
  passes were not independently re-read this pass beyond confirming they are
  absent from `git diff bda5bf4 --stat`.
- Dual static skill-scanner sweep (Cisco `skill-scanner` + NVIDIA
  `skillspector --no-llm`, via the gate wrapper) against the scripts directory
  containing the delta — **not re-run this pass**; carried from the prior
  same-day revision, whose result was **0 CRITICAL**, 6 HIGH, all in the
  same category and file set earlier passes already assessed as benign
  static false positives on this repo's own tooling/test suites. The four
  client-guard files swept (`client_guard.py`, `install_git_hooks.sh`, and
  their two test files) are the only `skills/_parallax/scripts/` files
  commit `8a4d5cb` itself touches, and are content-identical to the
  pre-rebase squashed commit for three of the four; the fourth,
  `test_install_git_hooks.py`, differs only by the base's own test-assertion
  edit merged in by the rebase (Scope Note above) — not a new
  scanner-relevant category.
  `git ls-files | wc -l`'s move from 699 to 707 is the rebase's new base and
  this file's own addition, not a change to this scanned file set: the
  other `skills/_parallax/scripts/` files that changed between the two
  bases (`build_bundle.py`, `run-gate-tests.sh`, `test_build_bundle.py`,
  `test_concierge_contract.py`) came in with `bda5bf4` from
  `fix/port-2026-10-20-fixes` and were swept by `audit-2026-10-23.md`, not
  by this file.
- This report was re-checked against all three available restriction sources
  after this revision's text was finalized: the packaging script's built-in
  canary-term list (import + direct regex, hit count only ever inspected — 0
  hits), the maintainer's separate local-only extra canary-term list (0
  hits), and `client_guard.py scan-text` piped the finished file through the
  registered-name scanner directly (0 hits, exit 0). Also reviewed by eye for
  any absolute local filesystem path, local account name, or working-copy
  directory suffix — none present.

## Checklist Results

SEC-01 PRIVACY_POSTURE: NA
  evidence: No end-user data collection in this diff; unchanged from prior audit.

SEC-02 RLS_COVERAGE: NA
  evidence: No Supabase/Postgres surface anywhere in this repo.

SEC-03 AUTH_EDGE_CASES: NA
  evidence: No auth surface in this diff.

SEC-04 SERVER_SIDE_VALIDATION: PASS
  evidence: No new req.body/HTTP input-handling surface. `Registry.parse`
  and `parse_allowlist` reject any unexpected field, wrong version or
  algorithm, non-hex entry, or empty digest set before trusting the file;
  the CI event-payload reader reads only a closed set of string fields from
  GitHub's own event JSON. No regression to the prior passes' SEC-04 basis.

SEC-05 RATE_LIMITS: NA
  evidence: No paid-API integration in this diff.

SEC-06 CORS_ALLOWLIST: NA
  evidence: No HTTP API surface anywhere in this repo.

SEC-07 CAPTCHA_PUBLIC_FORMS: NA
  evidence: No public-facing forms in this diff.

SEC-08 ERROR_RESPONSE_HYGIENE: NA
  evidence: No HTTP API surface. The guard's own failure path prints a rule
  id and location only (withheld when the location itself would leak a
  match), never a stack trace or matched text, to CI's public logs.

SEC-09 NO_API_KEYS_FRONTEND: PASS
  evidence: No frontend build exists in this repo. Secret-prefix / bearer-
  token / hardcoded-key grep of the full delta: 0 hits.

SEC-10 NO_ENV_IN_FRONTEND: PASS
  evidence: No `.env` file added; no `public/`/`dist/`/`static/` directory
  in this repo. The registry key is supplied only via an environment
  variable or an out-of-repo home-config file, consumed in-process, never
  logged, never passed as a CLI argument. The key-file permission-mode check
  in `load_key()` is verified by a passing test this pass.

SEC-11 SECURITY_HEADERS: NA
  evidence: No deployed production URL; no HTTP server anywhere in this repo.

SEC-12 OWASP_TOP10: PASS
  evidence: 0 Critical-severity findings attributable to this diff (dual
  static scanner sweep, this pass). No SQL/command/template injection, no
  `shell=True`, no unsafe deserialization introduced; all `git` invocations
  use argument lists, never shell strings built from scanned content. The
  new tag-to-blob/tree scanning closes a content-coverage gap (not an
  exploited one in this repo's history). Scoped precisely: the `origin/main`
  exclusion applies only when the push URL equals origin's fetch URL (only a
  trailing slash is normalized, so `X` and `X.git` are different targets) and
  the refresh of `refs/remotes/origin/main` succeeded. A failed refresh, any
  other target (including a pushurl that differs from the fetch URL and a
  local no-mistakes gate repo), and a new branch with unrelated history all
  get no exclusion; a non-origin push with no guard anywhere blocks. The layer
  sets `GIT_NO_REPLACE_OBJECTS=1` for its own git reads and puts the
  caller's value back afterwards, so the scans read the objects the push
  sends. `core.useReplaceRefs=true` in config overrides the variable; a
  reviewer observed that git then sends the substitute objects as well, and
  the receiver rejected the push for missing objects. A receiver that already
  holds the original objects was not tested. This does **not** extend to
  the message scanner's own rule content: the scanner runs whatever is in the
  checkout with no trusted-copy preference, so a branch that *edits* (rather
  than deletes) `scan_commit_messages.py` runs its own weakened rules
  unchallenged (item 2 below). It also does not extend to a commit added by
  the `no-mistakes` gate's document step, which never traverses this hook
  (item 3). Known Low residuals, deferred: tag annotations, notes and ref
  names reach the client guard but not the message-vocabulary scanner; with
  no real `refs/remotes/origin/main`, a local ref spelled with that full name
  can stand in for it; the refresh fetches only `main`, so the
  `refs/remotes/origin/master` arm is reachable only on a by-hand run. The CI check's
  self-certification bootstrap on first push and the by-design bypassability
  of the local pre-push layer remain accepted, disclosed design properties,
  not vulnerabilities.

## Critical Findings Detail

None at Critical or FAIL severity in this diff.

**Resolved since the first pass:**

1. **(Was Low, now closed) Client-guard key file permission mode.**
   `load_key()` now rejects a group- or world-readable key file before
   trusting its contents, verified by a passing test.
1a. **(Was Medium, now closed) Replace refs.** With `refs/replace/*` in
   effect both scanners read substitute objects while the push sends the
   originals. The layer now sets `GIT_NO_REPLACE_OBJECTS=1` for its own git
   reads and puts the caller's value back afterwards (overridden by
   `core.useReplaceRefs=true`, see SEC-12)
   (`test_replace_refs_do_not_hide_what_the_push_sends`,
   `test_the_layer_puts_the_callers_replace_setting_back`).
1b. **(Was Low, now closed) `.git` suffix match.** URL comparison stripped
   `.git`, so a local `X` matched an origin at `X.git`. Only a trailing slash
   is normalized now (`test_a_dot_git_suffix_does_not_make_another_repo_origin`).

**New this revision (pre-existing design properties, not introduced by this
diff — first recorded in this revision, not present in either prior pass of
this audit):**

2. **(Medium) Message-scanner-from-checkout has no trusted-copy
   preference.** Unlike `client_guard.py` (which `_parallax_guard` extracts
   from `refs/remotes/origin/main` into a tempfile and runs in preference to
   the checked-out copy, in `_parallax_guard` in `install_git_hooks.sh`),
   `scan_commit_messages.py` is invoked directly from the checkout path
   (`python3 "$_PARALLAX_SCAN" ...`, in the per-ref loop) with no equivalent
   origin/main cross-check on its *content*. The missing-vs-present check
   added this revision (the per-ref missing-scanner check) blocks a branch that **deletes** the
   script, but a branch that **edits** it — narrowing a rule, adding an
   allowlist entry, or truncating the vocabulary it checks — runs its own
   edited copy unchallenged, and the hook reports it as a clean scan. There
   is no CI backstop for this scanner: `evals.yml` (line ~205) states
   `scan_commit_messages.py` is deliberately not wired into CI, because a
   shallow checkout has no usable base-ref range. The commit-message
   vocabulary therefore has exactly one enforcement point — this bypassable
   local hook, running whatever copy of the script is on the branch being
   pushed. Not an exploited gap in this diff; worth a follow-up to either add
   a trusted-copy preference matching the guard's, or wire a CI check that
   runs the trusted copy against the outgoing range in the pull-request
   workflow.
3. **(Medium) A commit added inside the `no-mistakes` gate's document step
   never passes through this pre-push hook.** The gate forwards to `origin`
   from its own isolated worktree/repo, which has no copy of this layer
   installed; from this hook's perspective, a push through the gate is
   itself "elsewhere" regardless of where the gate ultimately forwards
   (confirmed unchanged by `test_a_gate_repo_never_gets_the_exclusion`, see
   above). `install_git_hooks.sh` itself documents why: its own `mkdir -p
   "$HOOKS_DIR"` failure path in the installer states "In a linked git
   worktree the hooks live with the main checkout; install there," and notes
   "The no-mistakes gate runs in exactly such a worktree" — direct evidence,
   from the installer's own comments, that this layer cannot be installed
   into the gate's worktree the way it is installed into a normal clone. The gate's document step has auto-fix enabled and may add a
   commit of its own before forwarding. The client-guard side of this gap is
   covered by a separate layer — the required `client-guard.yml` CI check
   runs on every branch and tag push to GitHub regardless of which local
   hook did or didn't run — but the commit-message vocabulary has no
   equivalent CI-side check (see item 2), so a message on a gate-added commit
   is scanned by nothing before it is public. Pre-existing behavior of the
   gate/hook boundary, not introduced by this diff.

**Carried forward (re-confirmed present, unchanged, and outside this diff's
footprint; not re-derived from scratch):**

4. **(Medium, still open) Render-gate path-containment is basename-only, not
   cwd-anchored.** `skills/_parallax/render_gate.py` still accepts any parent
   directory whose basename matches the draft-directory name without
   checking it sits under the session's resolved working directory.
   Untouched by `git diff bda5bf4`.
5. **(Medium, still open) Draft file mode unmeasured against the real host
   tool.** Not measured this pass either.
6. **(Low, still open) Unbounded read for `index.json`/`SHA256SUMS` in
   `release.py`'s release-verification routine.** Untouched by this diff.
7. **(Low, still open) Client-policy input readers lack a byte cap and
   bounded-YAML treatment** that a more hardened reader elsewhere in the
   codebase already has. Untouched by this diff.

**Non-blocking, informational, carried forward unchanged in substance:**

8. Registry bootstrap self-certification on first push (announced via CI
   notice; no action needed).
9. Registry metadata disclosure — the public registry's `lengths` array
   discloses counts and normalized character-lengths, not content; a
   deliberate tradeoff.
10. Fork pull requests always fail the required check without a key — an
    accepted, documented consequence of failing closed.

None of the above changes the SEC-04/SEC-09/SEC-10/SEC-12 PASS verdicts.

## Deep OWASP Findings (parallel track)

Not run this pass — Default Mode only, scoped to the diff described above.

## What I did not check

- Did not re-run the full repo-wide test suite; ran only the two targeted
  test files as evidence for this delta, same scope as the prior passes.
- Did not independently re-derive the four still-open carried-forward backlog
  items (4-7 above) beyond confirming the files they cite are present,
  unchanged, and outside this diff's `git diff bda5bf4 --stat` footprint.
- Did not re-run `pip-audit` or a dependency scan — no `requirements.txt`
  changed in this diff.
- Did not execute a live GitHub Actions run of `client-guard.yml`; it was
  first added in the pre-rebase first-pass commit, is unchanged since
  (confirmed content-identical in commit `8a4d5cb` and absent from
  `git status --short`), so the prior direct read of it was not
  re-examined this pass.
- Did not independently re-read the three client-policy `_read_input_file`
  readers this pass; relied on their absence from `git diff bda5bf4 --stat`
  to confirm they are unchanged.
- Did not re-verify sections of the prior passes unrelated to the pre-push
  layer and the client guard beyond the spot-checks recorded above (registry
  schema, prose diffs, backlog-file footprint, scanner sweeps); this revision
  was scoped to correcting the pre-push-layer and guard claims a reviewer
  flagged as outdated against the second round of hook-script changes.
- Did not test the no-ref-info fallback path (the no-ref-info fallback) against an
  actual `git push`; it is reachable only by a by-hand hook invocation with
  nothing on stdin, confirmed by direct read rather than by exercising it
  through a real push.

## Handoff

All items are PASS or NA; 0 FAIL; CRITICAL_FAILS=0. **Push will pass the
gate.** New backlog from this revision, none blocking: (1) add a
trusted-copy preference for the commit-message scanner matching the client
guard's, or add an equivalent CI-side check; (2) note that a commit added by
the `no-mistakes` gate's document step bypasses this hook entirely; (2a) Low:
tag annotations, notes and ref names are not checked by the message-vocabulary
scanner (the client guard covers them); (2b) Low: a force push over a remote tip
that is not local blocks with a "rewrite the message" hint where "fetch first"
is meant. Carried
forward, unchanged, none blocking: (3) anchor the render-gate
draft-directory containment check to the session's resolved working
directory; (4) measure the draft's actual file mode under the real host
tool; (5) add a byte cap to the release-verification
`index.json`/`SHA256SUMS` reads; (6) add a byte cap and bounded-YAML-node
treatment to the three client-policy input readers. No threat model is
present for this repo; recommend `/threat-model`.

SUMMARY: PASS_COUNT=4 FAIL_COUNT=0 NA_COUNT=8 CRITICAL_FAILS=0 AUDIT_DATE=2026-10-23 CHECKLIST_VERSION=1
