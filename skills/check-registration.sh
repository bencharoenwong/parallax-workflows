#!/usr/bin/env bash
# Install-health check: every skill in this repo that is registered under
# ~/.claude/skills/ should be a SYMLINK back into the repo, not a real-dir copy.
# Real-dir copies ("forks") drift silently — editing the repo no longer updates
# what the operator invokes. This is the detector for that failure mode.
#
# Scope note: only flags repo skills whose registered counterpart is a real dir.
# Standalone skills that live only under ~/.claude/skills (parallax-admin,
# parallax-deck-prep, parallax-template, ...) are NOT in this repo and are
# correctly ignored.
#
# Exit 0 = all registered repo skills are symlinks. Exit 1 = at least one fork.
# Advisory by default; wire into CI if you want a hard gate.
set -uo pipefail
cd "$(dirname "$0")"

reg_root="$HOME/.claude/skills"
forks=0 unreg=0 ok=0

lc() { printf '%s' "$1" | tr 'A-Z' 'a-z'; }

for d in */; do
  s=${d%/}
  [[ -f "$s/SKILL.md" ]] || continue
  reg="$reg_root/parallax-$(lc "$s")"
  if [[ -L "$reg" ]]; then
    ok=$((ok+1))
  elif [[ -d "$reg" ]]; then
    echo "  ✗ FORK (real dir, will drift): $reg  — should symlink -> $(pwd)/$s"
    forks=$((forks+1))
  else
    unreg=$((unreg+1))
  fi
done

echo ""
echo "registration summary: $ok symlinked, $forks fork(s), $unreg unregistered"
[[ $forks -eq 0 ]] || { echo "FAIL: $forks fork(s) drift from the repo. Reconcile then replace with a symlink."; exit 1; }
echo "PASS: all registered repo skills are symlinks."
