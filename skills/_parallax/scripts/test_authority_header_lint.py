"""Gates for authority-header-lint.py (skill-structure-conventions.md → Authority header)."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "authority-header-lint.py"
SKILLS_DIR = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location("authority_header_lint", SCRIPT)
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)

GOOD = ("# Title\n\n<!-- authority: contract -->\n<!-- verified: 2026-09-05 -->\n"
        "<!-- overrides: none -->\n\nBody.\n")

# The scoped shared-file set on 2026-09-05. A new shared .md is a one-line
# addition here in the PR that creates it.
SCOPED_21 = frozenset({
    "_parallax/README.md",
    "_parallax/parallax-conventions.md",
    "_parallax/skill-structure-conventions.md",
    "_parallax/jit-load-compliance-audit.md",
    "_parallax/coverage-matrix.md",
    "_parallax/response-schemas.md",
    "_parallax/token-costs.md",
    "_parallax/house-view/loader.md",
    "_parallax/house-view/render_helpers.md",
    "_parallax/house-view/auto-on-load-judge-pattern.md",
    "_parallax/house-view/README.md",
    "_parallax/house-view/MCP_FIELD_INVENTORY.md",
    "_parallax/house-view/stress-test-design.md",
    "_parallax/client-policy/policy-loader.md",
    "_parallax/white-label/integration-pattern.md",
    "_parallax/AI-profiles/output-template.md",
    "_parallax/AI-profiles/profile-schema.md",
    "_parallax/AI-profiles/consensus-config.md",
    "_parallax/AI-profiles/methodology-faq.md",
    "_parallax/AI-profiles/README.md",
    "_parallax/scripts/mcp_mocks/README.md",
})


def test_good_header_passes():
    assert lint.check_text(GOOD) == []


def test_missing_header_fails():
    assert lint.check_text("# Title\n\nBody with no header.\n")


def test_unknown_kind_fails():
    assert any("not one of" in p for p in lint.check_text(GOOD.replace("contract", "guidance")))


def test_non_date_fails():
    assert any("verified" in p for p in lint.check_text(GOOD.replace("2026-09-05", "n/a")))
    assert any("calendar" in p for p in lint.check_text(GOOD.replace("2026-09-05", "2026-13-40")))


def test_header_too_far_down_fails():
    late = "# Title\n\n" + "prose\n" * 7 + GOOD.split("\n", 2)[2]
    assert lint.check_text(late)


def test_out_of_order_fails():
    swapped = ("# Title\n\n<!-- verified: 2026-09-05 -->\n<!-- authority: contract -->\n"
               "<!-- overrides: none -->\n")
    assert any("order" in p for p in lint.check_text(swapped))


def test_scope_excludes_tests_profiles_and_dotdirs(tmp_path):
    for rel in ("_parallax/a.md", "_parallax/tests/b.md", "_parallax/AI-profiles/profiles/c.md",
                "_parallax/.cache/d.md", "_parallax/sub/e.md"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(GOOD)
    got = {str(p.relative_to(tmp_path)) for p in lint.scoped_files(tmp_path)}
    assert got == {"_parallax/a.md", "_parallax/sub/e.md"}


def test_real_scope_equals_pinned_set():
    got = {str(p.relative_to(SKILLS_DIR)) for p in lint.scoped_files(SKILLS_DIR)}
    assert got == SCOPED_21


def test_real_tree_is_clean():
    buf = io.StringIO()
    assert lint.main(SKILLS_DIR, out=buf) == 0, buf.getvalue()
