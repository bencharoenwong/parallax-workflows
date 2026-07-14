#!/usr/bin/env bash
# evals/rollout/run_corpus.sh — batch live-eval runner over a corpus .jsonl.
#
# One fresh `claude -p` per planned run (correct methodology: SKILL.md is cached at session
# start, so only a cold session honestly exercises a SKILL.md edit). Captures stream-json to
# evals/results/ (gitignored). Supports a repeat count per task so the same thesis can be run
# N times for a VARIANCE pass. Runs the connector preflight first and refuses to spend a token
# if the connector isn't live.
#
# Usage:
#   run_corpus.sh <corpus.jsonl> <label> [plan]
#     plan = comma-separated id[xN] list; default = every id once.
#     e.g.  run_corpus.sh evals/tasks/stress-test-thesis/golden.jsonl live \
#             "macro_led_long x3, weak_thesis, fx_carry_partial"
#
# Connector-access env (see evals/rollout/README.md): MCP_CONFIG / STRICT_MCP / ALLOWED_TOOLS /
# TARGET_MODEL. ROLLOUT_CMD/ROLLOUT_PREFIX default to the stress-test-thesis skill.
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

CORPUS="${1:?usage: run_corpus.sh <corpus.jsonl> <label> [plan]}"
LABEL="${2:?label required}"
PLAN="${3:-}"
[ -f "$CORPUS" ] || { echo "corpus not found: $CORPUS" >&2; exit 5; }

export ROLLOUT_CMD="${ROLLOUT_CMD:-/parallax-stress-test-thesis}"
export ROLLOUT_PREFIX="${ROLLOUT_PREFIX:-stress-test-thesis}"
HERE="evals/rollout"
PY="${PY:-.venv/bin/python3}"

# --- Hard connector gate: never spend on a dead connector -------------------
if ! bash "$HERE/preflight_connector.sh"; then
  echo "[run_corpus] ABORT — connector preflight failed; nothing spent." >&2
  exit 1
fi

# --- Expand the plan into a flat list of task ids ---------------------------
mapfile -t PLAN_ITEMS < <("$PY" - "$CORPUS" "$PLAN" <<'PY'
import json, sys
corpus, plan = sys.argv[1], sys.argv[2]
ids = [json.loads(l)["id"] for l in open(corpus) if l.strip()]
out = []
if plan.strip():
    for tok in plan.split(","):
        tok = tok.strip()
        if not tok:
            continue
        n = 1
        low = tok.lower()
        if "x" in low:
            base, _, cnt = low.rpartition("x")
            if cnt.strip().isdigit():
                tok, n = base.strip(), int(cnt)
        if tok not in ids:
            sys.stderr.write(f"unknown corpus id: {tok}\n"); sys.exit(4)
        out += [tok] * n
else:
    out = ids
print("\n".join(out))
PY
) || { echo "[run_corpus] bad plan" >&2; exit 4; }

[ "${#PLAN_ITEMS[@]}" -gt 0 ] || { echo "[run_corpus] empty plan" >&2; exit 4; }
echo "[run_corpus] ${#PLAN_ITEMS[@]} run(s): ${PLAN_ITEMS[*]}" >&2

# --- Execute one fresh session per planned run ------------------------------
i=0
for id in "${PLAN_ITEMS[@]}"; do
  i=$((i + 1))
  # Build the prompt args, appending client_profile= for profile tasks.
  args="$("$PY" - "$CORPUS" "$id" <<'PY'
import json, sys
corpus, tid = sys.argv[1], sys.argv[2]
t = [x for x in (json.loads(l) for l in open(corpus) if l.strip()) if x["id"] == tid][0]
a = t["args"]
if t.get("profile_args"):
    a += " client_profile=" + json.dumps(t["profile_args"], separators=(",", ":"))
print(a)
PY
)"
  echo "[run_corpus] ($i/${#PLAN_ITEMS[@]}) $id" >&2
  bash "$HERE/run_rollout.sh" "$args" en "${LABEL}-${id}-$i" >/dev/null || \
    echo "[run_corpus] WARN: run $id ($i) exited non-zero (see results/)" >&2
done

echo "[run_corpus] batch complete." >&2
echo "[run_corpus] grade with: $PY evals/graders/grade_corpus.py $LABEL" >&2
