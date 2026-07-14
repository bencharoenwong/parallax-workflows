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

# Bound the id: short-ticker skills (should-i-buy "AAPL") slug fine, but free-text
# skills (a thesis paragraph) would overflow the 255-byte filename limit. Cap the
# slug and append a stable hash of the full args so ids stay unique + readable.
RAW_ID=$(printf '%s_%s' "$ARGS" "$LANG_ARG" | tr -c 'A-Za-z0-9._-' '_')
ARGS_HASH=$(printf '%s_%s' "$ARGS" "$LANG_ARG" | cksum | cut -d' ' -f1)
SAFE_ID="$(printf '%.60s' "$RAW_ID")_${ARGS_HASH}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$RESULTS/${PREFIX}_${LABEL}_${SAFE_ID}_${TS}.stream.json"

PROMPT="$CMD ${ARGS}"
[ "$LANG_ARG" != "en" ] && PROMPT="$PROMPT $LANG_ARG"

echo "[rollout] ~24 Parallax tokens — $PROMPT (label=$LABEL)" >&2

MODEL_FLAG=()
[ -n "$TARGET_MODEL" ] && MODEL_FLAG=(--model "$TARGET_MODEL")

# Live-connector flags (CI / live-eval use). All optional — unset leaves behavior
# unchanged, so existing should-i-buy callers are unaffected. See evals/rollout/README.md.
#   MCP_CONFIG    — path(s) to a .mcp.json defining the Parallax server (--mcp-config)
#   STRICT_MCP    — non-empty => --strict-mcp-config (ONLY the supplied servers load: reproducible)
#   ALLOWED_TOOLS — tool allowlist so a non-interactive run never stalls on a permission
#                   prompt (e.g. "mcp__claude_ai_Parallax__*")
EXTRA_FLAGS=()
[ -n "${MCP_CONFIG:-}" ]    && EXTRA_FLAGS+=(--mcp-config ${MCP_CONFIG})
[ -n "${STRICT_MCP:-}" ]    && EXTRA_FLAGS+=(--strict-mcp-config)
[ -n "${ALLOWED_TOOLS:-}" ] && EXTRA_FLAGS+=(--allowedTools ${ALLOWED_TOOLS})

claude -p "$PROMPT" \
  --output-format stream-json --verbose \
  ${MODEL_FLAG[@]+"${MODEL_FLAG[@]}"} \
  ${EXTRA_FLAGS[@]+"${EXTRA_FLAGS[@]}"} \
  < /dev/null > "$OUT"

echo "$OUT"
