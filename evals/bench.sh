#!/usr/bin/env bash
# evals/bench.sh — time a single fresh-session skill invocation.
#
# Usage:
#   ./evals/bench.sh "<prompt>" [label]
#
# Example:
#   ./evals/bench.sh "/parallax-morning-brief $(cat evals/portfolios/small_5.json)" pre-fix
#
# Output (gitignored): evals/results/<sanitized-skill>_<label>_<UTC-timestamp>.{out,time}

set -euo pipefail

PROMPT="${1:?usage: $0 \"<prompt>\" [label]}"
LABEL="${2:-$(git rev-parse --short HEAD 2>/dev/null || echo nogit)}"

command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RESULTS="$REPO_ROOT/evals/results"
mkdir -p "$RESULTS"

# Extract a sanitized skill tag from the prompt for the filename
SKILL_TAG=$(printf '%s' "$PROMPT" | grep -oE '/parallax-[a-z0-9-]+' | head -1 | sed 's|^/parallax-||' || echo prompt)
[ -z "$SKILL_TAG" ] && SKILL_TAG=prompt

TS=$(date -u +%Y%m%dT%H%M%SZ)
STEM="$RESULTS/${SKILL_TAG}_${LABEL}_${TS}"
OUT="$STEM.out"
TIMEFILE="$STEM.time"

echo "[$(date -u +%H:%M:%S)Z] running ($SKILL_TAG, label=$LABEL)..."

# /usr/bin/time is more parseable than the bash builtin
TIME_BIN="/usr/bin/time"
if [ ! -x "$TIME_BIN" ]; then
  TIME_BIN=time
fi

# capture wall-clock with the builtin if /usr/bin/time isn't available
if [ "$TIME_BIN" = "time" ]; then
  START=$(date +%s.%N)
  claude -p "$PROMPT" > "$OUT" 2>&1 || true
  END=$(date +%s.%N)
  python3 -c "print(f'wall_seconds: {$END - $START:.2f}')" > "$TIMEFILE"
else
  "$TIME_BIN" -f 'wall_seconds: %e\nuser_seconds: %U\nsys_seconds: %S\nmax_rss_kb: %M' \
    -o "$TIMEFILE" \
    claude -p "$PROMPT" > "$OUT" 2>&1 || true
fi

WALL=$(grep -E '^wall_seconds' "$TIMEFILE" | awk '{print $2}')
BYTES=$(wc -c < "$OUT" | tr -d ' ')

echo "[$(date -u +%H:%M:%S)Z] done in ${WALL}s — output ${BYTES} bytes"
echo "  $OUT"
echo "  $TIMEFILE"
