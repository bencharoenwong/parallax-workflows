import importlib.util
import json
from pathlib import Path
import pytest

SHARED = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sm_roles", SHARED / "skill_manifest.py")
sm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm)

PLUGIN = set(sm.plugin_skills())
WEB = set(sm.web_skills()) | set(sm.standalone_skills("release"))


def test_role_ids_are_fixed():
    assert [r["id"] for r in sm.roles()] == list(sm.ROLE_IDS) == [
        "fund-manager", "rm", "rm-support", "research-analyst",
        "wealth-advisor", "individual-investor", "integrator"]


@pytest.mark.parametrize("available", [PLUGIN, WEB], ids=["plugin", "zip"])
def test_every_role_has_a_start_or_is_integrator(available):
    for rid in sm.ROLE_IDS:
        starts = sm.starts_for(rid, available)
        assert starts or rid == "integrator", rid
        assert all(kind in sm.INPUT_KINDS for _, kind in starts)
        assert len(starts) <= 3


def test_rank_one_ships_in_the_plugin():
    for rid in sm.ROLE_IDS:
        if rid == "integrator":
            continue
        assert sm.starts_for(rid, PLUGIN)[0] == sm.starts_for(rid, set(sm.skills()))[0], rid


def test_starts_for_promotes_next_shipped_with_its_input():
    full = sm.starts_for("rm", set(sm.skills()))
    assert [s for s, _ in full][:3] == ["parallax-client-review", "parallax-desk-call-list", "parallax-morning-brief"]
    web = sm.starts_for("rm", WEB)
    assert [s for s, _ in web] == ["parallax-client-review", "parallax-morning-brief"]
    assert dict(web)["parallax-morning-brief"] == "holdings"


@pytest.mark.parametrize("bad", [
    {"roles_extra": "ghost"}, {"rank": 0}, {"rank_dup": True}, {"kind": "csv"}])
def test_validation_rejects_bad_starts(bad):
    # A fresh parse each time: the cached manifest is never mutated.
    data = json.loads(sm.MANIFEST_PATH.read_text(encoding="utf-8"))
    row = data["skills"]["parallax-should-i-buy"]
    if "roles_extra" in bad:
        row["starts"]["ghost"] = {"rank": 1, "input": "ticker"}
    if "rank" in bad:
        row["starts"]["individual-investor"]["rank"] = bad["rank"]
    if "rank_dup" in bad:
        data["skills"]["parallax-portfolio-checkup"]["starts"]["individual-investor"]["rank"] = 1
    if "kind" in bad:
        row["starts"]["individual-investor"]["input"] = bad["kind"]
    with pytest.raises(ValueError):
        sm._validate(data)
