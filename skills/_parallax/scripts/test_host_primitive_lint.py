"""Gates for host-primitive-lint.py (parallax-conventions.md §14 mechanics)."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "host-primitive-lint.py"
SKILLS_DIR = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location("host_primitive_lint", SCRIPT)
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)

# The host-locked set still on the allowlist (34 on 2026-09-05; shrinks with each sweep PR). This literal and the script's
# LEGACY_ALLOWLIST are compared with EQUALITY: shrinking one without the other,
# or re-adding a swept skill, fails here and is a deliberate two-file edit.
LEGACY_PINNED = frozenset({
    "parallax-ai-buffett", "parallax-ai-consensus", "parallax-ai-greenblatt",
    "parallax-ai-klarman", "parallax-ai-ptj", "parallax-ai-soros",
    "parallax-cio-letter-prep", "parallax-client-review",
    "parallax-country-deep-dive", "parallax-credit-lens", "parallax-desk-call-list", "parallax-explain-portfolio",
    "parallax-halal-screen", "parallax-house-view-attribution",
    "parallax-load-house-view", "parallax-macro-outlook",
    "parallax-make-house-view", "parallax-morning-brief", "parallax-pair-finder",
    "parallax-portfolio-builder",
    "parallax-portfolio-checkup", "parallax-rebalance",
    "parallax-scenario-analysis", "parallax-stress-house-view",
    "parallax-stress-test-thesis", "parallax-thematic-screen",
    "parallax-watchlist-monitor", "parallax-white-label-onboard",
})


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel / "SKILL.md"
        p.parent.mkdir(parents=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def _run(root: Path) -> tuple[int, str]:
    buf = io.StringIO()
    rc = lint.main(root, out=buf)
    return rc, buf.getvalue()


def test_seeded_violation_fails(tmp_path):
    root = _tree(tmp_path, {"parallax-new": "# New\n\nCall `ToolSearch` with `+Parallax`.\n"})
    rc, out = _run(root)
    assert rc == 1
    assert "HOST-LOCKED: parallax-new/SKILL.md:3: ToolSearch" in out


def test_each_identifier_is_caught(tmp_path):
    samples = {
        "ToolSearch": "Call ToolSearch first.",
        "AskUserQuestion": "Use AskUserQuestion at the gate.",
        "WebFetch": "else WebFetch the page",
        "mcp__ namespace literal": "call mcp__claude_ai_Parallax__get_company_info",
        "Write tool": "persist with the `Write` tool",
        "Skill tool": "invoke via the Skill tool",
    }
    for label, line in samples.items():
        hits, _ = lint.scan_text(f"# X\n{line}\n")
        assert (2, label) in hits, label


def test_bare_prose_write_and_skill_are_not_flagged():
    hits, _ = lint.scan_text("# X\nWrite the report. This skill routes to /parallax-deep-dive.\n")
    assert hits == []


def test_host_note_block_is_exempt(tmp_path):
    text = ("# New\n\n<!-- host-note -->\nClaude Code: call `ToolSearch` with `+Parallax`.\n"
            "<!-- /host-note -->\n\nRun the discover-tools primitive per conventions §14.\n")
    root = _tree(tmp_path, {"parallax-new": text})
    rc, out = _run(root)
    assert rc == 0, out


def test_unclosed_host_note_fails(tmp_path):
    root = _tree(tmp_path, {"parallax-new": "# New\n\n<!-- host-note -->\nnothing after\n"})
    rc, out = _run(root)
    assert rc == 1
    assert "UNCLOSED HOST-NOTE" in out


def test_unclosed_block_before_a_paired_block_still_fails(tmp_path):
    """An UNCLOSED host-note must not be rescued by a later paired block.

    Regression: a plain non-greedy span matched from the first opening tag to the
    NEAREST closing tag, so an unclosed block merged with the next properly-paired
    one. That hid every identifier in between AND made `unclosed` read False —
    defeating the exact check meant to catch it. Found by review 2026-09-08 while
    59 host-note blocks already existed on downstream branches.
    """
    text = (
        "# X\n"
        "<!-- host-note -->\n"
        "never closed\n"
        "Call `ToolSearch` here\n"
        "<!-- host-note -->\n"
        "second block, properly paired\n"
        "<!-- /host-note -->\n"
        "Use `WebFetch` here\n"
    )
    hits, unclosed = lint.scan_text(text)
    assert unclosed is True, "unclosed opening tag must be reported"
    assert (4, "ToolSearch") in hits, "identifier inside the unclosed block must not be swallowed"
    assert (8, "WebFetch") in hits

    root = _tree(tmp_path, {"parallax-new": text})
    rc, out = _run(root)
    assert rc == 1
    assert "UNCLOSED HOST-NOTE" in out


def test_two_paired_blocks_are_both_stripped():
    """The fix must not over-strip: two well-formed blocks stay exempt."""
    text = (
        "# X\n"
        "<!-- host-note -->\nClaude Code: `ToolSearch`\n<!-- /host-note -->\n"
        "clean prose\n"
        "<!-- host-note -->\nClaude Code: `WebFetch`\n<!-- /host-note -->\n"
    )
    hits, unclosed = lint.scan_text(text)
    assert hits == [] and unclosed is False


def test_ordinary_html_comment_is_stripped():
    hits, unclosed = lint.scan_text("# X\n<!-- migration note: ToolSearch removed 2026-09 -->\nclean\n")
    assert hits == [] and not unclosed


def test_line_numbers_survive_stripping():
    text = "# X\n<!-- host-note -->\na\nb\n<!-- /host-note -->\nAskUserQuestion here\n"
    hits, _ = lint.scan_text(text)
    assert hits == [(6, "AskUserQuestion")]


def test_stale_allowlist_entry_fails(tmp_path):
    name = sorted(LEGACY_PINNED)[0]
    root = _tree(tmp_path, {name: "# Clean\n\nNo host identifiers at all.\n"})
    rc, out = _run(root)
    assert rc == 1
    assert f"STALE ALLOWLIST: {name}" in out


def test_allowlisted_file_with_hits_passes(tmp_path):
    name = sorted(LEGACY_PINNED)[0]
    root = _tree(tmp_path, {name: "# Legacy\n\nCall ToolSearch.\n"})
    rc, _ = _run(root)
    assert rc == 0


def test_allowlist_equals_pinned_literal():
    assert lint.LEGACY_ALLOWLIST == LEGACY_PINNED


def test_every_allowlisted_name_is_a_real_skill_dir():
    for name in lint.LEGACY_ALLOWLIST:
        assert (SKILLS_DIR / name / "SKILL.md").is_file(), name


def test_real_tree_is_clean():
    rc, out = _run(SKILLS_DIR)
    assert rc == 0, out
