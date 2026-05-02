#!/usr/bin/env bash
# evals/compare.sh — run the same prompt against two git refs, time each, summarize.
#
# Usage:
#   ./evals/compare.sh "<prompt>" <ref-a> <ref-b> [runs]
#
# Example:
#   ./evals/compare.sh "/parallax-morning-brief $(cat evals/portfolios/small_5.json)" main~1 main 3
#
# Refuses to run if working tree has uncommitted changes (would be lost on checkout).
# Restores original branch on exit (including on failure).

set -euo pipefail

PROMPT="${1:?usage: $0 \"<prompt>\" <ref-a> <ref-b> [runs]}"
REF_A="${2:?missing ref-a}"
REF_B="${3:?missing ref-b}"
RUNS="${4:-3}"

# Working-tree safety
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
  echo "ERROR: working tree has uncommitted changes; commit or stash before running compare.sh" >&2
  exit 1
fi

ORIGINAL_REF=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD)
trap 'git checkout -q "$ORIGINAL_REF"' EXIT

REPO_ROOT="$(git rev-parse --show-toplevel)"
RESULTS="$REPO_ROOT/evals/results"
mkdir -p "$RESULTS"

run_label() {
  local ref="$1"
  local label="$2"
  echo "=== checking out $ref (label=$label) ==="
  git checkout -q "$ref"
  for i in $(seq 1 "$RUNS"); do
    echo "  run $i/$RUNS"
    "$REPO_ROOT/evals/bench.sh" "$PROMPT" "${label}_run${i}"
  done
}

run_label "$REF_A" "a-$(echo "$REF_A" | tr / -)"
run_label "$REF_B" "b-$(echo "$REF_B" | tr / -)"

# Summary: median wall_seconds per ref
echo
echo "=== summary ==="
python3 - "$RESULTS" "$REF_A" "$REF_B" "$RUNS" <<'PY'
import sys, glob, os, re, statistics
results, ref_a, ref_b, runs = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])

def label_for(ref):
    return "a-" + ref.replace("/", "-")

def medians(label_prefix):
    walls = []
    for path in sorted(glob.glob(os.path.join(results, f"*_{label_prefix}_*.time"))):
        with open(path) as f:
            for line in f:
                if line.startswith("wall_seconds"):
                    walls.append(float(line.split()[1]))
                    break
    return walls

a = medians(label_for(ref_a))
b = medians("b-" + ref_b.replace("/", "-"))
if not a or not b:
    print(f"WARN: missing runs (a={len(a)}, b={len(b)})")
    sys.exit(0)
ma, mb = statistics.median(a), statistics.median(b)
print(f"  {ref_a:>20s}: median {ma:.2f}s   ({len(a)} runs: {[round(x,1) for x in a]})")
print(f"  {ref_b:>20s}: median {mb:.2f}s   ({len(b)} runs: {[round(x,1) for x in b]})")
delta = ma - mb
pct = (delta / ma * 100) if ma else 0
print(f"  delta              : {delta:+.2f}s ({pct:+.1f}%)  (positive = b faster than a)")
PY
