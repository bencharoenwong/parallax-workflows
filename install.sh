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

# Copy shared conventions, token costs, and AI profile framework
rm -rf "$SKILLS_DIR/_parallax"
cp -r "$SCRIPT_DIR/skills/_parallax" "$SKILLS_DIR/_parallax"
echo "  Copied shared conventions, token costs, and AI-profiles framework"

# Copy each skill with parallax- prefix
for skill_dir in "$SCRIPT_DIR"/skills/*/; do
    skill_name=$(basename "$skill_dir")
    [ "$skill_name" = "_parallax" ] && continue

    target="$SKILLS_DIR/parallax-$skill_name"
    mkdir -p "$target"
    cp -r "$skill_dir"* "$target/"
    echo "  Installed parallax-$skill_name"
done

echo ""
echo "Done! $(ls -d "$SCRIPT_DIR"/skills/*/ | grep -v _parallax | wc -l | tr -d ' ') workflows installed."
echo "Try: /parallax-should-i-buy AAPL"
