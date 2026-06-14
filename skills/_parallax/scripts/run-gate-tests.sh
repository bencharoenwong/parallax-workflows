#!/usr/bin/env bash
# run-gate-tests.sh — run the FULL skill/eval test suite for the no-mistakes gate.
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
# Invariant: each top-level root must hold at most ONE conftest.py (else two
# would collide inside that root's single process). This is asserted below and
# fails LOUDLY rather than silently under-running.
#
# Portable to bash 3.2 (macOS default — no mapfile / associative arrays).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"   # scripts -> _parallax -> skills -> repo root
cd "$ROOT"

# Top-level skills/* and evals/* dirs that contain at least one test file.
roots=$(
  { find skills -mindepth 1 -maxdepth 1 -type d
    find evals  -mindepth 1 -maxdepth 1 -type d
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
  echo "── pytest $d"
  if ! python3 -m pytest "$d" -q -p no:cacheprovider; then
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
