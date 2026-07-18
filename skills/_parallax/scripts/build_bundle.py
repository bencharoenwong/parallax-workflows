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
anything. Extra local-only scan terms can be supplied one-per-line in
~/.claude/parallax-canary-extra.txt (never tracked in this repo).

Stdlib-only; runs under python >= 3.9.
"""
from __future__ import annotations

import argparse
import json
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
    "house-view/README.md",
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


def _drop_line(text: str, line: str, label: str) -> str:
    needle = line + "\n"
    if needle not in text:
        raise BuildError(f"transform anchor not found ({label}): line")
    return text.replace(needle, "", 1)


def _swap(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise BuildError(f"transform anchor not found ({label}): old text")
    return text.replace(old, new, 1)


def transform_hv_loader(text: str) -> str:
    return _cut(text, "### Framework components", "### Factor aliases",
                "loader.md components")


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


def transform_hv_readme(text: str) -> str:
    return _swap(text, "Mirrors the `AI-profiles/` pattern: a family", "A family",
                 "house-view README pattern sentence")


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
    "_parallax/house-view/README.md": transform_hv_readme,
    "_parallax/parallax-conventions.md": transform_conventions,
    "_parallax/AI-profiles/output-template.md": transform_output_template,
    "parallax-concierge/SKILL.md": transform_concierge,
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

def load_canary_terms() -> list[str]:
    terms = list(CANARY_TERMS)
    if EXTRA_CANARY_FILE.exists():
        for line in EXTRA_CANARY_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                terms.append(line)
    else:
        print(f"WARN: extra scan-term file not found ({EXTRA_CANARY_FILE}); "
              "running with built-in terms only", file=sys.stderr)
    return terms


def canary_scan(root: Path) -> None:
    terms = load_canary_terms()
    hits = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for term in terms:
            if term in text:
                hits.append((path.relative_to(root), term))
    if hits:
        for rel, term in hits:
            print(f"  SCAN HIT: {rel}: {term}", file=sys.stderr)
        raise BuildError(f"term scan failed with {len(hits)} hit(s)")


REF_PARALLAX = re.compile(r"_parallax/[A-Za-z0-9_./-]+")
REF_REFERENCES = re.compile(
    r"(\.\./)?[A-Za-z0-9_-]*/?references/[A-Za-z0-9_/-]+\.md")
# repo-root examples/ docs referenced from skills as ../../examples/<name>
REF_EXAMPLES = re.compile(r"\.\./\.\./(examples/[A-Za-z0-9_./-]+\.md)")


def _resolve_parallax_ref(skills_root: Path, ref: str) -> bool:
    ref = ref.rstrip(".")
    candidates = [ref, ref + ".py", ref + ".md"]
    return any((skills_root / c).exists() for c in candidates)


def resolution_check(skills_root: Path) -> None:
    """Every shared-tree or references/ path named in a bundled SKILL.md must
    resolve inside the bundle."""
    failures = []
    for skill_md in sorted(skills_root.glob("*/SKILL.md")):
        if skill_md.parent.name == "_parallax":
            continue
        text = skill_md.read_text(encoding="utf-8")
        for ref in set(REF_PARALLAX.findall(text)):
            if not _resolve_parallax_ref(skills_root, ref):
                failures.append(f"{skill_md.parent.name}: {ref}")
        for m in {x.group(0) for x in REF_REFERENCES.finditer(text)}:
            if "<" in m:
                continue
            if not ((skill_md.parent / m).exists() or (skills_root / m).exists()):
                failures.append(f"{skill_md.parent.name}: {m}")
        for m in set(REF_EXAMPLES.findall(text)):
            if not (skills_root.parent / m).exists():
                failures.append(f"{skill_md.parent.name}: ../../{m}")
    if failures:
        for f in failures:
            print(f"  UNRESOLVED: {f}", file=sys.stderr)
        raise BuildError(f"{len(failures)} unresolved reference(s) in bundle")


# --------------------------------------------------------------------------
# Frontmatter (web build)
# --------------------------------------------------------------------------

FRONTMATTER_DESC = re.compile(r'(^description:\s*)("?)(.*?)(\2)\s*$',
                              re.M | re.S)


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
        for skill_md in sorted(skills_root.glob("*/SKILL.md")):
            example_refs |= set(REF_EXAMPLES.findall(
                skill_md.read_text(encoding="utf-8")))
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
        elif strict and not (SKILLS_DIR / "_parallax" / rel).is_dir():
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
                    if key in TRANSFORMS:
                        dest.write_text(
                            TRANSFORMS[key]((SKILLS_DIR / "_parallax" / t)
                                            .read_text(encoding="utf-8")),
                            encoding="utf-8")
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
