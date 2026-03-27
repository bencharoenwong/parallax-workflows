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

# Copy shared conventions and token costs
mkdir -p "$SKILLS_DIR/_parallax"
cp "$SCRIPT_DIR/skills/_parallax/parallax-conventions.md" "$SKILLS_DIR/_parallax/parallax-conventions.md"
cp "$SCRIPT_DIR/skills/_parallax/token-costs.md" "$SKILLS_DIR/_parallax/token-costs.md"
echo "  Copied shared conventions + token costs"

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
