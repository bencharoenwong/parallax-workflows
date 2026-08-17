#!/usr/bin/env bash
# Install the blocking commit-message scan into this clone's pre-push hook.
#
# WHY THIS EXISTS. `scan_commit_messages.py` guards a PUBLIC repo whose commit
# messages are public with it. It was documented as a step to run by hand, and
# on 2026-08-17 that failed: a push ran in a shell line after a FAILED scan
# rather than gated on it, and a flagged message reached the remote before it
# was force-pushed over. A pushed message cannot be unpublished, so the check
# belongs in a hook, not in a habit.
#
# CI cannot do this job: a shallow checkout has no usable base-ref range.
#
# Idempotent. Safe to re-run. Backs up any hook it modifies.

set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "FATAL: not inside a git work tree" >&2; exit 2; }
cd "$ROOT" || exit 2

SCANNER="skills/_parallax/scripts/scan_commit_messages.py"
[ -f "$SCANNER" ] || { echo "FATAL: $SCANNER not found — wrong repo?" >&2; exit 2; }

# Respect a configured hooksPath; fall back to the default.
HOOKS_DIR="$(git config --get core.hooksPath || true)"
[ -n "$HOOKS_DIR" ] || HOOKS_DIR="$(git rev-parse --git-dir)/hooks"
case "$HOOKS_DIR" in /*) ;; *) HOOKS_DIR="$ROOT/$HOOKS_DIR" ;; esac
mkdir -p "$HOOKS_DIR" || exit 2
HOOK="$HOOKS_DIR/pre-push"

MARKER="parallax:commit-message-scan"

if [ -f "$HOOK" ] && grep -q "$MARKER" "$HOOK" 2>/dev/null; then
    echo "  ✓ already installed in $HOOK"
    exit 0
fi

read -r -d '' LAYER <<'LAYER_EOF' || true
# --- parallax:commit-message-scan (BLOCKING) ---------------------------------
# Blocks on BOTH exit codes: 1 = a hit, 2 = the outgoing range could not be
# determined. 2 must block: the scanner fails closed rather than reporting a
# clean scan of nothing. Guarded on the script's presence so this hook stays
# valid in a clone that does not ship it.
_PARALLAX_SCAN="$(git rev-parse --show-toplevel 2>/dev/null)/skills/_parallax/scripts/scan_commit_messages.py"
if [ -f "$_PARALLAX_SCAN" ]; then
    python3 "$_PARALLAX_SCAN"
    _PARALLAX_SCAN_RC=$?
    if [ $_PARALLAX_SCAN_RC -ne 0 ]; then
        printf '\n\033[31m[pre-push] BLOCKED: commit-message scan failed (exit %s).\033[0m\n' "$_PARALLAX_SCAN_RC" >&2
        printf '           Rewrite the message locally before pushing; a pushed message\n' >&2
        printf '           cannot be unpublished. See CLAUDE.md, "Commit messages are public too".\n' >&2
        exit $_PARALLAX_SCAN_RC
    fi
fi
# --- end parallax:commit-message-scan ----------------------------------------
LAYER_EOF

if [ -f "$HOOK" ]; then
    BACKUP="$HOOK.bak.$(git rev-parse --short HEAD 2>/dev/null || echo manual)"
    cp "$HOOK" "$BACKUP" || exit 2
    echo "  backed up existing hook -> $BACKUP"
    # Insert BEFORE the last top-level `exit`, not at the end of the file.
    # Appending looks correct and is not: a hook ending in `exit 0` — which the
    # chained hook in this repo does — leaves the appended layer after the exit,
    # so it is installed, reported as installed, and never runs. That is the
    # same shape as a guard that returns healthy because it never executed.
    #
    # Insertion point is the last line matching a bare top-level exit. If there
    # is none, appending is safe because nothing terminates before it.
    LAST_EXIT="$(grep -n '^[[:space:]]*exit ' "$HOOK" | tail -1 | cut -d: -f1)"
    if [ -n "$LAST_EXIT" ]; then
        HEAD_N=$((LAST_EXIT - 1))
        {
            head -n "$HEAD_N" "$HOOK"
            printf '\n%s\n\n' "$LAYER"
            tail -n +"$LAST_EXIT" "$HOOK"
        } > "$HOOK.new" && mv "$HOOK.new" "$HOOK" || exit 2
    else
        printf '\n%s\n' "$LAYER" >> "$HOOK"
    fi
else
    printf '#!/usr/bin/env bash\nset -uo pipefail\n\n%s\n\nexit 0\n' "$LAYER" > "$HOOK"
fi

chmod +x "$HOOK" || exit 2
bash -n "$HOOK" || { echo "FATAL: hook has a syntax error; restore from the backup" >&2; exit 2; }
echo "  ✓ installed into $HOOK"
echo "  verify with: git push --dry-run <remote> <branch>"
