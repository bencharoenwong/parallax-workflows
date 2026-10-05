#!/usr/bin/env bash
# Rebuild .skill packages for upload to claude.ai.
# Usage: ./build-skills.sh [--no-lint] [--normalize] [skill-name ...]
# No args = build all KNOWN_SKILLS (manifest `standalone: release` tier).
#   --no-lint    skip lint/validation (emergencies only); the 200-char
#                description cap on translate-*-finance still runs
#   --normalize  rewrite SKILL.md frontmatter to spec-clean form first
#                (folds ported client-convention fields; see
#                _parallax/scripts/spec-normalize.py)
#
# Output: ~/Downloads/<skill-name>.skill
#
# Scope: translate-* and private-beta tiers only. The general-release Parallax
# workflow set ships to claude.ai via `_parallax/scripts/build_bundle.py web`
# (see its docstring for how the two packagers split).
#
# Tiers come from the `standalone` field in _parallax/manifest.json (see
# STANDALONE_TIERS in _parallax/skill_manifest.py). Each package holds tracked
# files only and must pass `build_bundle.py verify` before it is written; any
# failed skill makes the run exit 1.
#
# Portable to bash 3.2 (macOS default — no associative arrays).
set -euo pipefail

cd "$(dirname "$0")"

# Per-skill exclusions (relative to skills/). Returns space-separated paths.
get_excludes() {
  case "$1" in
    translate-chinese-finance)
      # INTEGRATION.md is repo-integration notes; normalize_runtime.py is a
      # maintenance script that rewrites the skill's own files if run.
      echo "translate-chinese-finance/references/INTEGRATION.md translate-chinese-finance/references/normalize_runtime.py"
      ;;
    *)
      echo ""
      ;;
  esac
}

# Tiers come from _parallax/manifest.json (`standalone`): release builds by
# default; beta (pilot customers only) and held (awaiting native-speaker
# review) build only when named, with a warning.
KNOWN_SKILLS=$(python3 ./_parallax/skill_manifest.py standalone release)
PRIVATE_BETA_SKILLS=$(python3 ./_parallax/skill_manifest.py standalone beta)
HELD_SKILLS=$(python3 ./_parallax/skill_manifest.py standalone held)

in_list() {
  local name="$1" s
  shift
  for s in "$@"; do
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
  if in_list "$name" $PRIVATE_BETA_SKILLS; then
    echo "  WARN: building private-beta skill '$name' — not for general release" >&2
  fi
  if in_list "$name" $HELD_SKILLS; then
    echo "  WARN: building held skill '$name' — awaiting native review, not for distribution" >&2
  fi
  local out_dir="${SKILL_BUILD_OUT_DIR:-$HOME/Downloads}"
  mkdir -p "$out_dir"
  local out="$out_dir/${name}.skill"
  local staging
  staging=$(mktemp -d)

  # Tracked files only (as build_bundle.py does), minus tests, test fixtures
  # and the per-skill excludes; untracked caches and work in progress never
  # ship. Fixtures are maintainer verification data, and a compressed binary
  # cannot be term-scanned meaningfully.
  local excludes
  excludes=" $(get_excludes "$name") "
  if ! git ls-files -- "$name" \
      | grep -Ev '(^|/)(tests/|fixtures/|test_[^/]*[.]py$|conftest[.]py$)' \
      | while IFS= read -r f; do
          [[ "$excludes" == *" $f "* ]] && continue
          mkdir -p "$staging/$(dirname "$f")" && cp "$f" "$staging/$f" || exit 1
        done; then
    echo "  ✗ $name: copying tracked files failed" >&2
    rm -rf "$staging"
    return 1
  fi
  if [[ ! -f "$staging/$name/SKILL.md" ]]; then
    echo "  ✗ $name: no tracked SKILL.md (commit the skill first)" >&2
    rm -rf "$staging"
    return 1
  fi
  if [[ "$name" == translate-*-finance ]]; then
    cp "_parallax/translation_validate.py" "$staging/$name/references/translation_common.py"
  fi
  if ! python3 ./_parallax/scripts/build_bundle.py verify "$staging/$name"; then
    echo "  ✗ $name: package failed verification; nothing written" >&2
    rm -rf "$staging"
    return 1
  fi
  # Fresh archive: stale files from a previous package must not survive.
  (cd "$staging" && zip -rq package.skill "$name")
  mv "$staging/package.skill" "$out"
  rm -rf "$staging"
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

# Flags (must precede skill names).
RUN_LINT=1
NORMALIZE=0
while [[ "${1:-}" == --* ]]; do
  case "$1" in
    --no-lint)   RUN_LINT=0 ;;
    --normalize) NORMALIZE=1 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

all_skill_dirs() {
  ls -d */ | while read -r d; do [[ -f "$d/SKILL.md" ]] && echo "$d"; done
}

# Spec normalization — fold ported client-convention frontmatter fields
# (user-invocable, argument-hint, negative-triggers) into spec-clean form
# before validation. Opt-in: rewrites source files.
if [[ $NORMALIZE -eq 1 ]]; then
  echo "Normalizing SKILL.md frontmatter to spec…"
  python3 ./_parallax/scripts/spec-normalize.py $(all_skill_dirs)
  echo ""
fi

# Coverage lint — gate the build on asset-class / endpoint mismatches.
# Pass --no-lint to skip in emergencies.
if [[ $RUN_LINT -eq 0 ]]; then
  echo "WARN: coverage-lint skipped (--no-lint)"
else
  echo "Linting JIT-load directives…"
  if ! lint_jit_directives; then
    echo "FAIL: one or more references/ directives point at a missing file." >&2
    exit 1
  fi
  echo "  ✓ all JIT-load directives resolve"
  echo ""
  echo "Linting cross-file section references (§N.M)…"
  if ! python3 ./_parallax/scripts/section-ref-lint.py; then
    echo "FAIL: one or more <file>.md §N references point at a missing section or file." >&2
    exit 1
  fi
  echo ""
  echo "Linting host-locked identifiers (conventions §14)…"
  if ! python3 ./_parallax/scripts/host-primitive-lint.py; then
    echo "FAIL: a non-legacy SKILL.md names a host tool outside a host-note block, or the legacy allowlist is stale." >&2
    exit 1
  fi
  echo ""
  echo "Linting authority headers on shared _parallax/*.md…"
  if ! python3 ./_parallax/scripts/authority-header-lint.py; then
    echo "FAIL: a shared _parallax/*.md lacks the authority/verified/overrides header." >&2
    exit 1
  fi
  echo ""
  echo "Validating agentskills.io spec compliance…"
  if ! python3 ./_parallax/scripts/spec-validate.py $(all_skill_dirs); then
    echo "FAIL: one or more skills violate the agentskills.io spec." >&2
    echo "      If the failure is ported client-convention frontmatter" >&2
    echo "      (user-invocable / negative-triggers / argument-hint), run:" >&2
    echo "      ./build-skills.sh --normalize" >&2
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

# claude.ai caps skill descriptions at 200 chars (stricter than the spec's
# 1024). Enforced for translate-*-finance only; not skippable with --no-lint.
echo "Checking claude.ai description cap (200 chars) for translate-*-finance…"
if ! python3 - "$@" <<'PY'
import sys
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

failed = 0
for name in sys.argv[1:]:
    if not fnmatchcase(name, "translate-*-finance"):
        continue
    md = Path(name) / "SKILL.md"
    if not md.is_file():
        continue  # build_one reports the missing directory
    fm = yaml.safe_load(md.read_text(encoding="utf-8").split("---\n", 2)[1])
    desc = fm.get("description") or ""
    if len(desc) > 200:
        print(f"  ✗ {name}: description {len(desc)} chars (> 200)", file=sys.stderr)
        failed = 1
sys.exit(failed)
PY
then
  echo "FAIL: shorten the description(s) above before packaging for claude.ai." >&2
  exit 1
fi
echo ""

echo "Building .skill packages:"
FAILED=""
for name in "$@"; do
  build_one "$name" || FAILED="$FAILED $name"
done
if [[ -n "$FAILED" ]]; then
  echo "FAIL: not built:$FAILED" >&2
  exit 1
fi
