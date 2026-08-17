#!/usr/bin/env bash
# Install the blocking commit-message scan into this clone's pre-push hook.
#
# WHY THIS EXISTS. `scan_commit_messages.py` guards a PUBLIC repo whose commit
# messages are public with it. Running it by hand failed once: a push ran in a
# shell line after a FAILED scan rather than gated on its exit code. A pushed
# message cannot be unpublished, so the check belongs in a hook.
#
# CI cannot do this job: a shallow checkout has no usable base-ref range.
#
# DESIGN: THE LAYER IS PREPENDED, NOT APPENDED.
# The first version searched for the hook's last `exit ` and inserted above it.
# That was wrong in five separate ways, each of which printed "installed" while
# a real push went through unscanned:
#   - an `exit` indented inside an `if` body matched, so the layer landed in a
#     branch that does not always run
#   - a hook ending in a bare `exit` (no trailing space) did not match at all
#   - a hook ending in `exec ...` never reaches anything appended after it
#   - appending discarded the original hook's exit status, silently disabling
#     a gate the user already had
#   - a `core.hooksPath` of `~/hooks` was not tilde-expanded, so the layer was
#     written to a literal `~` directory inside the work tree
#
# Prepending immediately after the shebang removes that whole class: the layer
# is the first executable statement, so it is reachable by construction, and
# the original hook body runs after it with its exit status intact.
#
# Idempotent. Refuses rather than guesses. Backs up any hook it modifies.

set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "FATAL: not inside a git work tree" >&2; exit 2; }
cd "$ROOT" || exit 2

SCANNER="skills/_parallax/scripts/scan_commit_messages.py"
[ -f "$SCANNER" ] || { echo "FATAL: $SCANNER not found — wrong repo?" >&2; exit 2; }

# `git rev-parse --git-path hooks` resolves core.hooksPath correctly, including
# a leading `~` and a relative path. `git config --get core.hooksPath` does not
# expand `~`, which is how the first version wrote into a literal `~` directory.
HOOKS_DIR="$(git rev-parse --git-path hooks 2>/dev/null)"
[ -n "$HOOKS_DIR" ] || { echo "FATAL: cannot resolve hooks dir" >&2; exit 2; }
case "$HOOKS_DIR" in /*) ;; *) HOOKS_DIR="$ROOT/$HOOKS_DIR" ;; esac

# Resolve symlinks before the inside-the-repo test below. That test is a string
# prefix match, so a SYMLINKED hooks directory — .git/hooks pointing elsewhere —
# string-matches "$ROOT/*" and sails past the outside-repo guard, and the write
# then lands through the link. Needs the symlink to be planted already, so it is
# defence in depth rather than a live hole, but a prefix test on an unresolved
# path is not the check it looks like.
_resolve() {
    if command -v realpath >/dev/null 2>&1; then realpath "$1" 2>/dev/null || echo "$1"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
    else echo "$1"; fi
}
HOOKS_DIR="$(_resolve "$HOOKS_DIR")"
ROOT_REAL="$(_resolve "$ROOT")"
HOOK="$HOOKS_DIR/pre-push"

# A hooksPath outside this repo is shared by every clone that points at it.
# Editing it is a global change wearing the costume of a per-repo install.
case "$HOOKS_DIR" in
    "$ROOT_REAL"/*) ;;
    *)
        printf '\n\033[33mWARNING: hooks dir is OUTSIDE this repo:\033[0m %s\n' "$HOOKS_DIR" >&2
        printf 'It is shared by every clone configured to use it, so this is a GLOBAL edit.\n' >&2
        printf 'Re-run with PARALLAX_HOOKS_FORCE=1 if that is what you intend.\n\n' >&2
        [ "${PARALLAX_HOOKS_FORCE:-0}" = "1" ] || exit 3
        ;;
esac

MARKER="parallax:commit-message-scan"

# Match the marker only as an installed layer, never as a passing mention in a
# comment someone wrote. The first version's bare grep let a TODO note make the
# installer report "already installed" while nothing was installed — which also
# blocked it from ever repairing a broken install.
already_installed() {
    [ -f "$1" ] && grep -q "^# --- ${MARKER} (BLOCKING)" "$1" 2>/dev/null
}

if already_installed "$HOOK"; then
    echo "  ✓ already installed in $HOOK"
    exit 0
fi

if [ -L "$HOOK" ]; then
    printf '\033[31mFATAL:\033[0m %s is a symlink.\n' "$HOOK" >&2
    printf 'Editing it would either detach this clone from its managed source or mutate\n' >&2
    printf 'the shared target. Install the layer in the source hook instead.\n' >&2
    exit 3
fi

if [ -f "$HOOK" ]; then
    FIRST_LINE="$(head -1 "$HOOK")"
    case "$FIRST_LINE" in
        '#!'*sh*) ;;   # sh, bash, zsh, dash
        *)
            printf '\033[31mFATAL:\033[0m %s is not a shell hook (first line: %s)\n' "$HOOK" "$FIRST_LINE" >&2
            printf 'Appending shell into it would corrupt it. Add the layer by hand.\n' >&2
            exit 3
            ;;
    esac
fi

read -r -d '' LAYER <<'LAYER_EOF' || true
# --- parallax:commit-message-scan (BLOCKING) ---------------------------------
# Prepended deliberately: first executable statement, so it cannot be stranded
# behind an `exit` or an `exec` further down. The original hook body runs after
# this and keeps its own exit status.
#
# Blocks on BOTH exit codes: 1 = a hit, 2 = the outgoing range could not be
# determined. 2 must block: the scanner fails closed rather than reporting a
# clean scan of nothing. Guarded on the script's presence so this hook stays
# valid in a clone that does not ship it.
_PARALLAX_SCAN="$(git rev-parse --show-toplevel 2>/dev/null)/skills/_parallax/scripts/scan_commit_messages.py"
if [ -f "$_PARALLAX_SCAN" ]; then
    # Scan what is ACTUALLY being pushed. git supplies
    # "<local_ref> <local_sha> <remote_ref> <remote_sha>" per ref on stdin.
    # Without this the scanner defaults to origin/main..HEAD, which is the
    # wrong range whenever the pushed branch is not the checked-out one:
    # `git push origin feature` from `main` scanned an empty range, reported
    # clean, and published unscanned commits.
    # Capture stdin to a file and RE-POINT it before returning control. A bare
    # `while read` drains stdin, and this layer is prepended — so every gate
    # after it (security, perimeter, git-lfs) would receive an EMPTY ref list
    # and silently do nothing. `exec <` restores it for the rest of the hook.
    _PARALLAX_STDIN="$(mktemp "${TMPDIR:-/tmp}/parallax-prepush.XXXXXX")"
    cat > "$_PARALLAX_STDIN"
    _PARALLAX_SCAN_RC=0
    _PARALLAX_SAW_REF=0
    while read -r _l_ref _l_sha _r_ref _r_sha; do
        [ -z "${_l_sha:-}" ] && continue
        case "$_l_sha" in *[!0]*) ;; *) continue ;; esac   # all-zero = deletion
        _PARALLAX_SAW_REF=1
        case "$_r_sha" in
            ""|*[!0-9a-f]*|0000000000000000000000000000000000000000)
                _PARALLAX_RANGE="$_l_sha" ;;               # new branch: all of it
            *) _PARALLAX_RANGE="$_r_sha..$_l_sha" ;;
        esac
        python3 "$_PARALLAX_SCAN" "$_PARALLAX_RANGE" || _PARALLAX_SCAN_RC=$?
    done < "$_PARALLAX_STDIN"
    exec < "$_PARALLAX_STDIN"
    rm -f "$_PARALLAX_STDIN"
    # No ref info (invoked by hand, or a deletion-only push): fall back to the
    # scanner's own default rather than skipping, so it never passes vacuously.
    if [ "$_PARALLAX_SAW_REF" -eq 0 ]; then
        python3 "$_PARALLAX_SCAN"
        _PARALLAX_SCAN_RC=$?
    fi
    if [ "$_PARALLAX_SCAN_RC" -ne 0 ]; then
        printf '\n\033[31m[pre-push] BLOCKED: commit-message scan failed (exit %s).\033[0m\n' "$_PARALLAX_SCAN_RC" >&2
        printf '           Rewrite the message locally before pushing; a pushed message\n' >&2
        printf '           cannot be unpublished. See CLAUDE.md, "Commit messages are public too".\n' >&2
        exit "$_PARALLAX_SCAN_RC"
    fi
fi
# --- end parallax:commit-message-scan ----------------------------------------
LAYER_EOF

mkdir -p "$HOOKS_DIR" || exit 2

if [ -f "$HOOK" ]; then
    BACKUP="$HOOK.bak.$(date +%Y%m%d%H%M%S)"
    cp "$HOOK" "$BACKUP" || exit 2
    echo "  backed up existing hook -> $BACKUP"
    SHEBANG="$(head -1 "$HOOK")"
    {
        printf '%s\n\n' "$SHEBANG"
        printf '%s\n\n' "$LAYER"
        tail -n +2 "$HOOK"
    } > "$HOOK.new" || exit 2
    mv "$HOOK.new" "$HOOK" || exit 2
else
    printf '#!/usr/bin/env bash\n\n%s\n\nexit 0\n' "$LAYER" > "$HOOK" || exit 2
fi

chmod +x "$HOOK" || exit 2

if ! bash -n "$HOOK" 2>/dev/null; then
    printf '\033[31mFATAL:\033[0m installed hook has a syntax error; restoring backup.\n' >&2
    [ -n "${BACKUP:-}" ] && cp "$BACKUP" "$HOOK"
    exit 2
fi

# Reachability, not just syntax. `bash -n` parses; it does not prove the layer
# executes. Assert the marker precedes any top-level `exit`/`exec`, which is
# what "installed" has to mean — the first version passed `bash -n` while the
# guard sat after the hook's terminal exit and never ran.
MARK_LINE="$(grep -n "^# --- ${MARKER} (BLOCKING)" "$HOOK" | head -1 | cut -d: -f1)"
TERM_LINE="$(grep -nE '^[[:space:]]*(exit|exec)([[:space:]]|$)' "$HOOK" | head -1 | cut -d: -f1)"
if [ -n "$MARK_LINE" ] && [ -n "$TERM_LINE" ] && [ "$MARK_LINE" -gt "$TERM_LINE" ]; then
    printf '\033[31mFATAL:\033[0m layer is unreachable (line %s, after a terminator at %s); restoring backup.\n' \
        "$MARK_LINE" "$TERM_LINE" >&2
    [ -n "${BACKUP:-}" ] && cp "$BACKUP" "$HOOK"
    exit 2
fi

echo "  ✓ installed into $HOOK"
echo "  verify with: git push --dry-run <remote> <branch>"
