#!/usr/bin/env bash
# evals/rollout/run_rollout.sh — one live fresh-session should-i-buy rollout,
# captured as stream-json (trajectory + final prose).
#
# Usage:
#   ./evals/rollout/run_rollout.sh '<args>' [lang] [label] [model]
# Example:
#   ./evals/rollout/run_rollout.sh AAPL en baseline claude-opus-4-8
#
# Output (gitignored): evals/results/should-i-buy_<label>_<id>_<UTC>.stream.json
# Cost: ~24 Parallax tokens per run (single stock; see token-costs.md).

set -euo pipefail

ARGS="${1:?usage: $0 '<args>' [lang] [label] [model]}"
LANG_ARG="${2:-en}"
LABEL="${3:-$(git rev-parse --short HEAD 2>/dev/null || echo nogit)}"
TARGET_MODEL="${4:-}"
TIMEOUT_SECONDS="${ROLLOUT_TIMEOUT_SECONDS:-900}"
export CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT="${CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT:-0}"

command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RESULTS="$REPO_ROOT/evals/results"
mkdir -p "$RESULTS"

# Skill is parameterized via env so existing should-i-buy callers are unchanged.
#   ROLLOUT_CMD              — slash command to invoke (default /parallax-should-i-buy)
#   ROLLOUT_PREFIX           — output filename prefix   (default should-i-buy)
#   ROLLOUT_TIMEOUT_SECONDS  — kill the rollout process group after N seconds
#                              (default 900); on timeout the partial output is
#                              removed and the script exits 124.
CMD="${ROLLOUT_CMD:-/parallax-should-i-buy}"
PREFIX="${ROLLOUT_PREFIX:-should-i-buy}"

# SAFE_ID is cosmetic only; task identity is parsed from LABEL. Cap it so
# array-valued args such as portfolio JSON do not exceed filesystem filename
# limits.
SAFE_ID=$(printf '%s_%s' "$ARGS" "$LANG_ARG" | tr -c 'A-Za-z0-9._-' '_' | cut -c1-48)
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$RESULTS/${PREFIX}_${LABEL}_${SAFE_ID}_${TS}.stream.json"

PROMPT="$CMD ${ARGS}"
[ "$LANG_ARG" != "en" ] && PROMPT="$PROMPT $LANG_ARG"

echo "[rollout] ~24 Parallax tokens — $PROMPT (label=$LABEL)" >&2

python3 - "$OUT" "$PROMPT" "$TARGET_MODEL" "$TIMEOUT_SECONDS" <<'PY'
import os
import signal
import subprocess
import sys

out, prompt, model, timeout_s = sys.argv[1:5]
cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]
if model:
    cmd.extend(["--model", model])

with open(out, "w") as fh:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=fh,
        text=True,
        start_new_session=True,
    )

try:
    proc.wait(timeout=int(timeout_s))
except subprocess.TimeoutExpired:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()
    try:
        os.unlink(out)
    except OSError:
        pass
    sys.stderr.write(f"rollout timeout after {timeout_s}s: {prompt}\n")
    raise SystemExit(124)

raise SystemExit(proc.returncode)
PY

echo "$OUT"
