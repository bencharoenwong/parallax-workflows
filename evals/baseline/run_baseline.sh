#!/usr/bin/env bash
# evals/baseline/run_baseline.sh — Stage-1 headline deliverable.
# For each core task: n live rollouts; grade Tier-1 (deterministic) + Tier-2
# (pinned judge); aggregate pass-rate + variance into a noise-floor report.
#
# Usage:
#   ./evals/baseline/run_baseline.sh [--dry-run] [-n N] [--model M]
# Cost: N * (#tasks) * ~24 Parallax tokens + N*(#tasks)*4 judge calls.
# Default N=3, 4 tasks -> 12 rollouts (~288 tokens). Hard cap below.

set -euo pipefail

N=3
MODEL="claude-opus-4-8"
DRY_RUN=0
MAX_ROLLOUTS=20   # hard cap — refuse to exceed without editing this file

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift;;
    -n) N="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"
TASKS="evals/tasks/should-i-buy/core.jsonl"
N_TASKS=$(grep -c . "$TASKS")
TOTAL=$(( N * N_TASKS ))

if [ "$TOTAL" -gt "$MAX_ROLLOUTS" ]; then
  echo "ABORT: $TOTAL rollouts exceeds MAX_ROLLOUTS=$MAX_ROLLOUTS. Lower -n or raise the cap deliberately." >&2
  exit 1
fi

echo "[baseline] tasks=$N_TASKS n=$N total_rollouts=$TOTAL est_tokens=$(( TOTAL * 24 )) judge_model=$MODEL" >&2

# Perimeter guard before any work.
python3 evals/graders/run_judge.py --check-model --model "$MODEL" >/dev/null

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] would run the following, no live calls:" >&2
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    id=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])")
    echo "  task=$id  x$N" >&2
  done < "$TASKS"
  exit 0
fi

TS=$(date -u +%Y%m%dT%H%M%SZ)
REPORT="evals/results/baseline_should-i-buy_${TS}.json"
RUNS_TMP="$(mktemp)"
echo "[]" > "$RUNS_TMP"

while IFS= read -r line; do
  [ -z "$line" ] && continue
  ARGS=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['args'])")
  ID=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])")
  for i in $(seq 1 "$N"); do
    STREAM=$(evals/rollout/run_rollout.sh "$ARGS" en "baseline_${ID}_r${i}" "$MODEL")
    python3 - "$STREAM" "$ID" "$MODEL" "$RUNS_TMP" <<'PY'
import sys, json
sys.path.insert(0, "evals/graders")
from transcript import load_transcript
from tier1_structural import grade_tier1
from run_judge import grade_tier2
stream, task, model, runs_path = sys.argv[1:5]
t = load_transcript(stream)
t1 = grade_tier1(t)
t1_frac = sum(c.passed for c in t1) / len(t1)
t2 = grade_tier2(t, model)
scored = [v for v in t2 if v["pass"] is not None]
t2_frac = (sum(1 for v in scored if v["pass"]) / len(scored)) if scored else 0.0
runs = json.load(open(runs_path))
runs.append({"task": task, "tier1": t1_frac, "tier2": t2_frac})
json.dump(runs, open(runs_path, "w"))
PY
  done
done < "$TASKS"

python3 - "$RUNS_TMP" "$REPORT" <<'PY'
import sys, json
sys.path.insert(0, "evals/baseline")
from aggregate_report import summarize
runs = json.load(open(sys.argv[1]))
report = summarize(runs)
report["runs"] = runs
json.dump(report, open(sys.argv[2], "w"), indent=2)
print(json.dumps(report["overall"], indent=2))
print("below_ceiling:", report["below_ceiling"])
PY
rm -f "$RUNS_TMP"
echo "[baseline] report: $REPORT" >&2
