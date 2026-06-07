#!/usr/bin/env bash
# Rebuild .skill packages for upload to claude.ai.
# Usage: ./build-skills.sh [skill-name ...]
# No args = build all KNOWN_SKILLS (general-release set).
#
# Output: ~/Downloads/<skill-name>.skill
#
# Two skill tiers:
#   KNOWN_SKILLS       — general-release skills, built by default (no-arg run).
#   PRIVATE_BETA_SKILLS — limited-distribution skills. Build by name only;
#                        never included in the no-arg default. A WARN line is
#                        emitted on every explicit build to keep the operator
#                        aware that the artifact is not for general release.
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

# Private beta — opt-in only, not built by default.
# Skills here are gated until pilot customers complete one full usage cycle.
PRIVATE_BETA_SKILLS="parallax-cio-letter-prep"

is_private_beta() {
  local name="$1"
  local s
  for s in $PRIVATE_BETA_SKILLS; do
    if [[ "$s" == "$name" ]]; then
      return 0
    fi
  done
  return 1
}

build_one() {
  local name="$1"
  if [[ ! -d "$name" ]]; then
    echo "  ✗ $name: directory not found, skipping" >&2
    return 1
  fi
  if is_private_beta "$name"; then
    echo "  WARN: building private-beta skill '$name' — not for general release" >&2
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

# JIT-load directive lint — assert every `references/...md` directive resolves.
# Specced in _parallax/skill-structure-conventions.md "Build-time check" but never
# shipped; absence let renamed/missing reference files drift silently. Resolves both
# local (references/x.md) and cross-skill (parallax-portfolio-checkup/references/x.md,
# ../client-review/references/x.md) forms — the latter two are NOT dangling.
lint_jit_directives() {
  local fail=0 skill_md skill_dir ref
  for skill_md in */SKILL.md; do
    skill_dir=$(dirname "$skill_md")
    while IFS= read -r ref; do
      [[ -z "$ref" || "$ref" == *"<"* ]] && continue   # skip placeholders like references/<name>.md
      # Resolve from the skill dir (covers local + ../sibling) OR from skills root (covers bare cross-skill).
      [[ -f "$skill_dir/$ref" || -f "$ref" ]] && continue
      echo "  ✗ JIT-directive DANGLING: $skill_md -> $ref" >&2
      fail=1
    done < <(grep -oE '(\.\./)?[A-Za-z0-9_-]*/?references/[A-Za-z0-9_/-]+\.md' "$skill_md" | sort -u)
  done
  return $fail
}

# Coverage lint — gate the build on asset-class / endpoint mismatches.
# Pass --no-lint as the first argument to skip in emergencies.
if [[ "${1:-}" == "--no-lint" ]]; then
  shift
  echo "WARN: coverage-lint skipped (--no-lint)"
else
  echo "Linting JIT-load directives…"
  if ! lint_jit_directives; then
    echo "FAIL: one or more references/ directives point at a missing file." >&2
    exit 1
  fi
  echo "  ✓ all JIT-load directives resolve"
  echo ""
  echo "Validating agentskills.io spec compliance…"
  if ! python3 ./_parallax/scripts/spec-validate.py $(ls -d */ | while read -r d; do [[ -f "$d/SKILL.md" ]] && echo "$d"; done); then
    echo "FAIL: one or more skills violate the agentskills.io spec." >&2
    exit 1
  fi
  echo ""
  if [[ -x ./_parallax/scripts/coverage-lint.sh ]]; then
    echo "Running coverage-lint…"
    ./_parallax/scripts/coverage-lint.sh
    echo ""
  fi
fi

if [[ $# -eq 0 ]]; then
  set -- $KNOWN_SKILLS
fi

echo "Building .skill packages:"
for name in "$@"; do
  build_one "$name" || true
done
