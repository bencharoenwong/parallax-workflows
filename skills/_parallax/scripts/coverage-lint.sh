#!/usr/bin/env bash
# coverage-lint.sh — flag asset-class / endpoint mismatches in SKILL.md files,
# plus structural checks for skills with bespoke scaffolding requirements.
#
# Bug class A — asset-class / endpoint mismatch:
#   A SKILL.md instructs the runtime model to call an equity-only tool
#   (e.g., `export_price_series`) on a symbol that may resolve to an ETF.
#   The tool returns empty silently; the model substitutes a plausible-looking
#   fallback; the user can't tell the output is degraded. See
#   `_parallax/coverage-matrix.md` for the canonical tool/asset-class table.
#
# Bug class B — skill-specific scaffolding drift (currently scoped to
#   `cio-letter-prep`): the skill ships with required helper scripts, contract
#   tests, MCP mocks, and frontmatter sections. If any of those go missing or
#   the SKILL.md stops citing them, the runtime is silently degraded.
#
# What this lints (class A — applies to every skill):
#   1. Every `export_price_series(...)` reference in skills/*/SKILL.md.
#   2. Look back ≤ 30 lines for an asset-class pre-classification keyword:
#        etf_profile | asset class | asset-class | asset_class
#        | Pre-classification | branch on asset
#   3. If keyword absent → FAIL with file:line.
#   4. Skip the `_parallax/` directory itself (it documents patterns,
#      not call them).
#   5. Skip lines tagged `<!-- coverage-lint: ignore-next -->` (escape
#      hatch for prose discussions of the bug class).
#
# What this lints (class B — only fires if `skills/cio-letter-prep/` exists):
#   1. SKILL.md exists and frontmatter contains name/description/
#      negative-triggers/gotchas keys.
#   2. SKILL.md body cites: parallax-conventions, contribution.py, and the
#      MCP contract tests (test_mcp_contracts or mcp_mocks).
#   3. scripts/contribution.py, scripts/test_contribution.py, and
#      scripts/test_mcp_contracts.py exist.
#   4. scripts/mcp_mocks/ contains ≥ 9 .json files.
#   5. (Optional) `pytest skills/cio-letter-prep/scripts/ -q` passes.
#      Skipped with a warning if pytest is not on PATH.
#
# Usage:
#   ./skills/_parallax/scripts/coverage-lint.sh         # lint all skills
#   ./skills/_parallax/scripts/coverage-lint.sh pair-finder explain-portfolio
#
# Exit:
#   0 — clean
#   1 — at least one violation found (across both check classes)

set -euo pipefail

cd "$(dirname "$0")/../../.."   # repo root

WINDOW=30                          # look-back window (lines)
# Match actual call sites only — `export_price_series(` (with open paren)
# or `export_price_series for X` (the imperative-instruction form). Bare
# backtick mentions in prose are discussion, not a call.
RISKY_RE='export_price_series\(|export_price_series` for|export_price_series` per'
RISKY_LABEL='export_price_series'
# Guard keywords that signal the author is aware of the asset-class split.
# Includes the partner endpoint (etf_daily_price) — if both endpoints are
# mentioned within the window, the dual-routing pattern is already in scope.
GUARD_RE='etf_profile|etf_daily_price|asset.class|Pre-classification|branch on asset|equity branch|Asset-class|equity legs'

if [[ $# -gt 0 ]]; then
  SKILLS=()
  for s in "$@"; do
    SKILLS+=("skills/$s/SKILL.md")
  done
else
  # All skill SKILL.md files except _parallax/
  while IFS= read -r f; do SKILLS+=("$f"); done < <(
    find skills -mindepth 2 -maxdepth 2 -name SKILL.md \
      | grep -v '/_parallax/' \
      | sort
  )
fi

violations=0
checked=0

# ----- Class B: skill-specific scaffolding (cio-letter-prep) ------------------
#
# Fires only if `skills/cio-letter-prep/` exists, so older branches and
# checkouts predating the skill stay clean. Increments the unified
# `violations` counter; emits `FAIL  <path>: <reason>` lines.
check_cio_letter_prep_structure() {
  local root="skills/cio-letter-prep"
  local skill_md="$root/SKILL.md"
  local scripts_dir="$root/scripts"
  local mocks_dir="$scripts_dir/mcp_mocks"

  # 1. SKILL.md must exist
  if [[ ! -f "$skill_md" ]]; then
    violations=$((violations + 1))
    echo "FAIL  $skill_md: missing (cio-letter-prep skill present but SKILL.md absent)"
    return  # nothing else to check without the file
  fi

  # 2. Frontmatter keys — must appear on their own line at the top of the file.
  # Extract the leading frontmatter block (between the first two `---` lines).
  local frontmatter
  frontmatter=$(awk 'NR==1 && /^---[[:space:]]*$/ {flag=1; next} flag && /^---[[:space:]]*$/ {exit} flag' "$skill_md")
  if [[ -z "$frontmatter" ]]; then
    violations=$((violations + 1))
    echo "FAIL  $skill_md: missing or malformed YAML frontmatter (expected leading --- ... --- block)"
  else
    local key
    for key in name description negative-triggers gotchas; do
      if ! grep -qE "^${key}:" <<< "$frontmatter"; then
        violations=$((violations + 1))
        echo "FAIL  $skill_md: frontmatter missing required key '${key}:'"
      fi
    done
  fi

  # 3. Body must cite conventions, math helper, and contract tests.
  if ! grep -q '_parallax/parallax-conventions' "$skill_md"; then
    violations=$((violations + 1))
    echo "FAIL  $skill_md: must cite '_parallax/parallax-conventions' (JIT-load reference)"
  fi
  if ! grep -q 'scripts/contribution\.py' "$skill_md"; then
    violations=$((violations + 1))
    echo "FAIL  $skill_md: must cite 'scripts/contribution.py' (math helper)"
  fi
  if ! grep -qE 'test_mcp_contracts|mcp_mocks' "$skill_md"; then
    violations=$((violations + 1))
    echo "FAIL  $skill_md: must cite 'test_mcp_contracts' or 'mcp_mocks' (MCP contract tests)"
  fi

  # 4. Required scripts exist
  local required_file
  for required_file in \
    "$scripts_dir/contribution.py" \
    "$scripts_dir/test_contribution.py" \
    "$scripts_dir/test_mcp_contracts.py"; do
    if [[ ! -f "$required_file" ]]; then
      violations=$((violations + 1))
      echo "FAIL  $required_file: missing (required by cio-letter-prep)"
    fi
  done

  # 5. mcp_mocks/ must contain ≥ 9 .json files
  if [[ ! -d "$mocks_dir" ]]; then
    violations=$((violations + 1))
    echo "FAIL  $mocks_dir: missing directory (cio-letter-prep requires ≥ 9 MCP mock JSONs)"
  else
    local mock_count
    mock_count=$(find "$mocks_dir" -maxdepth 1 -name '*.json' -type f | wc -l | tr -d ' ')
    if [[ "$mock_count" -lt 9 ]]; then
      violations=$((violations + 1))
      echo "FAIL  $mocks_dir: contains $mock_count .json file(s); cio-letter-prep requires ≥ 9"
    fi
  fi

  # 6. Optionally run the actual test suite. Strongest check; gated on pytest.
  if command -v pytest >/dev/null 2>&1; then
    if [[ -d "$scripts_dir" ]]; then
      if ! pytest "$scripts_dir" -q --no-header >/tmp/cio-letter-prep-pytest.log 2>&1; then
        violations=$((violations + 1))
        echo "FAIL  $scripts_dir: pytest suite failed (see /tmp/cio-letter-prep-pytest.log)"
        # Surface the tail so CI logs include the failure summary inline.
        tail -20 /tmp/cio-letter-prep-pytest.log 2>/dev/null \
          | sed 's/^/      | /'
      fi
    fi
  else
    echo "WARN  cio-letter-prep: pytest not on PATH; skipping test-suite check"
  fi
}

for skill_md in "${SKILLS[@]}"; do
  [[ -f "$skill_md" ]] || { echo "  SKIP: $skill_md (not found)" >&2; continue; }
  checked=$((checked + 1))

  # Each line that mentions the risky tool
  while IFS=: read -r line_num _; do
    [[ -z "$line_num" ]] && continue

    # Compute the look-back window start
    start=$((line_num - WINDOW))
    [[ $start -lt 1 ]] && start=1

    # Pull the window (start..line_num inclusive)
    window=$(sed -n "${start},${line_num}p" "$skill_md")

    # Escape hatch: if the line ABOVE the match has the ignore comment, skip
    prev_line=$((line_num - 1))
    if [[ $prev_line -gt 0 ]]; then
      prev_text=$(sed -n "${prev_line}p" "$skill_md")
      if grep -qE 'coverage-lint:\s*ignore-next' <<< "$prev_text"; then
        continue
      fi
    fi

    # Pass if the window contains a guard keyword
    if grep -qE "$GUARD_RE" <<< "$window"; then
      continue
    fi

    # Otherwise fail
    violations=$((violations + 1))
    echo "FAIL  $skill_md:$line_num — $RISKY_LABEL without asset-class guard in last $WINDOW lines"
    # Show the offending line for context
    offending=$(sed -n "${line_num}p" "$skill_md")
    echo "      → $offending"
  done < <(grep -nE "$RISKY_RE" "$skill_md" || true)
done

# ----- Class B invocation: only when the skill is present in this checkout ----
if [[ -d "skills/cio-letter-prep" ]]; then
  check_cio_letter_prep_structure
fi

echo ""
echo "Lint complete. Checked $checked skill files; $violations violation(s)."

if [[ $violations -gt 0 ]]; then
  echo ""
  echo "Fix: add an asset-class pre-classification step (call etf_profile on each"
  echo "symbol; route ETF symbols through etf_daily_price). See:"
  echo "  - skills/_parallax/coverage-matrix.md"
  echo "  - skills/pair-finder/SKILL.md   (Batch C, suggestion mode)"
  echo "  - skills/explain-portfolio/SKILL.md   (Step 1a)"
  exit 1
fi
