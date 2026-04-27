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
PARALLAX_TARGET="$SKILLS_DIR/_parallax"
PARALLAX_SOURCE="$SCRIPT_DIR/skills/_parallax"

if [ -L "$PARALLAX_TARGET" ] && [ "$(readlink "$PARALLAX_TARGET")" = "$PARALLAX_SOURCE" ]; then
    echo "  Symlinked  _parallax (already dev mode — edits live from repo)"
else
    rm -rf "$PARALLAX_TARGET"
    ln -s "$PARALLAX_SOURCE" "$PARALLAX_TARGET"
    echo "  Symlinked  _parallax (shared conventions + house-view loader/schema)"
fi

# Copy each skill with parallax- prefix
for skill_dir in "$SCRIPT_DIR"/skills/*/; do
    skill_name=$(basename "$skill_dir")
    [ "$skill_name" = "_parallax" ] && continue

    target="$SKILLS_DIR/parallax-$skill_name"

    # If the target is already a symlink pointing at this repo's skill dir,
    # skip — edits in the repo propagate automatically. Avoids `cp`-into-self errors.
    if [ -L "$target" ] && [ "$(readlink "$target")" = "${skill_dir%/}" ]; then
        echo "  Symlinked  parallax-$skill_name (dev mode — edits live from repo)"
        continue
    fi

    mkdir -p "$target"
    cp -r "$skill_dir"* "$target/"
    echo "  Installed  parallax-$skill_name"
done

echo ""
echo "Done! $(ls -d "$SCRIPT_DIR"/skills/*/ | grep -v _parallax | wc -l | tr -d ' ') workflows installed."
echo "Try: /parallax-should-i-buy AAPL"
