#!/usr/bin/env bash
# Rebuild .skill packages for upload to claude.ai.
# Usage: ./build-skills.sh [skill-name ...]
# No args = build all known skills.
#
# Output: ~/Downloads/<skill-name>.skill
#
# Portable to bash 3.2 (macOS default — no associative arrays).
set -euo pipefail

cd "$(dirname "$0")"

# Per-skill exclusions (relative to skills/). Returns space-separated paths.
get_excludes() {
  case "$1" in
    translate-chinese-finance)
      echo "translate-chinese-finance/references/INTEGRATION.md translate-chinese-finance/references/load_skill.py"
      ;;
    *)
      echo ""
      ;;
  esac
}

KNOWN_SKILLS="translate-chinese-finance translate-thai-finance"

build_one() {
  local name="$1"
  if [[ ! -d "$name" ]]; then
    echo "  ✗ $name: directory not found, skipping" >&2
    return 1
  fi
  local out="$HOME/Downloads/${name}.skill"
  rm -f "$out"

  local exc_args=()
  local exc
  for exc in $(get_excludes "$name"); do
    exc_args+=(-x "$exc")
  done

  zip -rq "$out" "$name" \
    -x "*.DS_Store" "*/__pycache__/*" "*/.git/*" \
    ${exc_args[@]+"${exc_args[@]}"}
  printf "  ✓ %s → %s (%s)\n" "$name" "$out" "$(du -h "$out" | cut -f1)"
}

# Coverage lint — gate the build on asset-class / endpoint mismatches.
# Pass --no-lint as the first argument to skip in emergencies.
if [[ "${1:-}" == "--no-lint" ]]; then
  shift
  echo "WARN: coverage-lint skipped (--no-lint)"
elif [[ -x ./_parallax/scripts/coverage-lint.sh ]]; then
  echo "Running coverage-lint…"
  ./_parallax/scripts/coverage-lint.sh
  echo ""
fi

if [[ $# -eq 0 ]]; then
  set -- $KNOWN_SKILLS
fi

echo "Building .skill packages:"
for name in "$@"; do
  build_one "$name" || true
done
