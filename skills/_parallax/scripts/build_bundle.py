#!/usr/bin/env python3
"""Build Parallax distribution artifacts from skills/.

Subcommands:
  plugin        Assemble the Claude Code plugin bundle (general-release set) at
                <repo>/plugin/ and write .claude-plugin/marketplace.json.
                Output is generated — never hand-edit plugin/; rerun this instead.
  web [name...] Build self-contained .skill zips for claude.ai upload at
                ~/Downloads/claude-web-skills/. Defaults to WEB_SKILLS.
                Shared-file dependencies are vendored under <skill>/_vendored/
                and references rewritten, so each zip is standalone.

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
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parents[1]          # skills/
REPO_ROOT = SKILLS_DIR.parent
PLUGIN_DIR = REPO_ROOT / "plugin"
MARKETPLACE_FILE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
WEB_OUT_DIR = Path.home() / "Downloads" / "claude-web-skills"
EXTRA_CANARY_FILE = Path.home() / ".claude" / "parallax-canary-extra.txt"

PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = (
    "Parallax equity-research workflows: stock evaluation, portfolio analysis, "
    "screening, translation, and client-review skills powered by the Parallax MCP server."
)

# General-release skill set (same tiering convention as build-skills.sh:
# skills outside this list are not built by the no-arg default paths).
PLUGIN_SKILLS = [
    "parallax-client-review",
    "parallax-concierge",
    "parallax-country-deep-dive",
    "parallax-credit-lens",
    "parallax-deep-dive",
    "parallax-due-diligence",
    "parallax-earnings-quality",
    "parallax-explain-portfolio",
    "parallax-halal-screen",
    "parallax-macro-outlook",
    "parallax-morning-brief",
    "parallax-pair-finder",
    "parallax-peer-comparison",
    "parallax-portfolio-builder",
    "parallax-portfolio-checkup",
    "parallax-rebalance",
    "parallax-scenario-analysis",
    "parallax-score-explainer",
    "parallax-should-i-buy",
    "parallax-thematic-screen",
    "parallax-watchlist-monitor",
    "parallax-white-label-onboard",
    "parallax-white-label-stock-report",
    "translate-chinese-finance",
    "translate-thai-finance",
]

# General-release web shortlist (claude.ai channel).
WEB_SKILLS = [
    "parallax-should-i-buy",
    "parallax-client-review",
    "parallax-portfolio-checkup",
    "parallax-score-explainer",
    "parallax-explain-portfolio",
    "parallax-watchlist-monitor",
    "parallax-morning-brief",
    "parallax-deep-dive",
    "parallax-due-diligence",
    "parallax-peer-comparison",
    "parallax-scenario-analysis",
    "parallax-rebalance",
]

# claude.ai caps skill descriptions at 200 chars; source frontmatter runs longer.
# Every web-built skill MUST have an entry here (build fails otherwise).
WEB_DESCRIPTIONS = {
    "parallax-should-i-buy": (
        "Quick stock evaluation: company overview, Parallax factor scores, financial "
        "health, trends, macro context, dividends, news, and analyst outlook in plain "
        "language. Accepts plain tickers or RICs."
    ),
    "parallax-client-review": (
        "RIA/wealth-advisor client portfolio review: analysis, redundancy, health flags, "
        "macro context, per-holding drill-down, and prioritized recommendations. "
        "Holdings as [{symbol, weight}]."
    ),
    "parallax-portfolio-checkup": (
        "Individual investor portfolio checkup: health flags, factor scores, redundancy, "
        "macro context, and plain-language recommendations. Holdings as [{symbol, weight}]."
    ),
    "parallax-score-explainer": (
        "Explain Parallax scores, factors, and methodology in plain language: why a "
        "stock scores the way it does and what would change it. Not for full stock analysis."
    ),
    "parallax-explain-portfolio": (
        "Portfolio drawdown attribution: decompose 'why am I down X%?' into market/regime, "
        "factor/thematic, and stock-specific components, with conditional guidance. "
        "Holdings as [{symbol, weight}]."
    ),
    "parallax-watchlist-monitor": (
        "Monitor a watchlist of tickers: flag score changes, news alerts, technical "
        "shifts, and analyst updates. Provide a list of symbols."
    ),
    "parallax-morning-brief": (
        "Fund manager morning brief: market regime, macro outlook, portfolio health, and "
        "key holding news. Portfolio as [{symbol, weight}] in RIC format."
    ),
    "parallax-deep-dive": (
        "Deep dive on a single position: profile, peers, financials, score trends, macro, "
        "technicals, dividends, news, and AI assessment. Symbol in RIC format. Not for "
        "quick checks or portfolio-level work."
    ),
    "parallax-due-diligence": (
        "Full research-analyst due diligence: financial statements, Palepu framework, "
        "technicals, news, score trends, and the full Parallax research report. Symbol "
        "in RIC format."
    ),
    "parallax-peer-comparison": (
        "Peer comparison for research analysts: peer snapshot, exported data, score "
        "trends, and relative price performance. Symbol in RIC format."
    ),
    "parallax-scenario-analysis": (
        "Stress a portfolio against a news event or scenario (rates +100bps, USD shock, "
        "2008 replay): exposure, sector impact, most-exposed holdings, rotation "
        "candidates. Needs portfolio + scenario."
    ),
    "parallax-rebalance": (
        "Portfolio rebalancing analysis: current state, health flags, macro context, and "
        "a prioritized information-framed action list with score rationale. Holdings as "
        "[{symbol, weight}]."
    ),
}

# Shared-tree paths (relative to skills/_parallax/) shipped with distributions.
# Directories are included recursively (tracked files only).
PARALLAX_INCLUDE = [
    "parallax-conventions.md",
    "response-schemas.md",
    "coverage-matrix.md",
    "token-costs.md",
    "skill-structure-conventions.md",
    "jit-load-compliance-audit.md",
    "render_gate.py",
    "white-label",
    "house-view/loader.md",
    "house-view/schema.yaml",
    "house-view/render_helpers.md",
    "house-view/view_status.py",
    "house-view/gap_detect.py",
    "house-view/gap_suggest.py",
    "house-view/auto-on-load-judge-pattern.md",
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


def transform_token_costs(text: str) -> str:
    """Drop the cost rows for house-view operator workflows. The bundle ships the
    house-view runtime but none of those commands, so pricing them advertises
    workflows a plugin user cannot run."""
    out = []
    dropped = 0
    excluded = ("/parallax-load-house-view", "/parallax-make-house-view",
                "/parallax-judge-house-view", "/parallax-stress-house-view",
                "/parallax-house-view-diff")
    for line in text.splitlines(keepends=True):
        if line.startswith("|") and any(f"`{c}`" in line for c in excluded):
            dropped += 1
            continue
        out.append(line)
    if dropped != len(excluded):
        raise BuildError(
            f"transform anchor not found (token-costs house-view rows): "
            f"dropped {dropped}, expected {len(excluded)}")
    text = "".join(out)
    # The two callouts below the table price and describe the same excluded
    # workflows; the auto-trigger one documents a drift check that cannot fire
    # in a bundle without the judge command.
    text = _cut(text, "> **Cost gotcha:**", "\n#", "token-costs cost-gotcha callout")
    return text


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
    return _drop_line(
        text,
        "- **Operator verification:** see "
        "[examples/testing-posture.md](../../examples/testing-posture.md)",
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
    "_parallax/token-costs.md": transform_token_costs,
    "_parallax/house-view/view_status.py": transform_view_status,
    "parallax-macro-outlook/SKILL.md": transform_macro_outlook,
    "parallax-thematic-screen/SKILL.md": transform_thematic_screen,
    "parallax-concierge/SKILL.md": transform_concierge,
    "parallax-portfolio-builder/SKILL.md": transform_portfolio_builder,
    "parallax-white-label-stock-report/SKILL.md": transform_white_label_stock_report,
}

# Applied on top of TRANSFORMS, web build only (self-contained zips).
WEB_TRANSFORMS = {
    "_parallax/parallax-conventions.md": transform_conventions_web,
}


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
        haystack = text.lower()
        for allowed in CANARY_ALLOWLIST:
            # \w (Unicode-aware) rather than [a-z0-9_]: an ASCII-only boundary
            # still masks an entry followed directly by a non-ASCII letter, so a
            # homoglyph glued onto the field name would suppress the term.
            haystack = re.sub(
                r"(?<!\w)" + re.escape(allowed.lower()) + r"(?!\w)",
                "\x00", haystack)
        for term in terms:
            if term.lower() in haystack:
                hits.append((path.relative_to(root), term))
    if hits:
        for rel, term in hits:
            print(f"  SCAN HIT: {rel}: {term}", file=sys.stderr)
        raise BuildError(f"term scan failed with {len(hits)} hit(s)")


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
        for ref in sorted({m.group(0) for m in REF_VENDORED.finditer(text)}):
            if not (skill_root / ref).exists():
                failures.append(f"{doc.relative_to(skill_root)}: {ref}")
    if failures:
        for f in failures:
            print(f"  UNRESOLVED: {f}", file=sys.stderr)
        raise BuildError(
            f"{len(failures)} unresolved vendored reference(s) in "
            f"{skill_root.name}")


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
RESOLUTION_EXEMPT_DOCS = {
    "_parallax/skill-structure-conventions.md",
    "_parallax/jit-load-compliance-audit.md",
}


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
            if ref.startswith("_parallax/scripts/"):
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

def build_plugin() -> None:
    staging = Path(tempfile.mkdtemp(prefix="parallax-plugin-"))
    try:
        skills_root = staging / "skills"
        for name in PLUGIN_SKILLS:
            assemble_skill(name, skills_root)
        assemble_parallax_shared(skills_root)

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

        manifest_dir = staging / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(json.dumps({
            "name": "parallax",
            "description": PLUGIN_DESCRIPTION,
            "version": PLUGIN_VERSION,
            "author": {"name": "Chicago Global", "url": "https://chicago.global"},
            "homepage": "https://chicago.global/parallax",
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
            "description": PLUGIN_DESCRIPTION,
            "version": PLUGIN_VERSION,
        }],
    }, indent=2) + "\n", encoding="utf-8")

    n_skills = len(PLUGIN_SKILLS)
    print(f"  ✓ plugin bundle → {PLUGIN_DIR} ({n_skills} skills)")
    print(f"  ✓ marketplace manifest → {MARKETPLACE_FILE}")


# --------------------------------------------------------------------------
# web subcommand
# --------------------------------------------------------------------------

CROSS_SKILL_REF = re.compile(
    r"(\.\./)?((?:parallax|translate)-[a-z0-9-]+)/(references/[A-Za-z0-9_./-]+)")
SKILL_DIR_GATE = '"<skill-dir>/../_parallax/'
_PLACEHOLDER = "\x00SKILLDIR\x00"

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
    return text.replace(_PLACEHOLDER, '"<skill-dir>/_vendored/_parallax/')


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
            shared_done = set()
            while shared_todo:
                rel = shared_todo.pop()
                if rel in shared_done:
                    continue
                if rel in WEB_VENDOR_EXCLUDE and rel not in seeds:
                    continue
                shared_done.add(rel)
                src = SKILLS_DIR / "_parallax" / rel
                targets = ([p[len("skills/_parallax/"):] for p in
                            tracked_files(f"_parallax/{rel}/")]
                           if src.is_dir() else [rel])
                for t in targets:
                    dest = skill_root / "_vendored" / "_parallax" / t
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    key = f"_parallax/{t}"
                    if key in TRANSFORMS or key in WEB_TRANSFORMS:
                        body = (SKILLS_DIR / "_parallax" / t).read_text(
                            encoding="utf-8")
                        if key in TRANSFORMS:
                            body = TRANSFORMS[key](body)
                        if key in WEB_TRANSFORMS:
                            body = WEB_TRANSFORMS[key](body)
                        dest.write_text(body, encoding="utf-8")
                    else:
                        shutil.copy2(SKILLS_DIR / "_parallax" / t, dest)
                    if t.endswith(".md"):
                        s, c = collect_deps(dest.read_text(encoding="utf-8"),
                                            strict=False)
                        shared_todo |= s - shared_done
                        cross_deps |= c
                # gap_suggest imports gap_detect at runtime.
                if rel.endswith("gap_suggest.py"):
                    shared_todo.add("house-view/gap_detect.py")
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

            for md in sorted(skill_root.rglob("*.md")):
                md.write_text(rewrite_refs(md.read_text(encoding="utf-8"), name),
                              encoding="utf-8")
            replace_description(skill_root / "SKILL.md", desc)

            web_resolution_check(skill_root)
            canary_scan(staging)

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
    args = parser.parse_args(argv)
    try:
        if args.cmd == "plugin":
            build_plugin()
        else:
            build_web(args.names or WEB_SKILLS)
    except BuildError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
