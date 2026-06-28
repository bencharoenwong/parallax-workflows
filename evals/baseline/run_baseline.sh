#!/usr/bin/env bash
# evals/baseline/run_baseline.sh — Stage-1 headline deliverable.
# For each core task: n live rollouts; grade Tier-1 (deterministic) + Tier-2
# (pinned judge); aggregate pass-rate + variance into a noise-floor report.
#
# Usage:
#   ./evals/baseline/run_baseline.sh [--skill NAME] [--dry-run] [-n N] [--model M]
# Cost: N * (#tasks) * ~24 Parallax tokens + N*(#tasks)*4 judge calls.
# Default N=3, 4 tasks -> 12 rollouts (~288 tokens). Hard cap below.

set -euo pipefail

N=3
MODEL="claude-opus-4-8"
DRY_RUN=0
SKILL="should-i-buy"
MAX_ROLLOUTS=20   # hard cap — refuse to exceed without editing this file

while [ $# -gt 0 ]; do
  case "$1" in
    --skill) SKILL="$2"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    -n) N="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

SPEC_JSON=$(python3 - "$SKILL" <<'PY'
import json
import sys

sys.path.insert(0, "evals/graders")
from eval_spec import load_spec

spec = load_spec(sys.argv[1])
print(json.dumps({
    "name": spec.name,
    "command": spec.command,
    "tasks_path": spec.tasks_path,
    "prefix": spec.prefix,
}))
PY
)
TASKS=$(printf '%s' "$SPEC_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['tasks_path'])")
CMD=$(printf '%s' "$SPEC_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['command'])")
PREFIX=$(printf '%s' "$SPEC_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['prefix'])")

if [ ! -f "$TASKS" ]; then
  echo "ABORT: skill '$SKILL' has no task file at $TASKS. Add eval tasks before running a baseline." >&2
  exit 1
fi

N_TASKS=$(grep -c . "$TASKS")
TOTAL=$(( N * N_TASKS ))

if [ "$TOTAL" -gt "$MAX_ROLLOUTS" ]; then
  echo "ABORT: $TOTAL rollouts exceeds MAX_ROLLOUTS=$MAX_ROLLOUTS. Lower -n or raise the cap deliberately." >&2
  exit 1
fi

echo "[baseline] skill=$SKILL command=$CMD tasks=$N_TASKS n=$N total_rollouts=$TOTAL est_tokens=$(( TOTAL * 24 )) judge_model=$MODEL" >&2

# Perimeter guard before any work. Runs in --dry-run too (it is an offline string
# check, not a model call), so a bad --model aborts before listing the plan. It
# does require the Python grader env (transcript/judge_criteria) to be importable.
python3 evals/graders/run_judge.py --check-model --model "$MODEL" >/dev/null

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] would run the following, no live calls:" >&2
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    id=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])")
    args=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['args'])")
    lang=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('lang', 'en'))")
    echo "  $CMD $args ${lang:+[$lang]}  task=$id  x$N" >&2
  done < "$TASKS"
  exit 0
fi

TS=$(date -u +%Y%m%dT%H%M%SZ)
REPORT="evals/results/baseline_${SKILL}_${TS}.json"
RUNS_TMP="$(mktemp)"
echo "[]" > "$RUNS_TMP"

while IFS= read -r line; do
  [ -z "$line" ] && continue
  ARGS=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['args'])")
  ID=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['id'])")
  LANG=$(printf '%s' "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('lang', 'en'))")
  for i in $(seq 1 "$N"); do
    STREAM=$(ROLLOUT_CMD="$CMD" ROLLOUT_PREFIX="$PREFIX" evals/rollout/run_rollout.sh "$ARGS" "$LANG" "baseline_${ID}_r${i}" "$MODEL")
    python3 - "$STREAM" "$ID" "$MODEL" "$RUNS_TMP" "$SKILL" <<'PY'
import sys, json
sys.path.insert(0, "evals/graders")
from eval_spec import load_spec
from transcript import load_transcript
from tier1_structural import grade_tier1
from run_judge import grade_tier2
stream, task, model, runs_path, skill = sys.argv[1:6]
spec = load_spec(skill)
t = load_transcript(stream)
t1 = grade_tier1(t, spec)
t1_frac = (sum(c.passed for c in t1) / len(t1)) if t1 else 0.0
t2 = grade_tier2(t, model, spec.tier2_criteria)
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
