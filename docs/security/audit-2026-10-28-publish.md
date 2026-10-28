# Security audit — client-guard rollout

AUDIT_DATE: 2026-10-28
AUDIT_COMMIT: ca86915378203b785f63c584f83e2a8a9615a313
AUDIT_BASE: 11a575fc2a98a2887edad355b10745feb3765e22
REVIEWED_STATE: resolved, uncommitted merge into the audited parent
CHECKLIST_VERSION: 1

## Scope and identity

This review covers the pending difference from `origin/main` at the base above.
It includes the new guard, registry, signed binary approval, workflow, hook changes,
tests, fixture update, documentation cleanup and generated reference copies.
The parent commit above is not the completed merge commit.
No unresolved merge entries remained when reviewed.

The SHA-256 of `git diff --binary origin/main` before adding this report was
`bccd6e6497a6b9941e25efbb0eb2d33fb684517dd214bd95c5774580d88066d3`.
This identifies the pending delta, not a committed Git tree.
The report itself is outside that fingerprint.

Reviewed runtime SHA-256 fingerprints:

| File | SHA-256 |
|---|---|
| `skills/_parallax/scripts/client_guard.py` | `e5734841d25897460d243c4561d0441f10ddbfd7da8dbae93aa2359277081b49` |
| `skills/_parallax/scripts/install_git_hooks.sh` | `cc8248c894fc16a6a1ce9bbdbac24c064d7643e17e97578f3776b3965d504a23` |
| `.github/workflows/client-guard.yml` | `ee137e10d5ec087386f242df9aaf521bc3eec6cfc0e94d40d5521e58bad8a542` |
| `.github/CODEOWNERS` | `5500ceb48846548e4cfff8d286f52821952d5f4f9f4d47916ffda7e52942b5e9` |
| `.gitleaks.toml` | `de22828de7ea97e89b74c23340a61bf8db289be5ed7ca28dc1a06dc352e606e4` |

The secret-scanner configuration matches the reviewed base.
Its test-fixture exceptions remain limited to named fixture paths.
No dependency declaration or lockfile changes appear in this delta.

## Checklist results

SEC-01 PRIVACY_POSTURE: NA
  evidence: This delta adds local repository scanning and contributor guidance.
  It adds no end-user data collection, telemetry service or application privacy flow.

SEC-02 RLS_COVERAGE: NA
  evidence: No database, row-level policy or database migration is added.

SEC-03 AUTH_EDGE_CASES: NA
  evidence: No application login, session or authorization endpoint is added.
  Workflow author-trust controls are reviewed under SEC-12.

SEC-04 SERVER_SIDE_VALIDATION: PASS
  evidence: The local guard validates registry structure and key association,
  verifies signed approvals, and rejects registry weakening through the proposed revision.
  Scanner errors return failure rather than a clean result.
  Review covered staged paths, symlink handling, embedded payloads, notebook
  structure, archive bounds and oversized Git objects.
  Eighteen focused regression tests passed on the reviewed runtime.
  They cover long unsupported headers, staged paths absent from disk,
  missing or wrong keys, and malformed notebook payloads.

SEC-05 RATE_LIMITS: NA
  evidence: This delta adds no public request handler or paid service integration.
  Local input-size bounds are assessed under SEC-04 and SEC-12.

SEC-06 CORS_ALLOWLIST: NA
  evidence: No HTTP application or browser-origin policy is added.

SEC-07 CAPTCHA_PUBLIC_FORMS: NA
  evidence: No public input form is added.

SEC-08 ERROR_RESPONSE_HYGIENE: NA
  evidence: No HTTP error-response surface is added.
  CLI and workflow output handling is reviewed under SEC-12.

SEC-09 NO_API_KEYS_FRONTEND: PASS
  evidence: No frontend key embedding or frontend build configuration is added.
  Redacted local secret scans found zero findings in outgoing history and
  in the staged merge changes. The public registry contains keyed digests;
  the approval file contains signed content identifiers, not the signing key.

SEC-10 NO_ENV_IN_FRONTEND: PASS
  evidence: No environment file or client-side environment export is added.
  The guard consumes its key through the process environment or an external
  local file. It rejects a key file with group or world permission bits.
  The workflow passes its secret only to the scanning step's environment.
  Neither command arguments nor the generated reference copies include key values.

SEC-11 SECURITY_HEADERS: NA
  evidence: No deployed HTTP server or security-header configuration is added.

SEC-12 OWASP_TOP10: PASS
  evidence: Source review found no new blocking injection or code-execution path
  in the reviewed delta. Git calls use argument lists; revision options are rejected.
  Archive members are read for scanning, never extracted into filesystem paths.
  Payload and object bounds limit reads; unsupported content produces findings.
  The long-header fallback consumes disjoint candidates without copying headers.
  The hook scans actual pushed refs and preserves input for subsequent hook layers.
  Default-branch exclusions require a successful refresh and matching destination.
  Installer refusals protect shared, symlinked, non-shell and malformed hooks.
  The workflow checks repository identity, author type and association before
  fetching or scanning candidate content. Untrusted PRs get a fixed failure.
  It executes a trusted guard with isolated Python and never executes PR code.
  Comment events scan only the comment author's fields.
  CI reporting withholds matching locations; unexpected exceptions print their type.
  Deployment controls and the residual limits below remain separate obligations.

## Local verification

- Restricted-term scan: 710 tracked files checked, no findings before this report.
- Outgoing message scan: three commits checked against the reviewed base, clean.
- Client-name scans of the audited parent tree, merged index and current working
  files: clean. The working-file scan included this new report.
- Redacted secret scans of outgoing history and staged merge changes: zero findings.
- Focused regressions: 18 passed, 658 deselected.
- Hook shell syntax, whitespace and unresolved-conflict checks: clean.
- The maintainer's full 17-suite offline run was still pending when this report
  was written. No earlier suite total is substituted for that pending result.

This review does not certify every historical commit or hosted edit revision.
The public-content scans above have the stated local scope only.

## Deployment items not verified by this review

No GitHub service or settings mutation was performed for this audit.
The source review does not establish the current environment policy,
secret placement, code-owner enforcement or required-check configuration.
Verify those separately through the
[maintainer checklist](../../CONTRIBUTING.md#maintainer-checklist-before-merging-client-guardyml).

Before merge, verify the main-only environment policy and secret placement,
then remove any broader repository-level copy as the checklist requires.
Workflow ownership protection and required status checks are distinct controls.
A CODEOWNERS file or a PR-review rule alone does not require a successful guard result.

The first installation has no existing default-branch PR guard to run.
Its push bootstrap can use the installed copy when the prior base lacks a guard.
After merge, confirm the actual main run and a subsequent PR's check attachment.
No live CI success, completed rollout or future push result is asserted here.

## Accepted limits and carried-forward backlog

The source check has no newly identified blocking finding in this scope.
The following limits remain disclosed; they are not claims of complete protection:

- Explicit name forms are required. Registry counts and lengths remain public.
  Detection targets accidental inclusion, not every deliberate encoding.
- Binary approvals bind exact bytes. A previously signed approval can be replayed.
- Local hooks remain bypassable. Legacy origin pushes without scanner copies warn.
  A failed refresh can leave recently registered forms unavailable locally.
- The message scanner still runs from the checkout. Gate-added commits bypass
  this clone's hook. Review final commit messages and changes independently.
- CI excludes review and release text, other branch pushes and tag pushes.
  Local Git hooks do not cover posted text. Main push runs can be skipped.
- Historical render containment, host draft permissions, release read bounds
  and client-policy input bounds are outside this delta and were not re-audited.
- Historical follow-ups about encoding edges, filename-free binary classification,
  archive resource use, hook portability, key-file ACLs and repeated scanning
  remain unverified beyond the specific code paths and regressions reviewed here.

The historical reports remain context, not current deployment certification.
Resolve any new final-tree scan or test failure before publishing.

SUMMARY: PASS_COUNT=4 FAIL_COUNT=0 NA_COUNT=8 CRITICAL_FAILS=0 AUDIT_DATE=2026-10-28 CHECKLIST_VERSION=1
