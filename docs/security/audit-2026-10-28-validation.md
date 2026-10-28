# Security audit — validation follow-up

AUDIT_DATE: 2026-10-28
AUDIT_COMMIT: 1c873ee8428205498814a3814b540919a3922c87
REVIEWED_STATE: uncommitted follow-up to the audited commit
CHECKLIST_VERSION: 1

## Scope and evidence

This report extends the [publication review](audit-2026-10-28-publish.md).
That report remains a historical snapshot, including its stated limits.
The validation gate subsequently reviewed the proposed difference and passed
all 17 offline suites at the commit above. Additional review identified two
cases absent from that evidence; this follow-up covers their fixes.

The signed approval in `.client-guard/allow-binary.txt` is restored byte for
byte from the earlier reviewed version. It covers an embedded member of a
reachable historical fixture, even though the current tree lacks that member.
No new approval or broader exemption is introduced.

Optional registry lookup now confirms absence through a successful Git tree
read. A failed tree read or a present entry with an unreadable blob raises
an error. The trusted registry union and fork-point removal rule remain intact.

The reviewed `skills/_parallax/scripts/client_guard.py` SHA-256 is
`e9451a0f489a51b3c3ce9d3887a726617315abc02d1edbd9b4460a6f71515a59`.
The follow-up changes only that runtime, its tests, the exact restored approval,
and this report and latest-report symlink. Other security conclusions below
carry forward the earlier review rather than claiming a fresh audit of every file.

## Checklist results

SEC-01 PRIVACY_POSTURE: NA
  evidence: No data collection, telemetry or application privacy flow changes.

SEC-02 RLS_COVERAGE: NA
  evidence: No database or database policy changes.

SEC-03 AUTH_EDGE_CASES: NA
  evidence: No application authentication or session changes.

SEC-04 SERVER_SIDE_VALIDATION: PASS
  evidence: Optional registry reads distinguish confirmed absence from Git
  read failures. Executable tests remove loose objects from isolated temporary
  repositories and assert failure. Existing trusted-union and removal tests
  remain applicable. A historical fixture test reaches the actual embedded
  member and verifies rejection without its exact approval and acceptance with it.

SEC-05 RATE_LIMITS: NA
  evidence: No public request handler or paid-service integration changes.

SEC-06 CORS_ALLOWLIST: NA
  evidence: No HTTP application or browser-origin policy changes.

SEC-07 CAPTCHA_PUBLIC_FORMS: NA
  evidence: No public input form changes.

SEC-08 ERROR_RESPONSE_HYGIENE: NA
  evidence: No HTTP response changes. New CLI failures identify the failed
  registry-read category and revision without printing blob contents.

SEC-09 NO_API_KEYS_FRONTEND: PASS
  evidence: No frontend or key distribution changes. The restored approval
  is a previously signed content identifier; no key is added.

SEC-10 NO_ENV_IN_FRONTEND: PASS
  evidence: No environment export or frontend configuration changes.
  Existing external-key handling remains unchanged.

SEC-11 SECURITY_HEADERS: NA
  evidence: No deployed HTTP server or security-header changes.

SEC-12 OWASP_TOP10: PASS
  evidence: Git calls retain argument-list execution and existing revision
  validation. Read failures no longer suppress the registry-removal baseline.
  Approval restoration binds only the same historical bytes. The new tests
  alter only disposable test repositories. Workflow permissions, trusted-code
  execution and author controls are unchanged from the publication review.

## Verification and remaining rollout

- Eight selected regression tests passed on the working follow-up.
- The separate temporary proposal reproduced five failing cases before the
  fix and passed ten selected cases afterward.
- The keyed scan of all 26 commits reachable from the reviewed head passed
  using the corrected working runtime and restored approval.
- The working script-directory scan and outgoing-message scan passed.
- The tracked-term scan checked 711 tracked files before adding this report.
- Whitespace validation passed. Full validation of this follow-up is pending;
  the earlier 17-suite pass is not substituted for it.

The historical-member test explicitly skips when a shallow checkout lacks its
historical commit. It ran successfully with full local history. Other new
failure-injection tests use freshly constructed repositories.

Environment policy and secret presence were separately checked through GitHub
metadata. The broader repository-level secret was removed. These operational
checks do not establish a successful guard workflow or required PR check.
No publication, main CI success or completed rollout is asserted here.
Verify the main workflow and a subsequent PR's check association before
treating automated merge protection as established. Accepted limits and
unreviewed historical backlog remain as recorded in the publication review.

SUMMARY: PASS_COUNT=4 FAIL_COUNT=0 NA_COUNT=8 CRITICAL_FAILS=0 AUDIT_DATE=2026-10-28 CHECKLIST_VERSION=1
