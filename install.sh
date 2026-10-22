#!/usr/bin/env bash
# Install Parallax workflows into Claude Code skills directory
set -euo pipefail

SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Parallax workflows to $SKILLS_DIR"

# Create skills directory if it doesn't exist
if [ ! -d "$SKILLS_DIR" ]; then
    echo "  Creating $SKILLS_DIR"
    mkdir -p "$SKILLS_DIR"
fi

# Symlink shared conventions, token costs, and AI profile framework.
# Symlinked (not copied) so edits to loader.md / schema.yaml / conventions
# propagate live without requiring a re-install. Idempotent.
# True when $1 is a symlink that resolves to the same directory as $2.
# Compares resolved physical paths, so relative links (../../parallax-workflows/...)
# and absolute links both count. A plain readlink string compare missed relative
# links and then copied each skill into itself through the link.
links_to() {
    [ -L "$1" ] && [ -d "$1" ] && [ "$(cd "$1" && pwd -P)" = "$(cd "$2" && pwd -P)" ]
}

PARALLAX_TARGET="$SKILLS_DIR/_parallax"
PARALLAX_SOURCE="$SCRIPT_DIR/skills/_parallax"

if links_to "$PARALLAX_TARGET" "$PARALLAX_SOURCE"; then
    echo "  Symlinked  _parallax (already dev mode — edits live from repo)"
else
    # Refuse to clobber a real directory — only replace stale symlinks.
    if [ -e "$PARALLAX_TARGET" ] && [ ! -L "$PARALLAX_TARGET" ]; then
        echo "  ERROR: $PARALLAX_TARGET exists and is not a symlink." >&2
        echo "  Refusing to delete a real directory. Move or remove it manually, then re-run." >&2
        exit 1
    fi
    rm -f "$PARALLAX_TARGET"
    ln -s "$PARALLAX_SOURCE" "$PARALLAX_TARGET"
    echo "  Symlinked  _parallax (shared conventions + house-view loader/schema)"
fi

# Copy each skill under its own name (dir name == frontmatter name per agentskills.io spec)
for skill_dir in "$SCRIPT_DIR"/skills/*/; do
    skill_name=$(basename "$skill_dir")
    [ "$skill_name" = "_parallax" ] && continue
    [ -f "$skill_dir/SKILL.md" ] || continue

    target="$SKILLS_DIR/$skill_name"

    # If the target is already a symlink pointing at this repo's skill dir,
    # skip — edits in the repo propagate automatically. Avoids `cp`-into-self errors.
    if links_to "$target" "${skill_dir%/}"; then
        echo "  Symlinked  $skill_name (dev mode — edits live from repo)"
        continue
    fi

    # Never copy through a symlink into some other directory.
    if [ -L "$target" ]; then
        echo "  SKIP       $skill_name ($target is a symlink to $(readlink "$target"); not overwriting)" >&2
        continue
    fi
    mkdir -p "$target"
    cp -r "$skill_dir"* "$target/"
    echo "  Installed  $skill_name"
done

echo ""
echo "Done! $(ls -d "$SCRIPT_DIR"/skills/*/ | grep -v _parallax | grep -cv '__pycache__' | tr -d ' ') workflows installed."
echo "Try: /parallax-should-i-buy AAPL"
