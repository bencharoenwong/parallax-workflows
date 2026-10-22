#!/usr/bin/env bash
# evals/rollout/preflight_connector.sh — HARD GATE before any live batch spends tokens.
#
# Verifies that a fresh `claude -p` session (1) authenticates and (2) actually loads the
# Parallax connector, by asking it to run one trivial check_api_health probe. Exits 0 only when both
# hold; non-zero with a precise reason otherwise.
#
# Why this exists: a spawned `claude -p` that lacks credentials returns HTTP 401 with an
# EMPTY report, and an empty transcript grades as a skill failure — silently blaming the
# skill for an infrastructure gap. This gate turns that into a loud, correct preflight abort.
#
# Env (see evals/rollout/README.md — the "connector-access contract"):
#   MCP_CONFIG     path(s) to a .mcp.json defining the Parallax server   (--mcp-config)
#   STRICT_MCP     non-empty => --strict-mcp-config
#   ALLOWED_TOOLS  tool allowlist, e.g. "mcp__claude_ai_Parallax__*"
#   TARGET_MODEL   optional model pin
set -uo pipefail

command -v claude >/dev/null || { echo "PREFLIGHT FAIL: claude CLI not on PATH" >&2; exit 3; }

MFLAG=(); [ -n "${TARGET_MODEL:-}" ] && MFLAG=(--model "$TARGET_MODEL")
XFLAG=()
[ -n "${MCP_CONFIG:-}" ]    && XFLAG+=(--mcp-config ${MCP_CONFIG})
[ -n "${STRICT_MCP:-}" ]    && XFLAG+=(--strict-mcp-config)
[ -n "${ALLOWED_TOOLS:-}" ] && XFLAG+=(--allowedTools ${ALLOWED_TOOLS})

TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT

claude -p "Call the Parallax check_api_health tool exactly once and report only whether it succeeded. Do nothing else." \
  --output-format stream-json --verbose \
  ${MFLAG[@]+"${MFLAG[@]}"} ${XFLAG[@]+"${XFLAG[@]}"} \
  < /dev/null > "$TMP" 2>&1 || true

# 1) Authentication
if grep -qE '"error_status":401|authentication_failed|Invalid authentication' "$TMP"; then
  echo "PREFLIGHT FAIL: authentication error (401) — the claude -p session has no valid credentials." >&2
  echo "  fix: export ANTHROPIC_API_KEY (or run from a logged-in session) in the runner env." >&2
  exit 1
fi
# 2) Connector loaded (init event lists a Parallax MCP server)
if ! grep -oE '"mcp_servers":\[[^]]*\]' "$TMP" | grep -qi 'parallax'; then
  echo "PREFLIGHT FAIL: no Parallax MCP server loaded (mcp_servers empty or missing Parallax)." >&2
  echo "  fix: set MCP_CONFIG to a .mcp.json defining the Parallax server (see evals/rollout/README.md)." >&2
  exit 2
fi
# 3) The probe tool actually ran (connector reachable, not just declared)
if ! grep -qE '"name"[[:space:]]*:[[:space:]]*"mcp__[^"]*check_api_health"' "$TMP"; then
  echo "PREFLIGHT FAIL: Parallax connector declared but the check_api_health probe never executed (tool blocked or unreachable)." >&2
  echo "  fix: ensure ALLOWED_TOOLS permits the Parallax tools so a non-interactive run can call them." >&2
  exit 4
fi

echo "PREFLIGHT OK: Parallax connector loaded and authenticated; check_api_health probe responded." >&2
exit 0
