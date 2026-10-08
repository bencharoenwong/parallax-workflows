"""README.md contract tests.

Both tests check executable/generated output, per the repo test-quality rule:
a test whose only evidence is that prose contains a string is a defect. One
checks the generated "who this is for" block for staleness; the other checks
that the published Quick Start table (the artifact users actually run)
advertises no command outside the built plugin."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bundle as bb

README = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")


def test_who_for_block_is_generated():
    block = README[README.index("<!-- who-for:begin -->") + len("<!-- who-for:begin -->\n"):README.index("<!-- who-for:end -->")]
    assert block == bb.render_who_for()


def test_quick_start_names_only_shipped_commands():
    qs = README[README.index("## Quick Start"):README.index("## What's in this repo")]
    assert not (bb.named_skills(qs) - set(bb.PLUGIN_SKILLS))
