#!/usr/bin/env python3
"""Build Parallax distribution artifacts from skills/.

Subcommands:
  plugin        Assemble the Claude Code plugin bundle (general-release set) at
                <repo>/plugin/ and write .claude-plugin/marketplace.json.
                Output is generated — never hand-edit plugin/; rerun this instead.
  verify dir... Check staged package directories (no symlinks or
                development files; text types and UTF-8 only; term scan).
                build-skills.sh runs it before zipping.
  files skill   Print a skill's tracked runtime files (development files
                removed), one per line. build-skills.sh copies this list.
  web [name...] Build self-contained .skill zips for claude.ai upload at
                ~/Downloads/claude-web-skills/. Defaults to WEB_SKILLS.
                Shared-file dependencies are vendored under <skill>/_vendored/
                and references rewritten, so each zip is standalone.

Relation to skills/build-skills.sh: the two claude.ai packagers cover disjoint
tiers. `web` here owns the general-release Parallax workflow set (WEB_SKILLS,
vendored + description-capped). build-skills.sh remains the per-skill packager
for the translate-* skills and the private-beta tier (output
~/Downloads/<name>.skill, with its own reference-integrity lints). Add a skill
to exactly one of the two sets, never both.

Both paths copy git-TRACKED files only (via `git ls-files`), apply the
distribution transforms below, and run a term-scan gate before emitting
anything. The scan's local-only extra terms live one-per-line in
~/.claude/parallax-canary-extra.txt (never tracked in this repo); the build
FAILS CLOSED when that file is absent unless PARALLAX_ALLOW_PARTIAL_SCAN=1
is set (see load_canary_terms).

Stdlib-only; runs under python >= 3.9.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parents[1]          # skills/

# `_parallax/skill_manifest.py` is the single source for the per-skill registries
# below. Loaded by path, not by package import: this module is itself loaded via
# importlib.util in the tests, so it has no reliable package context.
_manifest_spec = importlib.util.spec_from_file_location(
    "parallax_skill_manifest", SCRIPT_DIR.parent / "skill_manifest.py"
)
skill_manifest = importlib.util.module_from_spec(_manifest_spec)
_manifest_spec.loader.exec_module(skill_manifest)
REPO_ROOT = SKILLS_DIR.parent
PLUGIN_DIR = REPO_ROOT / "plugin"
MARKETPLACE_FILE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
WEB_OUT_DIR = Path.home() / "Downloads" / "claude-web-skills"
EXTRA_CANARY_FILE = Path.home() / ".claude" / "parallax-canary-extra.txt"

PLUGIN_VERSION = "0.1.0"
# Derived per build from the skills actually bundled: the same source builds
# parallax-workflows (translate-* present) and the parallax-agent tap output
# (translate-* absent), and the marketplace listing must match what installs.
# The comma before {translation} belongs to the substitution, not the template:
# a build that excludes translate-* renders the clause empty, and a hardcoded
# comma would leave "screening, and client-review" in the description the
# marketplace installer shows.
PLUGIN_DESCRIPTION_TEMPLATE = (
    "Parallax equity-research workflows: stock evaluation, portfolio analysis, "
    "screening{translation} and client-review skills powered by the Parallax "
    "MCP server."
)

# General-release skill set (same tiering convention as build-skills.sh:
# skills outside this list are not built by the no-arg default paths).
PLUGIN_SKILLS = skill_manifest.plugin_skills()

# PLUGIN_SKILLS entries that are legitimately absent from some checkouts (the
# parallax-agent tap ships without them). Anything else missing is a typo or an
# un-updated rename and must fail the build rather than silently shrink it.
KNOWN_OPTIONAL_SKILLS = {
    "translate-chinese-finance",
    "translate-thai-finance",
    "translate-vietnamese-finance",
}

# General-release web shortlist (claude.ai channel).
WEB_SKILLS = skill_manifest.web_skills()

# claude.ai caps skill descriptions at 200 chars; source frontmatter runs longer.
# Every web-built skill MUST have an entry here (build fails otherwise).
WEB_DESCRIPTIONS = skill_manifest.web_descriptions()

# Shared-tree paths (relative to skills/_parallax/) shipped with distributions.
# Directories are included recursively (tracked files only).
PARALLAX_INCLUDE = [
    "translation_validate.py",
    "parallax-conventions.md",
    "response-schemas.md",
    "coverage-matrix.md",
    "token-costs.md",
    "skill-structure-conventions.md",
    "jit-load-compliance-audit.md",
    "render_gate.py",
    "coverage_check.py",
    # The bundled white-label test imports skill_manifest.py, which reads
    # manifest.json; both must ship or that test tree breaks at import time.
    "skill_manifest.py",
    "manifest.json",
    "white-label",
    "house-view/loader.md",
    "house-view/schema.yaml",
    "house-view/render_helpers.md",
    "house-view/view_status.py",
    "house-view/gap_detect.py",
    "house-view/gap_suggest.py",
    "house-view/auto-on-load-judge-pattern.md",
    "client-policy/schema.yaml",
    "client-policy/policy-loader.md",
    "client-policy/adaptation.py",
    "client-policy/reconcile.py",
    "client-policy/requirements.txt",
    "AI-profiles/output-template.md",
]

# Distribution scan terms. Extra local-only terms come from EXTRA_CANARY_FILE.
# Branding-only canaries (glyphs + framework code-name) must appear NOWHERE in
# this public repo, including as literals here. Assemble them from codepoints so
# a plain-text scan of this tracked file never surfaces them; the gate still runs
# self-contained on any checkout with identical behavior. The snake_case /
# compute_* identifiers below are the public data contract (safe as literals).
_BRANDING_CANARIES = ["".join(map(chr, cps)) for cps in (
    (0x03A9,), (0x03A6,), (0x039E,), (0x03A8,),   # four branding glyphs
    (0x50, 0x52, 0x49, 0x53, 0x4D),               # framework code-name
)]
# Public MCP response fields that contain a scan term as a substring. These are
# part of the published data contract (already documented publicly in
# response-schemas.md), not internal identifiers — masked before scanning so
# case-insensitive matching does not fail the build on the public contract.
CANARY_ALLOWLIST = [
    "pick_toscore",
]

CANARY_TERMS = [
    "econometrics_phase",
    "valuation_state",
    "market_entropy",
    "psychological_wavelength",
    "compute_omega",
    "compute_phi",
    "compute_xi",
    "compute_psi",
    *_BRANDING_CANARIES,
]


class BuildError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Text transform helpers — every anchor MUST match or the build fails, so a
# drifted source file can never silently ship untransformed.
# --------------------------------------------------------------------------

def _cut(text: str, start: str, end: str, label: str) -> str:
    """Remove [start, end) — keeps the end anchor."""
    i = text.find(start)
    if i < 0:
        raise BuildError(f"transform anchor not found ({label}): start marker")
    j = text.find(end, i)
    if j < 0:
        raise BuildError(f"transform anchor not found ({label}): end marker")
    return text[:i] + text[j:]


def _swap(text: str, old: str, new: str, label: str, what: str = "old text") -> str:
    n = text.count(old)
    if n == 0:
        raise BuildError(f"transform anchor not found ({label}): {what}")
    if n > 1:
        raise BuildError(
            f"transform anchor not unique ({label}): {what} matched {n} times")
    return text.replace(old, new, 1)


def _drop_line(text: str, line: str, label: str) -> str:
    return _swap(text, line + "\n", "", label, what="line")


def _drop_line_prefix(text: str, prefix: str, label: str) -> str:
    """Drop the single line starting with `prefix`. Tolerates suffix drift
    (the tap sync flattens markdown links downstream, so the same source line
    is bracketed in parallax-workflows and plain in parallax-agent). Still
    fails loudly when the line is absent or ambiguous."""
    matches = [ln for ln in text.splitlines() if ln.startswith(prefix)]
    if not matches:
        raise BuildError(f"transform anchor not found ({label}): line prefix")
    if len(matches) > 1:
        raise BuildError(
            f"transform anchor not unique ({label}): prefix matched {len(matches)} lines")
    return _swap(text, matches[0] + "\n", "", label, what="line")


def _swap_every(text: str, old: str, new: str, label: str) -> str:
    """Replace EVERY occurrence. For anchors that legitimately recur (a command
    named in several error messages); still fails loudly when none match, so a
    renamed source anchor cannot silently no-op."""
    if old not in text:
        raise BuildError(f"transform anchor not found ({label}): recurring text")
    return text.replace(old, new)


HV_OPERATOR_TOOLING = "the house-view operator tooling"
HV_OPERATOR_COMMAND = "`/parallax-load-house-view"


def _swap_operator_commands(text: str, variants: tuple, label: str) -> str:
    """Each variant is optional (a source edit may legitimately drop one), but
    no backticked command form may survive the loop: a renamed flag matches no
    variant, and without a post-condition the renamed command would ship in the
    bundle untransformed with no build error."""
    for variant in variants:
        if variant in text:
            text = _swap_every(text, variant, HV_OPERATOR_TOOLING, label)
    if HV_OPERATOR_COMMAND in text:
        raise BuildError(
            f"transform anchor not found ({label}): a command form outside the "
            f"variant list survived the transform")
    return text


def transform_hv_loader(text: str) -> str:
    text = _cut(text, "### Framework components", "### Factor aliases",
                "loader.md components")
    # The house-view RUNTIME ships (this loader, the schema, the helper modules)
    # but every operator command that produces or repairs a view is excluded from
    # the bundle. Left as-is, the recovery paths in these error messages tell a
    # plugin user to run commands they do not have. Longest form first so the
    # flagged variants are rewritten before the bare command.
    return _swap_operator_commands(
        text,
        ("`/parallax-load-house-view --apply-judge <audit-hash>`",
         "`/parallax-load-house-view --apply-stress <audit-hash>`",
         "`/parallax-load-house-view --re-pair`",
         "`/parallax-load-house-view --extend`",
         "`/parallax-load-house-view --clear`",
         "`/parallax-load-house-view --edit`",
         "`/parallax-load-house-view`"),
        "loader.md operator command")


def transform_view_status(text: str) -> str:
    """Same problem as loader.md, but in runtime banner strings a user actually
    sees: every recovery path names an operator command the bundle excludes."""
    return _swap_operator_commands(
        text,
        ("`/parallax-load-house-view --extend`",
         "`/parallax-load-house-view --edit`",
         "`/parallax-load-house-view`"),
        "view_status operator command")


# A skill named in a shipped doc, as `/parallax-x` or bare `parallax-x`. Only
# names that are real skills (manifest rows) count, so prose cannot trip it.
_SKILL_REF = re.compile(r"(?<![\w-])/?((?:parallax|translate)-[a-z0-9-]*[a-z0-9])")


def named_skills(text: str) -> set[str]:
    return set(_SKILL_REF.findall(text)) & set(skill_manifest.skills())


def filter_token_costs(text: str, available: set[str]) -> str:
    """Keep only the cost rows, bullets and callouts for skills this
    distribution ships. Drops a table row whose first cell names an
    unavailable skill, a `-` bullet or `>` callout that names one, and a `###`
    section whose table ends up with no rows. Fails if any unavailable skill
    is still named afterwards."""
    lines = text.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            if named_skills("".join(lines[i:j])) - available:
                if j < len(lines) and not lines[j].strip():
                    j += 1                      # and the blank line after it
            else:
                out.extend(lines[i:j])
            i = j
            continue
        if (line.startswith("|") and not line.startswith("|---")
                and named_skills(line.split("|")[1]) - available):
            i += 1
            continue
        if line.startswith("- ") and named_skills(line) - available:
            i += 1
            continue
        out.append(line)
        i += 1
    sections = re.split(r"(?m)^(?=#{1,3} )", "".join(out))
    kept = []
    for sec in sections:
        rows = [ln for ln in sec.splitlines() if ln.startswith("|")]
        if sec.startswith("### ") and rows and len(rows) <= 2:
            continue                            # header + separator only
        kept.append(sec)
    text = "".join(kept)
    left = named_skills(text) - available
    if left:
        raise BuildError(f"token-costs still names skills this distribution "
                         f"does not ship: {sorted(left)}")
    return text


# House-view operator skills install together, outside the plugin and web sets.
# Every mention of one applies only once a house view exists, and a view
# exists only through them, so they are never marked unavailable.
HOUSE_VIEW_OPERATORS = frozenset({
    "parallax-load-house-view", "parallax-make-house-view",
    "parallax-judge-house-view", "parallax-stress-house-view",
    "parallax-house-view-diff", "parallax-house-view-attribution",
})

# Appended to a slash command for a skill the distribution does not ship, so
# a reader is never told to run something that is not installed.
PLUGIN_NOTE = " (not in the plugin)"
WEB_NOTE = " (not available on claude.ai)"
# A link target is left alone: a note inside `](...)` would break the link.
_CMD_REF = re.compile(
    r"(?<![\w/.~-])(?<!\]\()/((?:parallax|translate)-[a-z0-9-]*[a-z0-9])\b")
_CODE_SPAN = re.compile(r"(`[^`\n]*`)")


def annotate_unavailable_commands(text: str, available: set[str],
                                  note: str = PLUGIN_NOTE) -> str:
    """Mark every `/parallax-x` command whose skill is not in `available`.
    Inside a code span the note goes after the span; fenced code blocks are
    left as written so examples stay copyable. Idempotent. Only real skill
    names (manifest rows) count."""
    known = set(skill_manifest.skills())

    def unavailable(name: str) -> bool:
        return name in known and name not in available and name not in HOUSE_VIEW_OPERATORS

    out, fenced = [], False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if fenced or line.lstrip().startswith("```"):
            out.append(line)                    # examples stay copyable
            continue
        pieces = _CODE_SPAN.split(line)
        for i, piece in enumerate(pieces):
            after = pieces[i + 1] if i + 1 < len(pieces) else ""
            if _CODE_SPAN.fullmatch(piece):
                if (any(unavailable(n) for n in _CMD_REF.findall(piece))
                        and not after.startswith(note)):
                    pieces[i] = piece + note
            else:
                pieces[i] = _CMD_REF.sub(
                    lambda m, p=piece: m.group(0) + (
                        note if unavailable(m.group(1))
                        and not p[m.end():].startswith(note) else ""),
                    piece)
        out.append("".join(pieces))
    return "".join(out)


def annotate_tree(root: Path, available: set[str], note: str) -> None:
    """Apply annotate_unavailable_commands to every staged .md and .yaml."""
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".yaml"):
            text = path.read_text(encoding="utf-8")
            new = annotate_unavailable_commands(text, available, note)
            if new != text:
                path.write_text(new, encoding="utf-8")


def filter_shipped_docs(parallax_root: Path, available: set[str]) -> None:
    """Apply the skill-set filters to staged shared docs (plugin and web)."""
    path = parallax_root / "token-costs.md"
    if path.is_file():
        path.write_text(filter_token_costs(path.read_text(encoding="utf-8"),
                                           available), encoding="utf-8")


def transform_macro_outlook(text: str) -> str:
    """Drop the routing line to an investor-profile skill the bundle excludes."""
    return _drop_line(
        text,
        "- Regime-driven directional trade ideas for a specific ticker → "
        "use /parallax-ai-soros",
        "macro-outlook ai-soros route")


def transform_thematic_screen(text: str) -> str:
    """Drop the routing line to an investor-profile skill the bundle excludes."""
    return _drop_line(
        text,
        "- Regime-first or reflexivity-driven trade ideas "
        '(e.g., "trade ideas in current rates regime") → use /parallax-ai-soros',
        "thematic-screen ai-soros route")


def transform_hv_schema(text: str) -> str:
    text = _cut(text, "# Framework decomposition — four components",
                "# " + "-" * 75, "schema.yaml header block")
    text = _cut(text, "  # Framework component scores",
                "  # 11 GICS sectors", "schema.yaml tilts block")
    text = _drop_line(
        text,
        "    pillars: {}                              # e.g., {valuation_state: 0.4}",
        "schema.yaml conviction key")
    text = _drop_line(
        text,
        "    pillars: 0.75                            # added 2026-04-22 — framework component scores",
        "schema.yaml confidence key")
    text = _drop_line(
        text,
        "#       pillars: {econometrics_phase: 0}    # stripped (zero)",
        "schema.yaml fixture line")
    return text


def transform_portfolio_builder(text: str) -> str:
    """Drop the operator-verification link. It points at
    examples/testing-posture.md, whose smoke tests exercise the house-view
    operator layer (parallax-load-house-view etc.) that is excluded from the
    plugin. Removing the reference also stops the doc from being bundled —
    examples/ files ship only when a shipped skill still references them. The
    source SKILL.md keeps the link for full-clone users who have that layer."""
    return _drop_line_prefix(
        text,
        "- **Operator verification:** see ",
        "portfolio-builder operator-verification link")


def transform_white_label_stock_report(text: str) -> str:
    """Drop the /parallax-cio-letter-prep route from the frontmatter
    description. That skill is excluded from the plugin, and the description is
    user-visible in the plugin's skill list, so naming it there advertises a
    command the bundle does not provide. The routing intent (this skill is not
    for monthly CIO LP letters) survives without the dangling slash command.
    The source SKILL.md keeps the route for full-clone users who have it."""
    text = _swap(
        text,
        "not for monthly CIO LP letters (use /parallax-cio-letter-prep),",
        "not for monthly CIO LP letters,",
        "white-label-stock-report cio-letter-prep route")
    # Same command, same rationale, in the body routing list — scrubbing only the
    # frontmatter left the route advertised two screens further down.
    return _drop_line(
        text,
        "- Monthly fund-manager letter to LPs → use /parallax-cio-letter-prep",
        "white-label-stock-report cio-letter-prep body route")


def transform_conventions_web(text: str) -> str:
    """Web-only. A .skill zip is self-contained: there is no parallax-workflows
    checkout to resolve against, and skill-structure-conventions.md is an
    authoring/meta doc excluded from web zips (WEB_VENDOR_EXCLUDE). Left as-is,
    step 1 sends the agent to a path that does not exist inside the artifact.
    Point it at the bundled _vendored/ copy instead. Plugin builds keep the
    original wording — that bundle does ship the shared tree and the meta doc."""
    return _swap(
        text,
        "Resolve every `_parallax/...` conventions and house-view path to the "
        "canonical `parallax-workflows` copy (see "
        "`_parallax/skill-structure-conventions.md` → "
        '"Canonical source & path resolution"). '
        "Do not assume the installed skill directory contains them.",
        "Resolve every `_parallax/...` conventions and house-view path to the "
        "`_vendored/_parallax/` copy bundled inside this skill. This artifact is "
        "self-contained — there is no external `parallax-workflows` checkout to "
        "resolve against.",
        "conventions web path-resolution directive")


def transform_conventions(text: str) -> str:
    text = _drop_line(
        text,
        "| Multi-investor consensus across factor-profile lenses | `/parallax-ai-consensus` skill "
        "| Orchestrates Buffett / Klarman / Greenblatt / Soros / PTJ profile skills. "
        "**Skill-only by design** — multi-profile orchestration with judgment fusion does "
        "NOT translate to a REST contract without freezing the ensemble. |",
        "conventions consensus row")
    text = _drop_line(
        text,
        "| Single-investor profile factor scoring | `/parallax-ai-buffett`, `-ai-soros`, "
        "`-ai-greenblatt`, `-ai-klarman`, `-ai-ptj` | Each is a standalone profile skill. "
        "Profiles ARE proprietary — see `_parallax/AI-profiles/`. |",
        "conventions profile row")
    return text


def transform_concierge(text: str) -> str:
    text = _swap(text,
                 "four-branch menu (Stock / Portfolio / Discovery / Investor profiles)",
                 "three-branch menu (Stock / Portfolio / Discovery)",
                 "concierge description")
    text = _swap(text,
                 "- Opening = **4 branches** (never the full skill list at once)",
                 "- Opening = **3 branches** (never the full skill list at once)",
                 "concierge opening count")
    text = _drop_line(
        text,
        "**\U0001f3a9 Investor profile** — Buffett / Greenblatt / Klarman / Soros / PTJ style read",
        "concierge menu item")
    text = _swap(text, "Four buckets. No long list.", "Three buckets. No long list.",
                 "concierge buckets")
    text = _drop_line(
        text, "| Investor-style read | route to \U0001f3a9 Investor profile branch |",
        "concierge stock-branch row")
    text = _drop_line(
        text, "| CIO / quarterly letter prep | `/parallax-cio-letter-prep` |",
        "concierge letter row")
    text = _cut(text, "**House-view operations** (internal routing",
                "## \U0001f30d Discovery branch", "concierge house-view block")
    text = _cut(text, "## \U0001f3a9 Investor profile branch",
                "## Nudging after each skill runs", "concierge profile branch")
    text = _drop_line(text, '- "Run a Buffett-style read on this, or pause?"',
                      "concierge stock nudge")
    text = _cut(text, "**After an Investor-profile skill:**",
                "Always 2-3 options. Never 6.", "concierge profile nudges")
    text = _swap(
        text,
        "  - Investor-lens keyword + ticker (Buffett / Greenblatt / Klarman / Soros / PTJ) →\n"
        "    matching `/parallax-ai-<name> <ticker>`, then nudges\n",
        "",
        "concierge payload shortcut")
    text = _swap(text, "- **Open with exactly 4 branches.**",
                 "- **Open with exactly 3 branches.**", "concierge rule count")
    return text


def transform_output_template(text: str) -> str:
    """Distribution copy carries only the sections consumer skills render by
    reference from parallax-conventions.md (verdict language rules + the
    standard disclaimer). The full template ships with the AI investor-profile
    skills, which are not part of this distribution."""
    i5 = text.find("### 5. Verdict")
    j5 = text.find("### 6. Synthesis")
    i8 = text.find("### 8. Standard disclaimer (REQUIRED, VERBATIM)")
    j8 = text.find("## Rendering rules")
    if min(i5, j5, i8, j8) < 0 or not (i5 < j5 <= i8 < j8):
        raise BuildError("transform anchor not found (output-template sections)")
    return (
        "# Parallax AI Investor Profile — Output Template (distribution subset)\n\n"
        "This copy carries the sections that consumer skills render by reference from "
        "`parallax-conventions.md` (verdict language rules and the standard disclaimer). "
        "The full template ships with the AI investor-profile skills.\n\n"
        + text[i5:j5].rstrip() + "\n\n"
        + text[i8:j8].rstrip() + "\n"
    )


# Keyed by path relative to skills/.
TRANSFORMS = {
    "_parallax/house-view/loader.md": transform_hv_loader,
    "_parallax/house-view/schema.yaml": transform_hv_schema,
    "_parallax/parallax-conventions.md": transform_conventions,
    "_parallax/AI-profiles/output-template.md": transform_output_template,
    "_parallax/house-view/view_status.py": transform_view_status,
    "parallax-macro-outlook/SKILL.md": transform_macro_outlook,
    "parallax-thematic-screen/SKILL.md": transform_thematic_screen,
    "parallax-concierge/SKILL.md": transform_concierge,
    "parallax-portfolio-builder/SKILL.md": transform_portfolio_builder,
    "parallax-white-label-stock-report/SKILL.md": transform_white_label_stock_report,
}

# Applied on top of TRANSFORMS, web build only (self-contained zips).
def transform_loader_web(text: str) -> str:
    """Web-only. loader.md cites skill-structure-conventions.md, an authoring
    doc excluded from web zips (WEB_VENDOR_EXCLUDE). Drop the pointer and keep
    the rule it explains. Plugin builds ship that doc and keep the citation."""
    return _swap(
        text,
        "(frontmatter carries spec keys only, per "
        "`_parallax/skill-structure-conventions.md` → \"Spec compliance\"; "
        "house content such as gotchas lives in the body)",
        "(frontmatter carries spec keys only; house content such as gotchas "
        "lives in the body)",
        "loader web skill-structure citation")


def transform_due_diligence_web(text: str) -> str:
    """Web-only. The client-safe refusal is rendered verbatim to the user, so
    it must not name a workflow claude.ai does not offer; nor should the
    routing bullet. Both keep their client-review alternative."""
    text = _swap(
        text,
        "for a client-facing deliverable use /parallax-client-review or "
        "/parallax-white-label-stock-report.",
        "for a client-facing deliverable use /parallax-client-review.",
        "due-diligence client-safe refusal")
    return _swap(
        text,
        "→ use /parallax-client-review (portfolio) or "
        "/parallax-white-label-stock-report (single name)",
        "→ use /parallax-client-review (portfolio)",
        "due-diligence client-forwardable route")


WEB_TRANSFORMS = {
    "_parallax/parallax-conventions.md": transform_conventions_web,
    "_parallax/house-view/loader.md": transform_loader_web,
    "parallax-due-diligence/SKILL.md": transform_due_diligence_web,
}


# --------------------------------------------------------------------------
# Unshipped-language strip (plugin and web builds)
#
# A language whose translate skill a distribution does not ship must not be
# advertised by it either: the lang= docs and the §15 routing table would
# otherwise send users to a skill that is not installed. Applied to staged
# files after assembly, and only when the translate skill is absent from the
# distribution's skill set.
# --------------------------------------------------------------------------

class UnshippedLanguage:
    """A translate skill that may be held out of the plugin, and the staged
    files that mention its language code. Each transform removes only this
    language's own tokens and note paragraph, so two held languages can share
    a lang= list without one strip breaking the other's anchor.

    A plain class, not a dataclass: test modules load this file through
    importlib without registering it in sys.modules, and @dataclass cannot
    resolve string annotations in that case."""

    def __init__(self, code: str, skill: str, route: str) -> None:
        self.code = code
        self.skill = skill
        self.route = route  # the §15.2 routing-table fragment to remove
        self.transforms: dict = {}


def _drop_paragraph_line(text: str, prefix: str, label: str) -> str:
    """Drop a one-line paragraph starting with `prefix`, together with the
    newline before it, so removing any subset of adjacent one-line paragraphs
    leaves exactly one blank line behind."""
    matches = [ln for ln in text.splitlines() if ln.startswith(prefix)]
    if len(matches) != 1:
        raise BuildError(
            f"transform anchor {'not found' if not matches else 'not unique'} "
            f"({label}): paragraph prefix")
    return _swap(text, "\n" + matches[0] + "\n", "", label, what="paragraph")


def _strip_conventions(lang: "UnshippedLanguage", text: str) -> str:
    code, skill = lang.code, lang.skill
    text = _swap(text, f", `{code}`", "", f"conventions §15.1 {code} supported value")
    text = _swap(text, f", {code}", "", f"conventions §15.1 {code} unsupported message")
    text = _drop_paragraph_line(text, f"`{code}` routes to `{skill}`",
                                f"conventions §15.1 {code} note")
    return _swap(text, lang.route, "", f"conventions §15.2 {code} route")


_LANG_LIST_DOCS = (
    "parallax-should-i-buy/SKILL.md",
    "parallax-morning-brief/SKILL.md",
    "parallax-deep-dive/SKILL.md",
    "parallax-client-review/SKILL.md",
    "parallax-score-explainer/SKILL.md",
)


def _unshipped_language(code: str, skill: str, route: str) -> UnshippedLanguage:
    lang = UnshippedLanguage(code, skill, route)
    lang.transforms["_parallax/parallax-conventions.md"] = (
        lambda t: _strip_conventions(lang, t))
    for rel in _LANG_LIST_DOCS:
        lang.transforms[rel] = (
            lambda t, code=code: _swap(t, f", `{code}`", "", f"{code} lang= list"))
    return lang


# Transforms are keyed by path relative to skills/. Entries whose file is not
# staged (a checkout without the translate-* skills) are skipped;
# strip_unshipped_languages then fails the build on any mention they missed.
UNSHIPPED_LANGUAGES = (
    _unshipped_language(
        "vi-VN", "translate-vietnamese-finance",
        "; `vi-VN` → `translate-vietnamese-finance`"),
    _unshipped_language(
        "ar-SA", "translate-arabic-finance",
        "; `ar-SA` → `translate-arabic-finance` (no `target_variant` line — "
        "omit it, same as Thai)"),
)


def strip_unshipped_languages(skills_root: Path, skills: list[str],
                              locate=None) -> None:
    """Remove each held language from the staged bundle when its translate
    skill is not bundled, then fail closed on any surviving mention.

    `locate` maps a transform's skills/-relative path to its staged file; the
    default is the plugin layout. The web build passes its _vendored layout."""
    locate = locate or (lambda rel: skills_root / rel)
    for lang in UNSHIPPED_LANGUAGES:
        if lang.skill in skills:
            continue
        for rel, transform in lang.transforms.items():
            path = locate(rel)
            if path is not None and path.is_file():
                path.write_text(transform(path.read_text(encoding="utf-8")),
                                encoding="utf-8")
        # Shared executable validators can support draft locales without
        # exposing a user-facing route. The gate checks operator-facing
        # documentation and data for the language code and the held skill's
        # name; manifest.json lists every skill by design.
        leaks = sorted(
            str(p.relative_to(skills_root)) for p in skills_root.rglob("*")
            if p.is_file() and p.suffix in (".md", ".html", ".json")
            and p.name != "manifest.json"
            and any(term in p.read_text(encoding="utf-8", errors="ignore")
                    for term in (lang.code, lang.skill)))
        if leaks:
            raise BuildError(
                f"{lang.code} is advertised but {lang.skill} is not bundled: "
                + ", ".join(leaks))


# --------------------------------------------------------------------------
# Source enumeration and copying (tracked files only)
# --------------------------------------------------------------------------

def tracked_files(rel_prefix: str) -> list[str]:
    """Repo-relative tracked paths under skills/<rel_prefix>."""
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", f"skills/{rel_prefix}"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    if not out:
        raise BuildError(f"no tracked files under skills/{rel_prefix}")
    return sorted(out)


def copy_transformed(rel_skill_path: str, dest_root: Path) -> None:
    """Copy skills/<rel_skill_path> to <dest_root>/<rel_skill_path>, applying
    the registered transform when one exists."""
    src = SKILLS_DIR / rel_skill_path
    dst = dest_root / rel_skill_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    if rel_skill_path in TRANSFORMS:
        text = src.read_text(encoding="utf-8")
        dst.write_text(TRANSFORMS[rel_skill_path](text), encoding="utf-8")
    else:
        shutil.copy2(src, dst)


def assemble_skill(name: str, dest_root: Path, include_tests: bool = True) -> None:
    for repo_path in tracked_files(name + "/"):
        rel = repo_path[len("skills/"):]
        if not include_tests and f"{name}/tests/" in rel:
            continue
        copy_transformed(rel, dest_root)


def assemble_parallax_shared(dest_root: Path) -> None:
    for entry in PARALLAX_INCLUDE:
        src = SKILLS_DIR / "_parallax" / entry
        if src.is_dir():
            for repo_path in tracked_files(f"_parallax/{entry}/"):
                copy_transformed(repo_path[len("skills/"):], dest_root)
        else:
            if not src.exists():
                raise BuildError(f"allowlisted shared file missing: _parallax/{entry}")
            copy_transformed(f"_parallax/{entry}", dest_root)


# --------------------------------------------------------------------------
# Gates: term scan + reference resolution
# --------------------------------------------------------------------------

PARTIAL_SCAN_ENV = "PARALLAX_ALLOW_PARTIAL_SCAN"


def load_canary_terms() -> list[str]:
    """Built-in terms plus the local-only extra list.

    FAILS CLOSED when the extra list is absent. It carries most of the terms, so
    a missing file silently halves the scan — and this repo is public, so a
    machine without it (CI, a fresh clone, a second workstation) would otherwise
    publish under a weakened gate while reporting success. Set
    PARALLAX_ALLOW_PARTIAL_SCAN=1 to proceed deliberately with built-ins only."""
    terms = list(CANARY_TERMS)
    if EXTRA_CANARY_FILE.exists():
        for line in EXTRA_CANARY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    elif os.environ.get(PARTIAL_SCAN_ENV) == "1":
        print(f"WARN: extra scan-term file not found ({EXTRA_CANARY_FILE}); "
              f"running with {len(terms)} built-in terms only "
              f"({PARTIAL_SCAN_ENV}=1)", file=sys.stderr)
    else:
        raise BuildError(
            f"extra scan-term file not found ({EXTRA_CANARY_FILE}). The term "
            f"scan would run with only {len(terms)} built-in terms, which is a "
            f"materially weaker gate on a public repo. Restore the file, or set "
            f"{PARTIAL_SCAN_ENV}=1 to proceed deliberately with a reduced scan.")
    return terms


# A combining mark continues the word it follows, so an allowlist entry with a
# mark glued on is a different identifier and must not be masked.
_WORDISH = r"\w\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f"


def _fold(text: str) -> str:
    """Lower-case with format characters (Cf) removed."""
    return "".join(c for c in text if unicodedata.category(c) != "Cf").lower()


def _mask_allowlisted(haystack: str) -> str:
    """Token-bounded masking of CANARY_ALLOWLIST entries (see canary_scan).
    Word characters are Unicode-aware, so a homoglyph or mark glued onto an entry keeps it
    unmasked and the scan still sees the term inside it."""
    for allowed in CANARY_ALLOWLIST:
        haystack = re.sub(
            rf"(?<![{_WORDISH}])" + re.escape(allowed.lower()) + rf"(?![{_WORDISH}])",
            "\x00", haystack)
    return haystack


def canary_scan(root: Path) -> None:
    """Case-INSENSITIVE substring scan. Warehouse/schema identifiers are written
    upper-case in the term list but appear lower-case in real prose and SQL, so a
    case-sensitive scan would wave through exactly the form a leak is most likely
    to take. Known-benign collisions are masked out first via CANARY_ALLOWLIST.

    The masking is TOKEN-BOUNDED and substitutes a sentinel rather than deleting.
    Plain `str.replace` would be unsafe in both directions: an allowlist entry
    that ends with a scan term (as the public field does) would strip that term
    out of every sibling identifier sharing the prefix, shipping a real leak
    (`<field>_raw`, `<field>_internal`) clean; and splicing the neighbours
    together can manufacture a term the file never contained.

    Decoding uses errors='replace' so a stray non-UTF-8 byte cannot exempt a
    file from the scan — the replacement char can never mask a term, and a
    binary that happens to trip a term fails the build loudly (the safe
    direction) instead of shipping unscanned."""
    terms = load_canary_terms()
    hits = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        # The path is scanned too: a file named after a term leaks the term.
        # Two haystacks, a hit in either fails: the plain text, and its NFKC
        # form (folds full-width and compatibility variants). NFKC alone would
        # lose hits, because a combining mark after a term's last letter
        # composes with it. Format characters (zero-width space, soft hyphen)
        # are removed from both so they cannot split a term. Encodings such
        # as base64 or HTML entities are out of scope.
        raw = f"{path.relative_to(root).as_posix()}\n{text}"
        for form in (raw, unicodedata.normalize("NFKC", raw)):
            haystack = _mask_allowlisted(_fold(form))
            for term in terms:
                if any(t in haystack for t in {_fold(term), _fold(
                        unicodedata.normalize("NFKC", term))}):
                    hits.append((path.relative_to(root), term))
    hits = sorted(set(hits), key=lambda h: (str(h[0]), h[1]))
    if hits:
        for rel, term in hits:
            print(f"  SCAN HIT: {rel}: {term}", file=sys.stderr)
        raise BuildError(f"term scan failed with {len(hits)} hit(s)")


# A skill directory name: lowercase letters, digits, hyphens. Anything else
# (`..`, a slash) could stage files outside the package.
SKILL_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")

# Packages carry text only: every file must be one of these types and valid
# UTF-8. A binary or a UTF-16 file cannot be term-scanned meaningfully, so it
# is refused rather than special-cased.
PACKAGE_TEXT_SUFFIXES = frozenset({".md", ".py", ".txt", ".yaml", ".yml", ".json"})
_DEV_DIRS = frozenset({"tests", "test", "__tests__", "fixtures", "notes",
                       "__pycache__", ".pytest_cache"})
_DEV_NOTES = frozenset({"plans.md", "handoff.md", "lessons.md", "decisions.md",
                        "learnings.md"})


def is_dev_path(rel: str) -> bool:
    """A path (relative to a skill dir) that is development material: tests,
    test fixtures, caches, dotfiles, notebooks, planning notes. One rule for
    both the file list build-skills.sh copies and verify_package."""
    parts = PurePosixPath(rel).parts
    name = parts[-1]
    return (any(p in _DEV_DIRS or p.startswith(".") for p in parts)
            or name.lower() in _DEV_NOTES or name in ("conftest.py", "tests.py")
            or name.endswith(".ipynb")
            or name.endswith(".py") and (name.startswith("test_")
                                         or name.endswith("_test.py")))


def verify_package(root: Path) -> None:
    """Checks every distributed package must pass before it is written: no
    symlinks, no development files, text files only (allowed types, valid
    UTF-8), then the term scan."""
    problems = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            problems.append(f"symlink: {rel}")
        elif not p.is_file():
            continue
        elif is_dev_path(rel):
            problems.append(f"development file: {rel}")
        elif p.suffix not in PACKAGE_TEXT_SUFFIXES:
            problems.append(f"not an allowed text type: {rel}")
        else:
            try:
                p.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                problems.append(f"not UTF-8: {rel}")
    if problems:
        raise BuildError(f"package check failed: {problems}")
    canary_scan(root)


REF_VENDORED = re.compile(r"_vendored/[A-Za-z0-9_./-]+\.(?:md|py|yaml|json)")


def web_resolution_check(skill_root: Path) -> None:
    """Every `_vendored/...` path named in a finished web skill must resolve
    inside that skill. Runs after rewrite_refs, so it sees exactly the paths the
    consuming agent will follow — the only point where a doc that survived
    vendoring exclusion (WEB_VENDOR_EXCLUDE) but is still referenced in prose
    shows up as a dangling directive."""
    failures = []
    for doc in sorted(skill_root.rglob("*.md")):
        text = doc.read_text(encoding="utf-8")
        if "<skill-dir>/../" in text:
            failures.append(f"{doc.relative_to(skill_root)}: <skill-dir>/../ "
                            "points outside the package")
        for ref in sorted({m.group(0) for m in REF_VENDORED.finditer(text)}):
            # _parallax/scripts/ is author-time repo tooling (lints, the bundler
            # itself) — never bundled by design, so a ref to it is not a break.
            n = posixpath.normpath(ref)
            if (n == "_vendored/_parallax/scripts"
                    or n.startswith("_vendored/_parallax/scripts/")):
                continue
            if not (skill_root / ref).exists():
                failures.append(f"{doc.relative_to(skill_root)}: {ref}")
    if failures:
        for f in failures:
            print(f"  UNRESOLVED: {f}", file=sys.stderr)
        raise BuildError(
            f"{len(failures)} unresolved vendored reference(s) in "
            f"{skill_root.name}")


_SIBLING_FILE = re.compile(
    r"""with_name\(\s*["']([\w.-]+)["']\s*\)"""
    r"""|__file__\s*\)(?:\.resolve\(\s*\))?\.parent\s*/\s*["']([\w.-]+)["']""")


def missing_python_siblings(skill_root: Path) -> list[str]:
    """Files a vendored module needs beside it but the package lacks: names
    opened with Path.with_name("...") or Path(__file__).parent / "...", and
    sibling modules it imports (a module is a sibling when the source tree has
    it in the same directory)."""
    vendored = skill_root / "_vendored" / "_parallax"
    missing = set()
    for py in sorted(skill_root.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        needed = {a or b for a, b in _SIBLING_FILE.findall(text)}
        if vendored in py.parents:
            src_dir = SKILLS_DIR / "_parallax" / py.parent.relative_to(vendored)
            modules = set()
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules.add(node.module.split(".")[0])
                elif isinstance(node, ast.Import):
                    modules.update(a.name.split(".")[0] for a in node.names)
            needed |= {m + ".py" for m in modules if (src_dir / (m + ".py")).is_file()}
        for n in needed:
            if not py.with_name(n).exists():
                missing.add(py.with_name(n).relative_to(skill_root).as_posix())
    return sorted(missing)


_IMPORTED_NAME = re.compile(r"\b(?:from|import)\s+([A-Za-z_]\w*)")


def missing_anchor_modules(skill_root: Path, anchors: set) -> list[str]:
    """Modules that a package's docs import from a directory they put on
    sys.path (a dir anchor) but that the package lacks. Only names that are
    modules in that source directory count, so ordinary prose cannot trip it."""
    text = "\n".join(p.read_text(encoding="utf-8") for p in skill_root.rglob("*.md"))
    names = set(_IMPORTED_NAME.findall(text))
    missing = []
    for rel in sorted(anchors):
        for n in sorted(names):
            if ((SKILLS_DIR / "_parallax" / rel / f"{n}.py").is_file()
                    and not (skill_root / "_vendored" / "_parallax" / rel / f"{n}.py").exists()):
                missing.append(f"_vendored/_parallax/{rel}/{n}.py")
    return missing


REF_PARALLAX = re.compile(r"_parallax/[A-Za-z0-9_./-]+")
REF_REFERENCES = re.compile(
    r"(\.\./)?[A-Za-z0-9_-]*/?references/[A-Za-z0-9_/-]+\.md")
# repo-root examples/ docs referenced from skills as ../../examples/<name>
REF_EXAMPLES = re.compile(r"\.\./\.\./(examples/[A-Za-z0-9_./-]+\.md)")


def _resolve_parallax_ref(skills_root: Path, ref: str) -> bool:
    ref = ref.rstrip(".")
    candidates = [ref, ref + ".py", ref + ".md"]
    return any((skills_root / c).exists() for c in candidates)


# Authoring guides addressed to skill developers, not runtime material. Their
# prose is full of illustrative placeholder paths (`references/X.md`,
# `references/step-3.md`) that are examples of how to structure a skill, not
# refs to real files — so they are exempt from resolution_check.
RESOLUTION_EXEMPT_DOCS = skill_manifest.exempt_docs()


def bundled_skill_docs(skills_root: Path) -> list[Path]:
    """Every markdown doc in the bundle — each skill's SKILL.md plus its
    references/ and nested docs, AND the shared _parallax/ tree. The shared tree
    is included deliberately: it carries cross-skill references of its own
    (loader.md → portfolio-checkup's health-flags.md, etc.) that nothing else
    validates, so excluding it wholesale left the plugin free to ship a broken
    reference undetected. Authoring guides stay in the list — their exemption is
    scoped to the one ref class it applies to, inside resolution_check."""
    return sorted(skills_root.rglob("*.md"))


def resolution_check(skills_root: Path) -> None:
    """Every shared-tree, references/, or examples/ path named in a bundled
    skill doc must resolve inside the artifact."""
    failures = []
    for doc in bundled_skill_docs(skills_root):
        skill_dir = skills_root / doc.relative_to(skills_root).parts[0]
        where = doc.relative_to(skills_root)
        text = doc.read_text(encoding="utf-8")
        for ref in set(REF_PARALLAX.findall(text)):
            # _parallax/scripts/ is author-time repo tooling (lints, the bundler
            # itself) — never bundled by design, so a ref to it is not a break.
            n = posixpath.normpath(ref)
            if n == "_parallax/scripts" or n.startswith("_parallax/scripts/"):
                continue
            if not _resolve_parallax_ref(skills_root, ref):
                failures.append(f"{where}: {ref}")
        # Only the references/ class is exempted for authoring guides — their
        # placeholder paths (references/X.md) are illustrative. Their _parallax/
        # and examples/ refs are real and stay checked; both docs ship in the
        # plugin, so a whole-file exemption would let a renamed shared doc ship
        # broken.
        exempt_refs = where.as_posix() in RESOLUTION_EXEMPT_DOCS
        for m in {x.group(0) for x in REF_REFERENCES.finditer(text)}:
            if "<" in m or exempt_refs:
                continue
            if not ((skill_dir / m).exists() or (doc.parent / m).exists()
                    or (skills_root / m).exists()):
                failures.append(f"{where}: {m}")
        for m in set(REF_EXAMPLES.findall(text)):
            if not (skills_root.parent / m).exists():
                failures.append(f"{where}: ../../{m}")
    if failures:
        for f in failures:
            print(f"  UNRESOLVED: {f}", file=sys.stderr)
        raise BuildError(f"{len(failures)} unresolved reference(s) in bundle")


# --------------------------------------------------------------------------
# Frontmatter (web build)
# --------------------------------------------------------------------------

def replace_description(skill_md: Path, new_desc: str) -> None:
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise BuildError(f"no frontmatter in {skill_md}")
    fm = parts[1]
    m = re.search(r'^description:.*?(?=^\w[\w-]*:|\Z)', fm, re.M | re.S)
    if not m:
        raise BuildError(f"no description key in {skill_md}")
    fm = fm[:m.start()] + f'description: "{new_desc}"\n' + fm[m.end():]
    skill_md.write_text("---\n".join([parts[0], fm, parts[2]]), encoding="utf-8")


# --------------------------------------------------------------------------
# plugin subcommand
# --------------------------------------------------------------------------

def effective_plugin_skills() -> list[str]:
    """PLUGIN_SKILLS filtered to dirs present in THIS repo. The list is shared
    between parallax-workflows (full set) and the parallax-agent tap output
    (which excludes some skills, e.g. translate-*). Only KNOWN_OPTIONAL_SKILLS
    may be absent — any other missing entry is a typo/rename and raises, so a
    bad list can never silently shrink the bundle. An empty result is a hard
    error."""
    present = [n for n in PLUGIN_SKILLS if (SKILLS_DIR / n / "SKILL.md").is_file()]
    missing = [n for n in PLUGIN_SKILLS if n not in present]
    unexpected = [n for n in missing if n not in KNOWN_OPTIONAL_SKILLS]
    if unexpected:
        raise BuildError(
            f"{len(unexpected)} PLUGIN_SKILLS entry/entries have no SKILL.md and "
            f"are not in KNOWN_OPTIONAL_SKILLS: {', '.join(unexpected)}")
    if missing:
        print(f"  ! plugin list: {len(missing)} optional skill(s) absent in this "
              f"repo, excluded from bundle: {', '.join(missing)}", file=sys.stderr)
    if not present:
        raise BuildError("no PLUGIN_SKILLS present in this repo; nothing to bundle")
    return present


def plugin_description(skills: list[str]) -> str:
    """Description matching what this build actually ships."""
    translation = ", translation," if any(
        n.startswith("translate-") for n in skills) else ""
    return PLUGIN_DESCRIPTION_TEMPLATE.format(translation=translation)


def build_plugin() -> None:
    skills = effective_plugin_skills()
    description = plugin_description(skills)
    staging = Path(tempfile.mkdtemp(prefix="parallax-plugin-"))
    try:
        skills_root = staging / "skills"
        for name in skills:
            assemble_skill(name, skills_root)
        assemble_parallax_shared(skills_root)
        strip_unshipped_languages(skills_root, skills)
        filter_shipped_docs(skills_root / "_parallax", set(skills))

        # repo-root examples/ docs referenced from bundled skills ship at
        # <plugin>/examples/ so the ../../examples/ relative form resolves.
        example_refs = set()
        for doc in bundled_skill_docs(skills_root):
            example_refs |= set(REF_EXAMPLES.findall(
                doc.read_text(encoding="utf-8")))
        for rel in sorted(example_refs):
            if not (REPO_ROOT / rel).is_file():
                raise BuildError(f"referenced examples doc missing: {rel}")
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / rel, dest)
        annotate_tree(staging, set(skills), PLUGIN_NOTE)

        manifest_dir = staging / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(json.dumps({
            "name": "parallax",
            "description": description,
            "version": PLUGIN_VERSION,
            "author": {"name": "Chicago Global", "url": "https://chicago.global"},
            "homepage": "https://parallax.chicago.global",
            "repository": "https://github.com/bencharoenwong/parallax-workflows",
            "license": "MIT",
        }, indent=2) + "\n", encoding="utf-8")

        canary_scan(staging)
        resolution_check(skills_root)

        if PLUGIN_DIR.exists():
            shutil.rmtree(PLUGIN_DIR)
        shutil.copytree(staging, PLUGIN_DIR)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    MARKETPLACE_FILE.parent.mkdir(exist_ok=True)
    MARKETPLACE_FILE.write_text(json.dumps({
        "name": "parallax-workflows",
        "description": "Claude Code workflows for Parallax equity research by Chicago Global.",
        "owner": {"name": "Chicago Global", "url": "https://chicago.global"},
        "plugins": [{
            "name": "parallax",
            "source": "./plugin",
            "description": description,
            "version": PLUGIN_VERSION,
        }],
    }, indent=2) + "\n", encoding="utf-8")

    print(f"  ✓ plugin bundle → {PLUGIN_DIR} ({len(skills)} skills)")
    print(f"  ✓ marketplace manifest → {MARKETPLACE_FILE}")


# --------------------------------------------------------------------------
# web subcommand
# --------------------------------------------------------------------------

CROSS_SKILL_REF = re.compile(
    r"(\.\./)?((?:parallax|translate)-[a-z0-9-]+)/(references/[A-Za-z0-9_./-]+)")
SKILL_DIR_GATE = "<skill-dir>/../_parallax/"
_PLACEHOLDER = "\x00SKILLDIR\x00"

# Shared files a vendored file needs at run time but the prose does not name.
# The prose names the entry module or doc only; these come along with it. A web
# build fails if a vendored .py names a sibling that is not shipped (see
# missing_python_siblings) or a doc imports an unshipped module from a sys.path
# directory (see missing_anchor_modules), so a new companion cannot be
# forgotten silently.
RUNTIME_COMPANIONS = {
    "house-view/gap_suggest.py": ("house-view/gap_detect.py",),
    "white-label/rm_consumer.py": ("white-label/loader.py",),
    "white-label/loader.py": ("white-label/schema.yaml",),
    # loader.md runs `python -m view_status` from the house-view directory.
    "house-view/loader.md": ("house-view/view_status.py",),
}

# Authoring/meta docs — not runtime material; left out of web zips even though
# the shared docs reference them in prose.
WEB_VENDOR_EXCLUDE = {"skill-structure-conventions.md", "jit-load-compliance-audit.md"}


def rewrite_refs(text: str, self_name: str = "") -> str:
    text = text.replace(SKILL_DIR_GATE, _PLACEHOLDER)
    text = text.replace("../../examples/", "_vendored/examples/")
    text = re.sub(r"(?<![\w/])(\.\./)?_parallax/", "_vendored/_parallax/", text)
    if self_name:
        # a cross-skill ref to the skill being built is just its own file
        text = re.sub(r"(\.\./)?" + re.escape(self_name) + r"/(references/)",
                      r"\2", text)
    text = re.sub(r"(?<!_vendored/)(\.\./)?((?:parallax|translate)-[a-z0-9-]+/references/)",
                  r"_vendored/\2", text)
    return text.replace(_PLACEHOLDER, "<skill-dir>/_vendored/_parallax/")


def allowed_parallax_dirs() -> list[str]:
    return sorted(e for e in PARALLAX_INCLUDE
                  if (SKILLS_DIR / "_parallax" / e).is_dir())


def collect_deps(md_text: str, strict: bool = True) -> tuple[set, set]:
    """(shared-tree refs, cross-skill refs) named in a markdown body.

    Only allowlisted (PARALLAX_INCLUDE) shared files are returned. Outside the
    allowlist: strict mode fails the build (the ref is load-bearing for the
    skill); lenient mode skips it (prose mention inside a vendored shared file).
    """
    allow_dirs = allowed_parallax_dirs()

    def allowed(rel: str) -> bool:
        return (rel in PARALLAX_INCLUDE
                or any(rel.startswith(d + "/") for d in allow_dirs))

    shared = set()
    for ref in REF_PARALLAX.findall(md_text):
        rel = ref.rstrip(".")[len("_parallax/"):].rstrip("/")
        if not rel:
            continue  # `_parallax/...` in prose is a placeholder, not a file
        candidates = [rel, rel + ".py", rel + ".md"]
        resolved = next((c for c in candidates
                         if (SKILLS_DIR / "_parallax" / c).is_file()
                         or ((SKILLS_DIR / "_parallax" / c).is_dir() and allowed(c))),
                        None)
        if resolved is not None and allowed(resolved):
            shared.add(resolved)
        elif strict:
            raise BuildError(f"shared ref outside distribution set: _parallax/{rel}")
    cross = set()
    for m in CROSS_SKILL_REF.finditer(md_text):
        skill, rel = m.group(2), m.group(3)
        if not (SKILLS_DIR / skill / rel).exists():
            raise BuildError(f"unresolvable cross-skill ref: {skill}/{rel}")
        cross.add((skill, rel))
    return shared, cross


def build_web(names: list[str]) -> None:
    WEB_OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        if name not in WEB_DESCRIPTIONS:
            raise BuildError(f"{name}: no web description override (claude.ai caps "
                             "descriptions at 200 chars; add one to WEB_DESCRIPTIONS)")
        desc = WEB_DESCRIPTIONS[name]
        if len(desc) > 200 or len(name) > 64:
            raise BuildError(f"{name}: web frontmatter limits exceeded "
                             f"(name {len(name)}/64, description {len(desc)}/200)")

        staging = Path(tempfile.mkdtemp(prefix="parallax-web-"))
        try:
            skill_root = staging / name
            assemble_skill(name, staging, include_tests=False)

            # Transitive closure of vendored deps, seeded from the skill's md files.
            shared_todo, cross_deps, example_refs = set(), set(), set()
            for md in sorted(skill_root.rglob("*.md")):
                body = md.read_text(encoding="utf-8")
                s, c = collect_deps(body, strict=True)
                shared_todo |= s
                cross_deps |= c
                example_refs |= set(REF_EXAMPLES.findall(body))
            for rel in sorted(example_refs):
                if not (REPO_ROOT / rel).is_file():
                    raise BuildError(f"referenced examples doc missing: {rel}")
                dest = skill_root / "_vendored" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO_ROOT / rel, dest)
            seeds = set(shared_todo)
            shared_done, dir_anchors = set(), set()
            while shared_todo:
                rel = shared_todo.pop()
                if rel in shared_done:
                    continue
                if rel in WEB_VENDOR_EXCLUDE and rel not in seeds:
                    continue
                shared_done.add(rel)
                if (SKILLS_DIR / "_parallax" / rel).is_dir():
                    # A directory ref (e.g. a sys.path entry) ships nothing by
                    # itself; the files the skill uses are named separately.
                    # web_resolution_check confirms the directory exists.
                    dir_anchors.add(rel)
                    continue
                dest = skill_root / "_vendored" / "_parallax" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                key = f"_parallax/{rel}"
                if key in TRANSFORMS or key in WEB_TRANSFORMS:
                    body = (SKILLS_DIR / "_parallax" / rel).read_text(
                        encoding="utf-8")
                    if key in TRANSFORMS:
                        body = TRANSFORMS[key](body)
                    if key in WEB_TRANSFORMS:
                        body = WEB_TRANSFORMS[key](body)
                    dest.write_text(body, encoding="utf-8")
                else:
                    shutil.copy2(SKILLS_DIR / "_parallax" / rel, dest)
                if rel.endswith(".md"):
                    s, c = collect_deps(dest.read_text(encoding="utf-8"),
                                        strict=False)
                    shared_todo |= s - shared_done
                    cross_deps |= c
                shared_todo |= set(RUNTIME_COMPANIONS.get(rel, ())) - shared_done
            # Cross-skill files can themselves reference other cross-skill
            # files — vendor to a fixpoint. Refs back to the skill being built
            # resolve to its own references/ (see rewrite_refs), so skip those.
            cross_done = set()
            while cross_deps - cross_done:
                skill, rel = (cross_deps - cross_done).pop()
                cross_done.add((skill, rel))
                if skill == name:
                    continue
                dest = skill_root / "_vendored" / skill / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(SKILLS_DIR / skill / rel, dest)
                if rel.endswith(".md"):
                    _, c = collect_deps(dest.read_text(encoding="utf-8"),
                                        strict=False)
                    cross_deps |= c

            web_available = set(WEB_SKILLS) | set(skill_manifest.standalone_skills("release"))
            filter_shipped_docs(skill_root / "_vendored" / "_parallax", web_available)
            for key, transform in WEB_TRANSFORMS.items():
                if key.startswith(f"{name}/"):
                    own = skill_root / key[len(name) + 1:]
                    own.write_text(transform(own.read_text(encoding="utf-8")),
                                   encoding="utf-8")
            # Languages whose translator is held stay out of web packages too.
            # The release-tier translators ship as standalone packages, so
            # their routes stay.
            def locate(rel: str, name: str = name) -> Path | None:
                if rel == f"{name}/SKILL.md":
                    return skill_root / "SKILL.md"
                return skill_root / "_vendored" / rel
            strip_unshipped_languages(skill_root, sorted(web_available), locate)
            for md in sorted(skill_root.rglob("*.md")):
                md.write_text(rewrite_refs(md.read_text(encoding="utf-8"), name),
                              encoding="utf-8")
            annotate_tree(skill_root, web_available, WEB_NOTE)
            replace_description(skill_root / "SKILL.md", desc)

            web_resolution_check(skill_root)
            for rel in sorted(dir_anchors):
                if not (skill_root / "_vendored" / "_parallax" / rel).is_dir():
                    raise BuildError(f"{name}: directory ref _parallax/{rel} names no "
                                     "vendored file; name the files the skill uses")
            missing = (missing_python_siblings(skill_root)
                       + missing_anchor_modules(skill_root, dir_anchors))
            if missing:
                raise BuildError(f"{name}: vendored code needs unshipped files: {missing}")
            verify_package(staging)

            out = WEB_OUT_DIR / f"{name}.skill"
            out.unlink(missing_ok=True)
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in sorted(skill_root.rglob("*")):
                    if path.is_file():
                        zf.write(path, path.relative_to(staging))
            size_kb = out.stat().st_size // 1024
            print(f"  ✓ {name} → {out} ({size_kb}K, "
                  f"{len(shared_done)} shared + {len(cross_deps)} cross-skill files vendored)")
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plugin")
    web = sub.add_parser("web")
    web.add_argument("names", nargs="*", default=None)
    verify = sub.add_parser("verify", help="check staged package directories")
    verify.add_argument("dirs", nargs="+", type=Path)
    files = sub.add_parser("files", help="tracked runtime files of one skill")
    files.add_argument("skill")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "plugin":
            build_plugin()
        elif args.cmd == "verify":
            for d in args.dirs:
                verify_package(d)
        elif args.cmd == "files":
            # Paths are tracked in the repo the caller runs from (cwd = the
            # skills/ dir build-skills.sh works in), relative to that cwd.
            skill = args.skill.rstrip("/")
            if not SKILL_NAME.fullmatch(skill):
                raise BuildError(f"invalid skill name: {args.skill!r}")
            listed = subprocess.run(
                ["git", "--literal-pathspecs", "ls-files", "-z", "--", f"{skill}/"],
                capture_output=True, check=True).stdout.decode("utf-8")
            paths = [f for f in listed.split("\0") if f]
            if not paths:
                raise BuildError(f"no tracked files under {skill}/ (run from skills/)")
            for f in paths:
                if not is_dev_path(PurePosixPath(f).relative_to(skill).as_posix()):
                    print(f)
        else:
            build_web(args.names or WEB_SKILLS)
    except BuildError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
