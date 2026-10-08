#!/usr/bin/env bash
# evals/concierge_journeys.sh — live journey tests for the concierge's
# New-here path (see evals/README.md "Live concierge journeys").
#
# These run a REAL model via `claude -p` against the plugin's bundled
# Parallax connector (or an existing signed-in one). They are owner-run,
# pre-release checks, NOT CI tests: they bill Parallax credits and take real
# wall-clock time.
#
# Usage:
#   PARALLAX_E2E_LIVE=1 bash evals/concierge_journeys.sh
#
# Env:
#   PARALLAX_E2E_LIVE            Required to run for real. Unset/not "1" =>
#                                 print a skip message and exit 0.
#   PARALLAX_E2E_DRY_RUN          "1" => print each `claude` command instead
#                                 of running it (no credits spent, no model
#                                 call). Takes effect even without
#                                 PARALLAX_E2E_LIVE=1.
#   PARALLAX_E2E_ALLOWED_TOOLS    --allowedTools pattern for the Parallax
#                                 connector. Default: "mcp__parallax__*" —
#                                 the plugin's bundled MCP server key (see
#                                 plugin/.mcp.json). If you're exercising a
#                                 different signed-in connector instead (for
#                                 example a claude.ai OAuth connector named
#                                 "Parallax"), its tool names are namespaced
#                                 differently — try
#                                 "mcp__claude_ai_Parallax__*" (see the
#                                 connector-access contract in
#                                 evals/rollout/README.md) and override this
#                                 var accordingly.
#
# Journeys are defined in evals/tasks/concierge/journeys.jsonl, one JSON
# object per line:
#   {"id", "prompt", "expect": [...], "forbid": [...], "expect_any"?: [...],
#    "needs"?: "no-connector"}
# "needs": "no-connector" runs with --strict-mcp-config and an empty
# --mcp-config, simulating a disconnected host (no Parallax tools reachable
# at all) instead of the plugin's bundled connector.
#
# Every journey also runs with --plugin-dir "$PLUGIN_DIR" and
# --setting-sources project, so the test exercises this branch's built
# plugin copy and not whatever skills/settings happen to be installed under
# ~/.claude on the machine running this script.
#
# The expect/forbid/expect_any check itself lives in
# evals/concierge_journeys_check.py (pytested at
# evals/graders/test_concierge_journeys_check.py) so the matching logic is
# not duplicated between this script and its tests.
#
# Results (gitignored) land at evals/results/concierge_<id>_<UTC-ts>.txt.

set -uo pipefail

DRY_RUN="${PARALLAX_E2E_DRY_RUN:-}"

if [ "$DRY_RUN" != "1" ] && [ "${PARALLAX_E2E_LIVE:-}" != "1" ]; then
  echo "SKIP: PARALLAX_E2E_LIVE not set to 1 — live concierge journeys do not run by default (they bill Parallax credits). See evals/README.md 'Live concierge journeys'. Set PARALLAX_E2E_DRY_RUN=1 to preview the commands for free."
  exit 0
fi

command -v python3 >/dev/null || { echo "python3 not on PATH" >&2; exit 1; }
if [ "$DRY_RUN" != "1" ]; then
  command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
JOURNEYS="$REPO_ROOT/evals/tasks/concierge/journeys.jsonl"
CHECK="$REPO_ROOT/evals/concierge_journeys_check.py"
RESULTS="$REPO_ROOT/evals/results"
PLUGIN_DIR="$REPO_ROOT/plugin"
ALLOWED_TOOLS="${PARALLAX_E2E_ALLOWED_TOOLS:-mcp__parallax__*}"

[ -f "$JOURNEYS" ] || { echo "journeys file not found: $JOURNEYS" >&2; exit 1; }
[ -f "$CHECK" ] || { echo "checker not found: $CHECK" >&2; exit 1; }
mkdir -p "$RESULTS"

# Async Parallax tools (get_news_synthesis, get_assessment, ...) can poll
# past the default MCP idle timeout in a non-interactive session; match
# evals/rollout/run_rollout.sh's convention of disabling it for live runs.
export CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT="${CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT:-0}"

jfield() {
  # jfield <json-line> <key> — extract a scalar string field, "" if absent/null.
  python3 -c '
import json, sys
d = json.loads(sys.argv[1])
v = d.get(sys.argv[2], "")
print("" if v is None else v)
' "$1" "$2"
}

TOTAL=0
FAILS=0

while IFS= read -r LINE || [ -n "$LINE" ]; do
  [ -z "$LINE" ] && continue
  case "$LINE" in
    \#*) continue ;;
  esac

  ID=$(jfield "$LINE" id)
  PROMPT=$(jfield "$LINE" prompt)
  NEEDS=$(jfield "$LINE" needs)
  TOTAL=$((TOTAL + 1))

  XFLAGS=(--plugin-dir "$PLUGIN_DIR" --setting-sources project)
  if [ "$NEEDS" = "no-connector" ]; then
    XFLAGS+=(--strict-mcp-config --mcp-config '{"mcpServers":{}}')
  else
    XFLAGS+=(--allowedTools "$ALLOWED_TOOLS")
  fi

  CMD=(claude -p "$PROMPT" --output-format text "${XFLAGS[@]}")

  if [ "$DRY_RUN" = "1" ]; then
    printf '[%s] DRY RUN: ' "$ID"
    printf '%q ' "${CMD[@]}"
    printf '\n'
    continue
  fi

  TS=$(date -u +%Y%m%dT%H%M%SZ)
  OUT="$RESULTS/concierge_${ID}_${TS}.txt"
  # < /dev/null: a bare claude -p with a prompt arg still reads stdin if any
  # is attached, and without this the while-loop's own input (the journeys
  # file) feeds the next journey's prompt into this one's stdin instead.
  "${CMD[@]}" < /dev/null > "$OUT" 2>&1 || true

  if CHECK_OUT=$(python3 "$CHECK" "$LINE" < "$OUT" 2>&1); then
    echo "PASS: $ID"
  else
    FAILS=$((FAILS + 1))
    echo "FAIL: $ID"
    echo "$CHECK_OUT" | sed 's/^/  /'
    echo "  output: $OUT"
  fi
done < "$JOURNEYS"

if [ "$DRY_RUN" = "1" ]; then
  exit 0
fi

echo "---"
echo "Total: $TOTAL, Failed: $FAILS"
[ "$TOTAL" -gt 0 ] && [ "$FAILS" -eq 0 ]
