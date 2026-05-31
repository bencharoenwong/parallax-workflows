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

command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RESULTS="$REPO_ROOT/evals/results"
mkdir -p "$RESULTS"

# Skill is parameterized via env so existing should-i-buy callers are unchanged.
#   ROLLOUT_CMD    — slash command to invoke (default /parallax-should-i-buy)
#   ROLLOUT_PREFIX — output filename prefix   (default should-i-buy)
CMD="${ROLLOUT_CMD:-/parallax-should-i-buy}"
PREFIX="${ROLLOUT_PREFIX:-should-i-buy}"

SAFE_ID=$(printf '%s_%s' "$ARGS" "$LANG_ARG" | tr -c 'A-Za-z0-9._-' '_')
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$RESULTS/${PREFIX}_${LABEL}_${SAFE_ID}_${TS}.stream.json"

PROMPT="$CMD ${ARGS}"
[ "$LANG_ARG" != "en" ] && PROMPT="$PROMPT $LANG_ARG"

echo "[rollout] ~24 Parallax tokens — $PROMPT (label=$LABEL)" >&2

MODEL_FLAG=()
[ -n "$TARGET_MODEL" ] && MODEL_FLAG=(--model "$TARGET_MODEL")

claude -p "$PROMPT" \
  --output-format stream-json --verbose \
  ${MODEL_FLAG[@]+"${MODEL_FLAG[@]}"} \
  < /dev/null > "$OUT"

echo "$OUT"
