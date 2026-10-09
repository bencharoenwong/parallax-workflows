#!/usr/bin/env bash
# evals/concierge_journeys.sh — live journey tests for the concierge's
# New-here path (see evals/README.md "Live concierge journeys").
#
# These run a REAL model via `claude -p` against a signed-in Parallax
# connector. They are owner-run, pre-release checks, NOT CI tests: most of
# them bill Parallax credits and take real wall-clock time.
#
# Usage:
#   PARALLAX_E2E_LIVE=1 bash evals/concierge_journeys.sh
#   PARALLAX_E2E_LIVE=1 PARALLAX_E2E_ONLY=J2,J3,J5,J8 bash evals/concierge_journeys.sh
#
# Env:
#   PARALLAX_E2E_LIVE            Required to run for real. Unset/not "1" =>
#                                 print a skip message and exit 0.
#   PARALLAX_E2E_DRY_RUN          "1" => print each `claude` command instead
#                                 of running it (no credits, no model call).
#                                 Takes effect even without PARALLAX_E2E_LIVE.
#   PARALLAX_E2E_ONLY             Comma-separated journey ids to run. Each
#                                 entry matches a full id or the part before
#                                 its first "_" (J2 matches J2_not_connected).
#   PARALLAX_E2E_CONNECTOR        account (default) | plugin.
#                                 account: the Parallax connector on your
#                                 claude.ai account, or one added with
#                                 `claude mcp add`; allows
#                                 mcp__claude_ai_Parallax__* and
#                                 mcp__parallax__*. When the account has the
#                                 connector, Claude Code drops the plugin's
#                                 bundled copy.
#                                 plugin: the plugin's bundled server. Sets
#                                 ENABLE_CLAUDEAI_MCP_SERVERS=false for the run
#                                 and allows mcp__plugin_parallax_parallax__*.
#                                 Needs a one-time `/mcp` sign-in to that
#                                 server and the server-side loopback sign-in
#                                 fix.
#   PARALLAX_E2E_ALLOWED_TOOLS    Overrides the Parallax tool patterns the
#                                 connector mode picks (comma-separated).
#                                 Read, Grep, Glob and Write/Edit inside the
#                                 scratch tree are always allowed on top.
#                                 Bash runs only inside the sandbox.
#   PARALLAX_E2E_TIMEOUT          Per-journey limit in seconds (default 600).
#                                 A timeout is a FAIL.
#
# Journeys are defined in evals/tasks/concierge/journeys.jsonl, one JSON
# object per line:
#   {"id", "prompt", "expect"?: [...], "forbid"?: [...], "expect_any"?: [...],
#    "needs"?: "no-connector" | "connector-optional",
#    "skill"?: "parallax:<skill>"  (default parallax:parallax-concierge)}
# Every line is validated before any `claude` call; an invalid line aborts.
# "needs": "no-connector" runs with claude.ai connectors disabled,
# --strict-mcp-config and an empty --mcp-config, so no Parallax server loads.
# "needs": "connector-optional" runs like a connector journey but skips only
# the Parallax-server-presence check (for a journey that calls no Parallax
# tool; a claude.ai connector may be missing from the init message).
#
# Each journey runs from a fresh scratch directory (mktemp -d), so the repo's
# CLAUDE.md and source files are out of reach, with --plugin-dir pointing at
# this branch's built plugin/ (absolute path) and --setting-sources project so
# user-level skills and settings stay out. HOME is a scratch home that holds
# only symlinks to ~/.claude, ~/.claude.json and, on macOS,
# ~/Library/Keychains (sign-in and connectors still load), so local Parallax
# config under ~/.parallax, such as white-label branding, never reaches a
# report. PARALLAX_HOUSE_VIEW_DIR is an empty scratch directory, and TMPDIR
# and CLAUDE_CODE_TMPDIR are inside the scratch tree. Shell commands run in
# Claude Code's Bash sandbox with no network and writes only inside the
# scratch tree (see SANDBOX_SETTINGS below).
#
# The run fails closed (evals/concierge_journeys_check.py): any
# permission_denials in the result, a missing/errored result, a non-zero
# exit, a timeout, no successful Skill call of the journey's required skill,
# no skill from the parallax: plugin namespace, a Parallax skill called
# without the parallax: prefix,
# an init message that does not list this plugin directory, a connector
# journey with no connected Parallax server at init and no successful Parallax
# tool call, or a no-connector journey that shows a Parallax server or calls
# a Parallax tool is a FAIL, whatever the text says. expect/expect_any run on
# the final answer; forbid runs on all assistant text in the run.
#
# Results (gitignored) land in evals/results/: concierge_<id>_<UTC-ts>.jsonl
# (raw stream), .txt (all assistant text) and .stderr. INT/TERM stops the
# running claude and removes its scratch directory.

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
JOURNEYS="$REPO_ROOT/evals/tasks/concierge/journeys.jsonl"
CHECK="$REPO_ROOT/evals/concierge_journeys_check.py"
RESULTS="$REPO_ROOT/evals/results"
PLUGIN_DIR="$REPO_ROOT/plugin"
TIMEOUT="${PARALLAX_E2E_TIMEOUT:-600}"
ONLY="${PARALLAX_E2E_ONLY:-}"
CONNECTOR="${PARALLAX_E2E_CONNECTOR:-account}"

case "$TIMEOUT" in
  ''|*[!0-9]*) echo "PARALLAX_E2E_TIMEOUT must be a positive integer: $TIMEOUT" >&2; exit 1 ;;
esac

# CONN_ENV: env assignments for connector journeys (run through `env`).
case "$CONNECTOR" in
  account)
    DEFAULT_TOOLS="mcp__claude_ai_Parallax__*,mcp__parallax__*"
    CONN_ENV=()
    ;;
  plugin)
    DEFAULT_TOOLS="mcp__plugin_parallax_parallax__*"
    CONN_ENV=(ENABLE_CLAUDEAI_MCP_SERVERS=false)
    ;;
  *)
    echo "PARALLAX_E2E_CONNECTOR must be account or plugin: $CONNECTOR" >&2
    exit 1
    ;;
esac
ALLOWED_TOOLS="${PARALLAX_E2E_ALLOWED_TOOLS:-$DEFAULT_TOOLS}"
# Allowed in every journey: --setting-sources project drops user-level
# permissions, and routed skills read the plugin's shared files. Write/Edit is
# added per journey, limited to the scratch tree. Bash has no allow rule: it
# runs only inside Claude Code's Bash sandbox (SANDBOX_SETTINGS below), which
# auto-allows a sandboxed command and lets the OS confine it.
BASE_TOOLS="Read,Grep,Glob"
# Bash sandbox (code.claude.com/docs/en/sandboxing). The OS (Seatbelt on
# macOS) confines every shell command and its child processes:
# - writes only to the cwd (the scratch tree) and the per-user temp dir,
#   which CLAUDE_CODE_TMPDIR puts inside the scratch tree; Claude Code's
#   protected paths (~/.claude, ~/.claude.json) stay write-denied even
#   through the scratch home's symlinks;
# - no network: allowedDomains is empty and strictAllowlist refuses other
#   hosts (Parallax calls go through MCP, not Bash);
# - allowUnsandboxedCommands false ignores dangerouslyDisableSandbox, so there
#   is no unsandboxed retry; failIfUnavailable refuses to start without the
#   sandbox instead of running commands unsandboxed.
# No --add-dir: an added directory would become writable to sandboxed
# commands, and the plugin must stay read-only.
SANDBOX_SETTINGS='{"sandbox":{"enabled":true,"failIfUnavailable":true,"autoAllowBashIfSandboxed":true,"allowUnsandboxedCommands":false,"network":{"allowedDomains":[],"strictAllowlist":true}}}'
REAL_HOME="$HOME"

[ -f "$JOURNEYS" ] || { echo "journeys file not found: $JOURNEYS" >&2; exit 1; }
[ -f "$CHECK" ] || { echo "checker not found: $CHECK" >&2; exit 1; }
[ -d "$PLUGIN_DIR" ] || { echo "plugin dir not found: $PLUGIN_DIR" >&2; exit 1; }
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

selected() {
  # selected <id> — 0 if PARALLAX_E2E_ONLY is empty or names this id.
  [ -z "$ONLY" ] && return 0
  local entry
  local IFS=,
  for entry in $ONLY; do
    if [ "$entry" = "$1" ] || [ "$entry" = "${1%%_*}" ]; then
      return 0
    fi
  done
  return 1
}

# Validate every line first, so a malformed journey never costs a model call.
BAD=0
ALL_IDS=""
while IFS= read -r LINE || [ -n "$LINE" ]; do
  [ -z "$LINE" ] && continue
  case "$LINE" in \#*) continue ;; esac
  if ! VOUT=$(python3 "$CHECK" --validate "$LINE" 2>&1); then
    BAD=1
    echo "invalid journey line: $LINE" >&2
    echo "$VOUT" | sed 's/^/  /' >&2
  else
    ALL_IDS="$ALL_IDS $(jfield "$LINE" id)"
  fi
done < "$JOURNEYS"
[ "$BAD" -eq 0 ] || exit 1

for ENTRY in $(printf '%s' "$ONLY" | tr ',' ' '); do
  MATCHED=0
  for JID in $ALL_IDS; do
    if [ "$ENTRY" = "$JID" ] || [ "$ENTRY" = "${JID%%_*}" ]; then MATCHED=1; fi
  done
  [ "$MATCHED" -eq 1 ] || echo "WARNING: PARALLAX_E2E_ONLY entry matched no journey: $ENTRY" >&2
done

TOTAL=0
FAILS=0
PID=""
SCRATCH=""

cleanup() {
  # Stop a running claude and its children, drop the scratch dir.
  if [ -n "$PID" ]; then
    pkill -TERM -P "$PID" 2>/dev/null
    kill -TERM "$PID" 2>/dev/null
    sleep 1
    pkill -KILL -P "$PID" 2>/dev/null
    kill -KILL "$PID" 2>/dev/null
    PID=""
  fi
  if [ -n "$SCRATCH" ]; then
    rm -rf "$SCRATCH"
    SCRATCH=""
  fi
}
trap 'cleanup; echo "interrupted" >&2; exit 130' INT TERM HUP
trap cleanup EXIT

while IFS= read -r LINE || [ -n "$LINE" ]; do
  [ -z "$LINE" ] && continue
  case "$LINE" in \#*) continue ;; esac

  ID=$(jfield "$LINE" id)
  selected "$ID" || continue
  PROMPT=$(jfield "$LINE" prompt)
  NEEDS=$(jfield "$LINE" needs)
  TOTAL=$((TOTAL + 1))

  # Scratch layout (cwd = $SCRATCH): home/ holds only symlinks to the real
  # ~/.claude, ~/.claude.json and (macOS) ~/Library/Keychains, so sign-in and
  # connectors still load but ~/.parallax (local branding and house views) is
  # absent; house-view/ is an empty PARALLAX_HOUSE_VIEW_DIR; tmp/ is TMPDIR
  # and the sandbox's per-user temp dir.
  if [ "$DRY_RUN" = "1" ]; then
    SCR="<scratch>"
    SCR_REAL="<scratch>"
  else
    SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/concierge_e2e.XXXXXX")
    [ -n "$SCRATCH" ] && [ -d "$SCRATCH" ] || { echo "mktemp -d failed" >&2; exit 1; }
    SCR="$SCRATCH"
    SCR_REAL=$(cd "$SCRATCH" && pwd -P)
    mkdir -p "$SCRATCH/home" "$SCRATCH/house-view" "$SCRATCH/tmp"
    ln -s "$REAL_HOME/.claude" "$SCRATCH/home/.claude"
    [ -e "$REAL_HOME/.claude.json" ] && ln -s "$REAL_HOME/.claude.json" "$SCRATCH/home/.claude.json"
    # macOS keeps the Claude Code login in the login keychain, which is found
    # through $HOME/Library/Keychains; without it the run is "Not logged in".
    if [ -d "$REAL_HOME/Library/Keychains" ]; then
      mkdir -p "$SCRATCH/home/Library"
      ln -s "$REAL_HOME/Library/Keychains" "$SCRATCH/home/Library/Keychains"
    fi
  fi
  # Write/Edit only inside the scratch tree, under both path spellings
  # (/var/folders/... and /private/var/folders/... on macOS).
  EDIT_RULES="Edit(/$SCR/**)"
  [ "$SCR_REAL" != "$SCR" ] && EDIT_RULES="$EDIT_RULES,Edit(/$SCR_REAL/**)"
  ISO_ENV=(HOME="$SCR/home" TMPDIR="$SCR/tmp" CLAUDE_CODE_TMPDIR="$SCR/tmp"
           PARALLAX_HOUSE_VIEW_DIR="$SCR/house-view")

  if [ "$NEEDS" = "no-connector" ]; then
    RUN_ENV=(ENABLE_CLAUDEAI_MCP_SERVERS=false)
    # --allowedTools takes a variadic list, so it goes last.
    XFLAGS=(--strict-mcp-config --mcp-config '{"mcpServers":{}}' --allowedTools "$BASE_TOOLS,$EDIT_RULES")
  else
    RUN_ENV=(${CONN_ENV[@]+"${CONN_ENV[@]}"})
    XFLAGS=(--allowedTools "$BASE_TOOLS,$EDIT_RULES,$ALLOWED_TOOLS")
  fi

  CMD=(env "${ISO_ENV[@]}" ${RUN_ENV[@]+"${RUN_ENV[@]}"} claude -p "$PROMPT"
       --output-format stream-json --verbose
       --plugin-dir "$PLUGIN_DIR"
       --setting-sources project --settings "$SANDBOX_SETTINGS" "${XFLAGS[@]}")

  if [ "$DRY_RUN" = "1" ]; then
    printf '[%s] DRY RUN (cwd: <scratch> = fresh mktemp -d, timeout %ss): ' "$ID" "$TIMEOUT"
    printf '%q ' "${CMD[@]}"
    printf '\n'
    continue
  fi

  TS=$(date -u +%Y%m%dT%H%M%SZ)
  RAW="$RESULTS/concierge_${ID}_${TS}.jsonl"
  TXT="$RESULTS/concierge_${ID}_${TS}.txt"
  ERR="$RESULTS/concierge_${ID}_${TS}.stderr"

  # exec replaces the subshell, so $PID is claude itself and the kill below
  # reaches it. < /dev/null keeps the journeys file off claude's stdin.
  ( cd "$SCRATCH" && exec "${CMD[@]}" ) < /dev/null > "$RAW" 2> "$ERR" &
  PID=$!
  ELAPSED=0
  TIMED_OUT=0
  while kill -0 "$PID" 2>/dev/null; do
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
      TIMED_OUT=1
      pkill -TERM -P "$PID" 2>/dev/null
      kill -TERM "$PID" 2>/dev/null
      sleep 3
      pkill -KILL -P "$PID" 2>/dev/null
      kill -KILL "$PID" 2>/dev/null
      break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
  done
  wait "$PID" 2>/dev/null
  RC=$?
  PID=""
  rm -rf "$SCRATCH"
  SCRATCH=""

  CHECK_ARGS=("$LINE" --stream "$RAW" --exit-code "$RC" --plugin-dir "$PLUGIN_DIR" --text-out "$TXT")
  [ "$TIMED_OUT" -eq 1 ] && CHECK_ARGS+=(--timed-out)

  if CHECK_OUT=$(python3 "$CHECK" "${CHECK_ARGS[@]}" 2>&1); then
    echo "PASS: $ID"
    echo "$CHECK_OUT" | grep -v '^PASS$' | sed 's/^/  /'
  else
    FAILS=$((FAILS + 1))
    echo "FAIL: $ID"
    echo "$CHECK_OUT" | sed 's/^/  /'
  fi
  echo "  text: $TXT"
  echo "  stream: $RAW"
done < "$JOURNEYS"

if [ "$DRY_RUN" = "1" ]; then
  exit 0
fi

echo "---"
echo "Total: $TOTAL, Failed: $FAILS"
[ "$TOTAL" -gt 0 ] && [ "$FAILS" -eq 0 ]
