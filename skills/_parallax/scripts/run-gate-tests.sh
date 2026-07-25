#!/usr/bin/env bash
# run-gate-tests.sh — run the skill/eval Python suites for the repository gate.
#
# Why not a single `pytest` invocation: three skills ship a `tests/conftest.py`
# (_parallax/white-label, parallax-judge-house-view, parallax-make-house-view).
# The `tests/` dirs aren't packages and their parent dirs are hyphenated, so
# pytest names every one `tests.conftest`; collecting two in one process fails
# (`Plugin already registered ... tests.conftest`). `--import-mode=importlib`
# does NOT fix it (the conftest plugin name still collides). The robust fix is
# one process per top-level test root, so each conftest gets its own scope.
#
# Roots are AUTO-DISCOVERED (every skills/* and evals/* dir containing test
# files), so new skills with tests are covered with no edit here — closing the
# silent-partial-coverage gap that the hand-picked `house-view + graders`
# command left (it ran ~285 of ~905 tests).
#
# The default mode is hermetic/offline and deselects tests marked `npx` because
# the real smoke uses `npx -y`, which can download and execute a package. Set
# PARALLAX_GATE_MODE=network only in an explicitly network-authorized run.
#
# Invariant: each top-level root must hold at most ONE conftest.py (else two
# would collide inside that root's single process). This is asserted below and
# fails LOUDLY rather than silently under-running.
#
# Portable to bash 3.2 (macOS default — no mapfile / associative arrays).
set -uo pipefail

gate_mode="${PARALLAX_GATE_MODE:-offline}"
case "$gate_mode" in
  offline|network) ;;
  *)
    echo "run-gate-tests: invalid PARALLAX_GATE_MODE '$gate_mode' (expected offline or network)" >&2
    exit 2
    ;;
esac

if [ "$gate_mode" = "offline" ]; then
  # Defense in depth for any opt-in integration checks added later. Tests must
  # still use fakes, but inherited operator settings cannot activate live paths.
  export PARALLAX_E2E_LIVE=0
  export PARALLAX_E2E_SPEND=0
  export PARALLAX_S1_INTEGRATION=0
fi
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"   # scripts -> _parallax -> skills -> repo root
cd "$ROOT" || exit

# Top-level skills/* and evals/* dirs that contain at least one test file.
roots=$(
  { find skills -mindepth 1 -maxdepth 1 -type d
    if [ -d evals ]; then
      find evals -mindepth 1 -maxdepth 1 -type d
    fi
  } | while IFS= read -r d; do
    if find "$d" \( -name 'test_*.py' -o -name '*_test.py' \) -print -quit 2>/dev/null | grep -q .; then
      echo "$d"
    fi
  done | sort -u
)

if [ -z "$roots" ]; then
  echo "run-gate-tests: no test roots discovered under skills/ or evals/" >&2
  exit 1
fi

fail=0
n=0
while IFS= read -r d; do
  [ -z "$d" ] && continue
  # Guard the one-conftest-per-root invariant — fail loud, never silently mis-run.
  cfg=$(find "$d" -name conftest.py | wc -l | tr -d ' ')
  if [ "$cfg" -gt 1 ]; then
    echo "run-gate-tests: $d holds $cfg conftest.py files — they will collide in one" >&2
    echo "  pytest process. Split this root (run each conftest subtree separately)." >&2
    fail=1
    continue
  fi
  n=$((n + 1))
  echo "── pytest $d ($gate_mode)"
  if [ "$gate_mode" = "offline" ]; then
    python3 -m pytest "$d" -q -p no:cacheprovider -m "not npx"
    status=$?
  else
    python3 -m pytest "$d" -q -p no:cacheprovider
    status=$?
  fi
  if [ "$status" -ne 0 ]; then
    fail=1
    echo "  ✗ FAILED: $d" >&2
  fi
done <<EOF
$roots
EOF

if [ "$fail" -eq 0 ]; then
  echo "✓ all $n gate test suites passed"
else
  echo "✗ one or more gate test suites failed or collided" >&2
fi
exit $fail
