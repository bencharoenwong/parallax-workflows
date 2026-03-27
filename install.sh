#!/usr/bin/env bash
# Install Parallax workflows into Claude Code skills directory
set -euo pipefail

SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Parallax workflows to $SKILLS_DIR"

# Check if Claude Code skills directory exists
if [ ! -d "$SKILLS_DIR" ]; then
    echo "Error: Skills directory not found at $SKILLS_DIR"
    echo "Set CLAUDE_SKILLS_DIR to your Claude Code skills path"
    exit 1
fi

# Copy shared conventions
mkdir -p "$SKILLS_DIR/_shared"
cp "$SCRIPT_DIR/skills/_shared/parallax-conventions.md" "$SKILLS_DIR/_shared/parallax-conventions.md"
echo "  Copied shared conventions"

# Copy each skill with parallax- prefix
for skill_dir in "$SCRIPT_DIR"/skills/*/; do
    skill_name=$(basename "$skill_dir")
    [ "$skill_name" = "_shared" ] && continue

    target="$SKILLS_DIR/parallax-$skill_name"
    mkdir -p "$target"
    cp -r "$skill_dir"* "$target/"
    echo "  Installed parallax-$skill_name"
done

echo ""
echo "Done! $(ls -d "$SCRIPT_DIR"/skills/*/ | grep -v _shared | wc -l | tr -d ' ') workflows installed."
echo "Try: /parallax-should-i-buy AAPL"
