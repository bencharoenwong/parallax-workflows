#!/usr/bin/env bash
# coverage-lint.sh — flag asset-class / endpoint mismatches in SKILL.md files.
#
# Bug class: a SKILL.md instructs the runtime model to call an equity-only
# tool (e.g., `export_price_series`) on a symbol that may resolve to an ETF.
# The tool returns empty silently; the model substitutes a plausible-looking
# fallback; the user can't tell the output is degraded. See
# `_parallax/coverage-matrix.md` for the canonical tool/asset-class table.
#
# What this lints:
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
# Usage:
#   ./skills/_parallax/scripts/coverage-lint.sh         # lint all skills
#   ./skills/_parallax/scripts/coverage-lint.sh pair-finder explain-portfolio
#
# Exit:
#   0 — clean
#   1 — at least one violation found

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
