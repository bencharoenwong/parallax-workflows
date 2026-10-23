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

read -r -d '' LAYER <<'LAYER_EOF' || true
# --- parallax:commit-message-scan (BLOCKING) ---------------------------------
# Prepended deliberately: first executable statement, so it cannot be stranded
# behind an `exit` or an `exec` further down. The original hook body runs after
# this and keeps its own exit status.
#
# Blocks on BOTH exit codes: 1 = a hit, 2 = the outgoing range could not be
# determined. 2 must block: the scanner fails closed rather than reporting a
# clean scan of nothing. A clone that does not ship the scanner skips it, unless
# origin/main ships it: then a branch that deletes it is blocked.
# Scan the objects git will actually send. With refs/replace/* in effect every
# git read below (messages, file contents, the trusted guard blob) would see the
# substitute while the push sends the original. core.useReplaceRefs=true in
# config overrides this variable; git then sends the substitute too, so scan and
# push still read the same objects. The caller's value is put back at the end of
# the layer, so hook code after it is unaffected.
_PARALLAX_NRO_SET="${GIT_NO_REPLACE_OBJECTS+set}"
_PARALLAX_NRO="${GIT_NO_REPLACE_OBJECTS:-}"
export GIT_NO_REPLACE_OBJECTS=1
_PARALLAX_SCAN="$(git rev-parse --show-toplevel 2>/dev/null)/skills/_parallax/scripts/scan_commit_messages.py"
# client_guard.py scans the same range for registered client names: contents of
# every added or modified file in every pushed commit (not just the tip, since
# intermediate commits are published too), file paths, messages and the remote
# branch name. It needs the client-guard key and fails closed (exit 2) without it.
# Called on every push, independent of the message scanner: a branch that
# deletes one scanner must not switch off the other. _parallax_guard resolves the
# guard from origin/main, then the checkout, and otherwise blocks or warns.
_PARALLAX_GUARD="$(git rev-parse --show-toplevel 2>/dev/null)/skills/_parallax/scripts/client_guard.py"
_PARALLAX_REGISTRY="$(git rev-parse --show-toplevel 2>/dev/null)/.client-guard/registry.json"
# Prefer the guard committed on origin/main over the checked-out copy: an old
# checkout (or a branch that edits the guard) must not decide what is scanned.
# origin/main's registry and allowlist are merged in via CLIENT_GUARD_TRUSTED_REV.
# Always the full ref name: git resolves a short `origin/main` to a local
# branch or tag of that name first, which would let a local ref pose as main.
_parallax_guard() {
    _pg_top="$(git rev-parse --show-toplevel 2>/dev/null)"
    _pg_rel="skills/_parallax/scripts/client_guard.py"
    if git cat-file -e "refs/remotes/origin/main:$_pg_rel" 2>/dev/null \
            && git cat-file -e "refs/remotes/origin/main:.client-guard/registry.json" 2>/dev/null; then
        _pg_tmp="$(mktemp "${TMPDIR:-/tmp}/parallax-guard.XXXXXX")" || return 2
        git show "refs/remotes/origin/main:$_pg_rel" > "$_pg_tmp" || { rm -f "$_pg_tmp"; return 2; }
        CLIENT_GUARD_REPO_ROOT="$_pg_top" CLIENT_GUARD_TRUSTED_REV=refs/remotes/origin/main \
            python3 "$_pg_tmp" scan-range "$@"
        _pg_rc=$?
        rm -f "$_pg_tmp"
        return "$_pg_rc"
    elif [ -f "$_PARALLAX_GUARD" ]; then
        python3 "$_PARALLAX_GUARD" scan-range "$@"
    elif [ -f "$_PARALLAX_REGISTRY" ]; then
        printf '\n\033[31m[pre-push] BLOCKED: .client-guard/registry.json exists but client_guard.py is missing.\033[0m\n' >&2
        return 2
    elif [ "${_PARALLAX_ELSEWHERE:-0}" = 1 ]; then
        # A push away from origin (often an old clone of private history) must
        # not pass unscanned just because neither copy of the guard is there.
        printf '\n\033[31m[pre-push] BLOCKED: pushing to a remote other than origin and no client guard was found.\033[0m\n' >&2
        return 2
    else
        # Warn, not block: a repo or branch that predates the guard still pushes.
        printf '\033[33m[pre-push] WARNING: no client guard was found; client names were NOT scanned.\033[0m\n' >&2
    fi
}
# True when this push goes to the URL origin/main was FETCHED from. Only then
# are commits on origin/main already public at the target. A clone whose origin
# is a PRIVATE repo pushing to the public one would otherwise skip everything on
# its origin/main -- exactly the history never published. A pushurl that
# differs from the fetch URL makes $2 differ too, so it counts as elsewhere.
# A local gate repo (no-mistakes) also counts as elsewhere: where it forwards
# is recorded in the gate's own state, not in anything this hook can trust, so
# a push through it scans the whole branch.
# Invoked by hand (no URL): nothing is published, so the exclusion is kept.
# Only a trailing slash is dropped. Stripping `.git` made a local `X` match an
# origin at `X.git`, a different repository; a mismatch only scans more.
_parallax_norm_url() { printf '%s' "${1%/}"; }
_parallax_targets_origin() {
    [ -n "${1:-}" ] || return 0
    _pt_url="$(git remote get-url origin 2>/dev/null)"
    [ -n "$_pt_url" ] || return 1
    [ "$(_parallax_norm_url "$1")" = "$(_parallax_norm_url "$_pt_url")" ]
}
# Always runs; each scanner call checks for its own script. It used to need a
# scanner, guard or registry in the checkout (or the guard on a not-yet-
# refreshed origin/main), so an old checkout pushed elsewhere skipped the
# refresh and the no-guard block entirely.
{
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
    _PARALLAX_STDIN="$(mktemp "${TMPDIR:-/tmp}/parallax-prepush.XXXXXX" 2>/dev/null)"
    if [ -z "$_PARALLAX_STDIN" ] || [ ! -f "$_PARALLAX_STDIN" ]; then
        # Unchecked, this degraded to the scanner's default range — silently
        # reverting to the wrong-range behaviour this layer exists to fix.
        printf '\n\033[31m[pre-push] BLOCKED: cannot create a temp file to read the ref list.\033[0m\n' >&2
        exit 2
    fi
    cat > "$_PARALLAX_STDIN"
    # Refresh origin/main first (best effort). A stale copy lacks names the
    # maintainer registered since the last fetch, and lacks the guard itself in
    # a clone that predates it. Failure (offline) is reported on every push and
    # drops the origin/main exclusion below. A stalled transfer is bounded:
    # HTTP aborts below 1 KB/s for 15 s; SSH gets a connect and keepalive
    # timeout unless the user configured their own SSH program. An HTTP
    # connect still uses curl's own connect timeout. No BatchMode: a
    # passphrase key without an agent may prompt, as it did for the push.
    _PARALLAX_FETCH_FAILED=""
    if git remote get-url origin >/dev/null 2>&1; then
        (
            if [ -z "${GIT_SSH_COMMAND:-}" ] && [ -z "${GIT_SSH:-}" ] \
                    && [ -z "${GIT_SSH_VARIANT:-}" ] \
                    && [ -z "$(git config --get core.sshCommand 2>/dev/null)" ] \
                    && [ -z "$(git config --get ssh.variant 2>/dev/null)" ]; then
                export GIT_SSH_COMMAND="ssh -o ConnectTimeout=15 -o ServerAliveInterval=5 -o ServerAliveCountMax=3"
            fi
            GIT_TERMINAL_PROMPT=0 git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 \
                fetch -q --no-tags origin "+refs/heads/main:refs/remotes/origin/main" \
                </dev/null >/dev/null 2>&1
        ) || _PARALLAX_FETCH_FAILED=1
    fi
    if [ -n "$_PARALLAX_FETCH_FAILED" ]; then
        printf '\n\033[33m[pre-push] WARNING: could not refresh origin/main. Scanning the whole pushed history, since a stale origin/main proves nothing about the target; the guard may also lack recently registered names.\033[0m\n' >&2
    fi
    # Commits already reachable from the PUBLISHED default branch are public
    # with or without this push. Without the exclusion below, merging main
    # into a branch put main's whole history back into "$_r_sha..$_l_sha",
    # and one old public message tripping a since-added rule blocked a push
    # that published nothing new. Remote-tracking refs only: a LOCAL main may
    # hold unpushed commits that still need scanning. Only when the push
    # targets origin (see _parallax_targets_origin) AND the refresh succeeded:
    # matching URLs do not prove matching history (a repo re-created at the
    # same URL, a repointed origin). Otherwise nothing is excluded and a new
    # branch is scanned whole.
    _PARALLAX_PUBLIC=""
    _PARALLAX_ELSEWHERE=0
    _parallax_targets_origin "${2:-}" || _PARALLAX_ELSEWHERE=1
    if [ -z "$_PARALLAX_FETCH_FAILED" ] && [ "$_PARALLAX_ELSEWHERE" = 0 ]; then
        for _pub in refs/remotes/origin/main refs/remotes/origin/master; do
            if git rev-parse --verify --quiet "$_pub" >/dev/null 2>&1; then
                _PARALLAX_PUBLIC="$_pub"; break
            fi
        done
    fi
    _PARALLAX_SCAN_RC=0
    _PARALLAX_SAW_REF=0
    while read -r _l_ref _l_sha _r_ref _r_sha; do
        [ -z "${_l_sha:-}" ] && continue
        case "$_l_sha" in *[!0]*) ;; *) continue ;; esac   # all-zero = deletion
        _PARALLAX_SAW_REF=1
        case "$_r_sha" in
            ""|*[!0-9a-f]*|0000000000000000000000000000000000000000)
                # New branch: the remote has no counterpart, so there is no
                # "$_r_sha..$_l_sha" to scan. Scan the whole branch; the
                # "^$_PARALLAX_PUBLIC" selector below removes what is already
                # on the published main. A bare rev alone walked every ancestor
                # and blocked new branches on 60 old public messages. A base
                # chosen from other refs (local main, a stale origin/master)
                # left commits that this push publishes unscanned, so there is
                # no base: only the freshly fetched origin/main excludes.
                _PARALLAX_RANGE="$_l_sha" ;;
            *) _PARALLAX_RANGE="$_r_sha..$_l_sha" ;;
        esac
        if [ ! -f "$_PARALLAX_SCAN" ] && git cat-file -e \
                "refs/remotes/origin/main:skills/_parallax/scripts/scan_commit_messages.py" 2>/dev/null; then
            printf '\n\033[31m[pre-push] BLOCKED: scan_commit_messages.py is missing here but present on origin/main.\033[0m\n' >&2
            _PARALLAX_SCAN_RC=2
        elif [ -f "$_PARALLAX_SCAN" ]; then
            if [ -n "$_PARALLAX_PUBLIC" ]; then
                python3 "$_PARALLAX_SCAN" "$_PARALLAX_RANGE" "^$_PARALLAX_PUBLIC" || _PARALLAX_SCAN_RC=$?
            else
                python3 "$_PARALLAX_SCAN" "$_PARALLAX_RANGE" || _PARALLAX_SCAN_RC=$?
            fi
        else
            printf '\033[33m[pre-push] WARNING: scan_commit_messages.py not found; commit messages were NOT scanned.\033[0m\n' >&2
        fi
        if [ -n "$_PARALLAX_PUBLIC" ]; then
            _parallax_guard --ref "${_r_ref:-}" "$_PARALLAX_RANGE" "^$_PARALLAX_PUBLIC" || _PARALLAX_SCAN_RC=$?
        else
            _parallax_guard --ref "${_r_ref:-}" "$_PARALLAX_RANGE" || _PARALLAX_SCAN_RC=$?
        fi
    done < "$_PARALLAX_STDIN"
    # Record whether git supplied ANY ref lines before the file goes away.
    # The emptiness test has to happen here: `rm -f` below unlinks it, and the
    # later check then always saw "no input" and fell through to the default
    # range — the exact fallback it was meant to distinguish.
    # `exec <` keeps a live fd, so unlinking after it is safe on POSIX.
    _PARALLAX_HAD_INPUT=0
    [ -s "$_PARALLAX_STDIN" ] && _PARALLAX_HAD_INPUT=1
    exec < "$_PARALLAX_STDIN"
    rm -f "$_PARALLAX_STDIN"
    # No ref info (invoked by hand, or a deletion-only push): fall back to the
    # scanner's own default rather than skipping, so it never passes vacuously.
    if [ "$_PARALLAX_SAW_REF" -eq 0 ]; then
        if [ "$_PARALLAX_HAD_INPUT" -eq 1 ]; then
            # Refs were supplied but every one was a deletion. There are no
            # commits being published, so there is nothing to scan. Falling
            # through to the default range scanned the CHECKED-OUT branch, which
            # has nothing to do with the ref being deleted — the same wrong-range
            # family this layer was written to fix.
            _PARALLAX_SCAN_RC=0
        else
            # No ref info at all (invoked by hand). Use the scanner's default
            # rather than skipping, so it cannot pass vacuously.
            if [ -f "$_PARALLAX_SCAN" ]; then
                python3 "$_PARALLAX_SCAN"
                _PARALLAX_SCAN_RC=$?
            fi
            if [ -n "$_PARALLAX_PUBLIC" ]; then
                _parallax_guard HEAD "^$_PARALLAX_PUBLIC" || _PARALLAX_SCAN_RC=$?
            else
                _parallax_guard HEAD || _PARALLAX_SCAN_RC=$?
            fi
        fi
    fi
    if [ "$_PARALLAX_SCAN_RC" -ne 0 ]; then
        printf '\n\033[31m[pre-push] BLOCKED: commit-message or client-name scan failed (exit %s).\033[0m\n' "$_PARALLAX_SCAN_RC" >&2
        printf '           Rewrite the message locally before pushing; a pushed message\n' >&2
        printf '           cannot be unpublished. See CLAUDE.md, "Commit messages are public too".\n' >&2
        exit "$_PARALLAX_SCAN_RC"
    fi
    if [ -n "$_PARALLAX_NRO_SET" ]; then
        GIT_NO_REPLACE_OBJECTS="$_PARALLAX_NRO"
    else
        unset GIT_NO_REPLACE_OBJECTS
    fi
}
# --- end parallax:commit-message-scan ----------------------------------------
LAYER_EOF

# Match the marker only as an installed layer, never as a passing mention in a
# comment someone wrote. The first version's bare grep let a TODO note make the
# installer report "already installed" while nothing was installed — which also
# blocked it from ever repairing a broken install.
already_installed() {
    [ -f "$1" ] && grep -q "^# --- ${MARKER} (BLOCKING)" "$1" 2>/dev/null
}

# The installed copy of the layer -- marker line through end marker -- for
# comparison against the current LAYER text.
installed_layer() {
    sed -n "/^# --- ${MARKER} (BLOCKING)/,/^# --- end ${MARKER} /p" "$1"
}

_PARALLAX_REFRESH=0
BACKUP=""
if already_installed "$HOOK"; then
    if [ "$(installed_layer "$HOOK")" = "$(printf '%s' "$LAYER")" ]; then
        echo "  ✓ already installed in $HOOK"
        exit 0
    fi
    # An OLDER layer is installed. Without this path a fixed layer never
    # reaches a clone that installed before the fix: the marker grep reported
    # "already installed" forever. Fall through the same refusal checks a
    # fresh install runs; the old region is stripped just before assembly.
    _PARALLAX_REFRESH=1
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


if ! mkdir -p "$HOOKS_DIR" 2>/dev/null; then
    # A linked worktree's .git is a FILE, so a relative hooks path joined to the
    # worktree root cannot be created. The no-mistakes gate runs in exactly such
    # a worktree, and the failure was a raw mkdir error with no diagnostic.
    printf '\033[31mFATAL:\033[0m cannot create hooks directory: %s\n' "$HOOKS_DIR" >&2
    printf 'In a linked git worktree the hooks live with the main checkout; install there.\n' >&2
    exit 2
fi

if [ "$_PARALLAX_REFRESH" = 1 ]; then
    if ! installed_layer "$HOOK" | tail -1 | grep -q "^# --- end ${MARKER} "; then
        printf '\033[31mFATAL:\033[0m the installed layer in %s has no end marker.\n' "$HOOK" >&2
        printf 'Stripping it would delete everything after the start marker, including any\n' >&2
        printf 'other gates below it. Repair or remove the layer by hand, then re-run.\n' >&2
        exit 3
    fi
    BACKUP="$HOOK.bak.$(date +%Y%m%d%H%M%S)"
    cp "$HOOK" "$BACKUP" || exit 2
    echo "  backed up existing hook -> $BACKUP"
    sed "/^# --- ${MARKER} (BLOCKING)/,/^# --- end ${MARKER} /d" "$HOOK" > "$HOOK.strip" || exit 2
    mv "$HOOK.strip" "$HOOK" || exit 2
    echo "  refreshing outdated layer in $HOOK"
fi

if [ -f "$HOOK" ]; then
    if [ -z "${BACKUP:-}" ]; then
        BACKUP="$HOOK.bak.$(date +%Y%m%d%H%M%S)"
        cp "$HOOK" "$BACKUP" || exit 2
        echo "  backed up existing hook -> $BACKUP"
    fi
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
