import json
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import audit_chain  # noqa: E402
import view_commit  # noqa: E402

WRITABLE_ALL = ("view.yaml", "prose.md", "provenance.yaml")
AUDIT = "audit.jsonl"


def _seed(tmp_path, version_id="v1"):
    (tmp_path / "view.yaml").write_text(
        f"metadata:\n  version_id: {version_id}\n  view_id: vw\n", encoding="utf-8"
    )
    audit_chain.append_entry(tmp_path / AUDIT, {"action": "extraction_attempt", "applied": False})


def _row(version_id="v2", **kw):
    return {"action": "save", "version_id": version_id, "applied": True, **kw}


def test_audit_jsonl_is_rejected_with_its_own_message():
    with pytest.raises(view_commit.CommitRejected, match="append-only"):
        view_commit.validate_write_remove_keys({"audit.jsonl": "x"}, frozenset())


@pytest.mark.parametrize("key", ["../view.yaml", "a/view.yaml", "view.yaml.tmp.abc", "notes.txt"])
def test_unwritable_keys_are_rejected(key):
    with pytest.raises(view_commit.CommitRejected):
        view_commit.validate_write_remove_keys({key: "x"}, frozenset())


def test_non_string_content_is_rejected():
    with pytest.raises(view_commit.CommitRejected, match="str"):
        view_commit.validate_write_remove_keys({"view.yaml": 123}, frozenset())


def test_version_id_required_when_writing():
    with pytest.raises(view_commit.CommitRejected, match="version_id"):
        view_commit.validate_audit_entry({"action": "save"}, {"view.yaml": "x"})


def test_version_id_not_required_when_only_removing():
    view_commit.validate_audit_entry(
        {"action": "clear", "destination": "/a", "reason": "b"}, {}
    )


def test_clear_requires_destination_and_reason():
    with pytest.raises(view_commit.CommitRejected, match="destination"):
        view_commit.validate_audit_entry({"action": "clear", "reason": "b"}, {})


def test_prose_body_hash_ignores_frontmatter_and_normalizes_crlf():
    lf = "---\npaired_yaml_hash: a\n---\nBody text\n"
    crlf = "---\r\npaired_yaml_hash: a\r\n---\r\nBody text\r\n"
    assert view_commit.compute_prose_body_hash(lf) == view_commit.compute_prose_body_hash(crlf)


def test_prose_body_hash_is_recomputed_not_read_from_frontmatter(tmp_path):
    """SECURITY: trusting the stored field reopens the legacy-view downgrade attack."""
    (tmp_path / "prose.md").write_text(
        "---\nprose_body_hash: " + "0" * 64 + "\n---\nreal body\n", encoding="utf-8"
    )
    resolved = view_commit.IDENTITY_RESOLVERS["prose_body_hash"](tmp_path)
    assert resolved != "0" * 64
    assert resolved == view_commit.compute_prose_body_hash("---\nx\n---\nreal body\n")


def test_parent_version_id_resolves_against_on_disk_version_id(tmp_path):
    (tmp_path / "view.yaml").write_text("metadata:\n  version_id: v2\n", encoding="utf-8")
    assert view_commit.IDENTITY_RESOLVERS["parent_version_id"](tmp_path) == "v2"


def test_resolvers_only_read_what_is_asked_for(tmp_path):
    """--clear needs version_id only; a corrupt prose.md must not break it."""
    (tmp_path / "view.yaml").write_text("metadata:\n  version_id: v2\n", encoding="utf-8")
    (tmp_path / "prose.md").write_bytes(b"\xff\xfe not utf-8")
    assert view_commit.IDENTITY_RESOLVERS["version_id"](tmp_path) == "v2"


def test_view_hash_agrees_with_the_oracle_on_zero_valued_tilts():
    """Zero-valued tilts are the schema's default state for every pillar,
    sector and region, so a strip-rule divergence misfires on real views."""
    import test_view_hash as oracle

    samples = [
        {},
        {"tilts": {}, "excludes": []},
        {"tilts": {"pillars": {"econometrics_phase": 0, "valuation_state": 1},
                   "sectors": {"energy": 0, "financials": 2}}, "excludes": []},
        {"tilts": {"sectors": {"a": 0}}, "excludes": []},
        {"tilts": {"factors": {"momentum": -1}}, "excludes": ["XYZ"]},
    ]
    for sample in samples:
        _canonical, expected = oracle.compute_view_hash(sample)
        assert view_commit.compute_view_hash(sample) == expected, sample


def test_locked_variant_requires_a_token(tmp_path):
    _seed(tmp_path)
    with pytest.raises(TypeError):
        view_commit.commit_view_locked(tmp_path, write={}, remove=frozenset(),
                                       audit_entry=_row(), expected_identity={})


def test_token_for_another_dir_is_rejected(tmp_path):
    _seed(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    with audit_chain.view_transaction(other) as token:
        with pytest.raises(view_commit.CommitRejected, match="TransactionToken"):
            view_commit.commit_view_locked(tmp_path, token=token, write={},
                                           remove=frozenset(), audit_entry=_row(),
                                           expected_identity={})


def test_prior_audit_rows_survive_a_clear(tmp_path):
    """Direct regression for the defect: --clear must not truncate the chain."""
    _seed(tmp_path)
    (tmp_path / "prose.md").write_text("---\nx: 1\n---\nbody\n", encoding="utf-8")
    (tmp_path / "provenance.yaml").write_text("a: 1\n", encoding="utf-8")
    before = len(audit_chain.verify_chain(tmp_path / AUDIT))
    view_commit.commit_view(
        tmp_path, write={}, remove=frozenset(WRITABLE_ALL),
        audit_entry={"action": "clear", "version_id": "v1",
                     "destination": "/archive/x", "reason": "operator cleared"},
        expected_identity={"version_id": "v1"},
    )
    rows = audit_chain.verify_chain(tmp_path / AUDIT)
    assert len(rows) == before + 1
    assert sum(1 for r in rows if r.get("chain_root")) == 1
    for name in WRITABLE_ALL:
        assert not (tmp_path / name).exists()


def test_moved_identity_writes_nothing(tmp_path):
    _seed(tmp_path, version_id="v9")
    before = (tmp_path / AUDIT).read_bytes()
    with pytest.raises(audit_chain.ViewChangedMidRun):
        view_commit.commit_view(tmp_path, write={"view.yaml": "metadata:\n  version_id: v2\n"},
                                remove=frozenset(), audit_entry=_row(),
                                expected_identity={"parent_version_id": "v1"})
    assert (tmp_path / AUDIT).read_bytes() == before


def test_row_that_disagrees_with_bytes_is_rejected(tmp_path):
    _seed(tmp_path)
    content = "metadata:\n  version_id: v2\ntilts:\n  sectors:\n    health_care: 1\n"
    with pytest.raises(view_commit.CommitRejected, match="view_hash"):
        view_commit.commit_view(tmp_path, write={"view.yaml": content},
                                remove=frozenset(),
                                audit_entry=_row(view_hash="0" * 64),
                                expected_identity={"parent_version_id": "v1"})
    assert not list(tmp_path.glob("*.tmp.*"))


def test_witness_loss_is_loud(tmp_path, monkeypatch):
    _seed(tmp_path)
    content = "metadata:\n  version_id: v2\n"
    monkeypatch.setattr(audit_chain, "append_entry",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(view_commit.CommitWitnessLost, match="v2"):
        view_commit.commit_view(tmp_path, write={"view.yaml": content},
                                remove=frozenset(),
                                audit_entry=_row(view_hash=view_commit.compute_view_hash({})),
                                expected_identity={"parent_version_id": "v1"})


def test_append_entry_is_reached_through_the_module_attribute(tmp_path, monkeypatch):
    """Pins the import style test_e2e_concurrency.py depends on."""
    _seed(tmp_path)
    seen = {}
    real = audit_chain.append_entry
    monkeypatch.setattr(audit_chain, "append_entry",
                        lambda p, e, **k: seen.setdefault("hit", True) or real(p, e, **k))
    view_commit.commit_view(tmp_path, write={}, remove=frozenset(),
                            audit_entry={"action": "extend", "version_id": "v1"},
                            expected_identity={"version_id": "v1"})
    assert seen.get("hit") is True


def test_two_threads_both_commit_and_the_chain_stays_valid(tmp_path):
    _seed(tmp_path)
    errors = []

    def worker(n):
        try:
            view_commit.commit_view(tmp_path, write={}, remove=frozenset(),
                                    audit_entry={"action": "extend", "version_id": "v1",
                                                 "note": f"w{n}"},
                                    expected_identity={"version_id": "v1"})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "commit_view deadlocked"
    assert not errors
    assert len(audit_chain.verify_chain(tmp_path / AUDIT)) == 3


def test_staged_files_are_cleaned_up_when_a_later_write_fails(tmp_path, monkeypatch):
    _seed(tmp_path)
    real_open = view_commit.os.open
    calls = {"n": 0}

    def flaky(path, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("no space left on device")
        return real_open(path, *a, **k)

    monkeypatch.setattr(view_commit.os, "open", flaky)
    with pytest.raises(view_commit.CommitRejected):
        view_commit.commit_view(
            tmp_path,
            write={"view.yaml": "metadata:\n  version_id: v2\n", "provenance.yaml": "a: 1\n"},
            remove=frozenset(), audit_entry=_row(view_hash=view_commit.compute_view_hash({})),
            expected_identity={"parent_version_id": "v1"})
    assert not list(tmp_path.glob("*.tmp.*"))


def test_staged_files_are_created_0600_not_chmodded_after(tmp_path):
    _seed(tmp_path)
    content = "metadata:\n  version_id: v2\n"
    view_commit.commit_view(tmp_path, write={"view.yaml": content}, remove=frozenset(),
                            audit_entry=_row(view_hash=view_commit.compute_view_hash({})),
                            expected_identity={"parent_version_id": "v1"})
    assert (tmp_path / "view.yaml").stat().st_mode & 0o777 == 0o600
