from pathlib import Path

CONV = (Path(__file__).resolve().parents[1] / "parallax-conventions.md").read_text(encoding="utf-8")


def test_conventions_carry_the_duplicate_connector_rule():
    sec = CONV[CONV.index("## 0.1"):CONV.index("## 0.2")]
    assert "more than one Parallax namespace" in sec
    assert "never call one logical tool on two namespaces" in sec


def test_schedule_task_primitive_has_a_cell_for_every_host():
    table = CONV[CONV.index("### §14.2"):CONV.index("### §14.3")]
    header = next(ln for ln in table.splitlines() if ln.startswith("| Primitive"))
    hosts = [c.strip() for c in header.strip("|").split("|")][1:]
    row = next(ln for ln in table.splitlines() if ln.startswith("| `schedule-task`"))
    cells = [c.strip() for c in row.strip("|").split("|")][1:]
    assert len(cells) == len(hosts) and all(cells)
    assert "Cowork (plugin)" in hosts and "claude.ai chat (plugin)" in hosts
    assert "`schedule-task`" in CONV[CONV.index("### §14.3"):]
