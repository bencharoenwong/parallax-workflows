"""README.md contract tests.

Both tests check executable/generated output, per the repo test-quality rule:
a test whose only evidence is that prose contains a string is a defect. One
checks the generated "who this is for" block for staleness; the other checks
that the published Quick Start table (the artifact users actually run)
advertises no command outside the built plugin."""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bundle as bb

README = (Path(__file__).resolve().parents[3] / "README.md").read_text(encoding="utf-8")


def test_who_for_block_is_generated():
    block = README[README.index("<!-- who-for:begin -->") + len("<!-- who-for:begin -->\n"):README.index("<!-- who-for:end -->")]
    assert block == bb.render_who_for()


# A slash-command token: "/" not preceded by a word, path or URL character,
# an optional "parallax:" plugin prefix, then a parallax- or translate- skill
# name. Captures the skill name.
_COMMAND = re.compile(r"(?<![\w/.:-])/(?:parallax:)?((?:parallax|translate)-[a-z0-9-]+)")


def test_quick_start_names_only_shipped_commands():
    qs = README[README.index("## Quick Start"):README.index("## What's in this repo")]
    commands = set(_COMMAND.findall(qs))
    assert commands, "Quick Start names no /parallax- or /translate- command"
    unshipped = commands - set(bb.PLUGIN_SKILLS)
    assert not unshipped, f"Quick Start names commands the plugin does not ship: {sorted(unshipped)}"
