import collections
import json
import subprocess
import sys
import sys as _sys
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


def test_view_hash_is_recomputed_not_read_from_metadata(tmp_path):
    """SECURITY: --re-pair blesses whatever is on disk and keys on view_hash.
    Trusting metadata.view_hash lets an edit to the tilts pass the guard while
    the stale stored field goes unchanged."""
    (tmp_path / "view.yaml").write_text(
        "metadata:\n  version_id: v1\n  view_hash: " + "0" * 64 + "\n"
        "tilts:\n  sectors:\n    health_care: 2\n",
        encoding="utf-8",
    )
    resolved = view_commit.IDENTITY_RESOLVERS["view_hash"](tmp_path)
    assert resolved != "0" * 64
    assert resolved == view_commit.compute_view_hash(
        {"tilts": {"sectors": {"health_care": 2}}}
    )


def test_view_hash_resolver_returns_none_when_there_is_no_view(tmp_path):
    assert view_commit.IDENTITY_RESOLVERS["view_hash"](tmp_path) is None


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


def test_impostor_tokens_are_rejected(tmp_path):
    """The token is proof the lock is held; a look-alike proves nothing.
    A duck-typed stand-in carrying the right view_dir must not satisfy it."""
    _seed(tmp_path)
    lookalike = collections.namedtuple("TransactionToken", "view_dir")(tmp_path)
    for impostor in (object(), lookalike):
        with pytest.raises(view_commit.CommitRejected, match="TransactionToken"):
            view_commit.commit_view_locked(
                tmp_path, token=impostor, write={}, remove=frozenset(),
                audit_entry=_row(), expected_identity={})


def test_fresh_install_save_accepts_a_null_parent_version_id(tmp_path):
    """Nothing on disk to read, so the plan passes JSON null."""
    content = "metadata:\n  version_id: v1\n"
    view_commit.commit_view(
        tmp_path, write={"view.yaml": content}, remove=frozenset(),
        audit_entry=_row(version_id="v1", view_hash=view_commit.compute_view_hash({})),
        expected_identity={"parent_version_id": None})
    assert (tmp_path / "view.yaml").read_text() == content


def test_staging_order_covers_exactly_the_writable_set():
    """Two sources of truth here would accept a name, never write it, and
    still witness it with a successful row."""
    assert frozenset(view_commit._STAGING_ORDER) == view_commit.WRITABLE


def test_a_single_key_that_is_neither_inline_nor_path_is_rejected(tmp_path):
    with pytest.raises(view_commit.CommitRejected, match="neither 'inline' nor 'path'"):
        view_commit._resolve_content(tmp_path, "view.yaml", {"contents": "x"})


def test_undeletable_artifact_reports_what_was_already_removed(tmp_path, monkeypatch):
    """A PermissionError mid-remove must not escape raw: the removals that
    already landed cannot be undone, so this is a partial apply."""
    _seed(tmp_path)
    (tmp_path / "prose.md").write_text("---\nx: 1\n---\nbody\n", encoding="utf-8")
    (tmp_path / "provenance.yaml").write_text("a: 1\n", encoding="utf-8")
    real_unlink = Path.unlink

    def flaky_unlink(self, *a, **k):
        if self.name == "view.yaml":
            raise PermissionError("read-only file system")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    with pytest.raises(view_commit.CommitPartiallyApplied) as excinfo:
        view_commit.commit_view(
            tmp_path, write={}, remove=frozenset(WRITABLE_ALL),
            audit_entry={"action": "clear", "version_id": "v1",
                         "destination": "/archive/x", "reason": "operator cleared"},
            expected_identity={"version_id": "v1"})
    # Sorted order: prose.md and provenance.yaml go before view.yaml.
    assert "prose.md" in str(excinfo.value)
    assert "provenance.yaml" in str(excinfo.value)


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
        view_commit.commit_view(
            tmp_path, write={"view.yaml": "metadata:\n  version_id: v2\n"},
            remove=frozenset(),
            audit_entry=_row(view_hash=view_commit.compute_view_hash({})),
            expected_identity={"parent_version_id": "v1"})
    assert (tmp_path / AUDIT).read_bytes() == before


def test_view_hash_is_required_when_view_yaml_is_written(tmp_path):
    """A row witnessing a written view must identify it."""
    _seed(tmp_path)
    with pytest.raises(view_commit.CommitRejected, match="view_hash is required"):
        view_commit.commit_view(
            tmp_path,
            write={"view.yaml": "metadata:\n  version_id: v2\n"},
            remove=frozenset(),
            audit_entry={"action": "save", "version_id": "v2"},   # no view_hash
            expected_identity={"parent_version_id": "v1"})
    assert not list(tmp_path.glob("*.tmp.*"))


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
    barrier = threading.Barrier(2)

    def worker(n):
        try:
            barrier.wait(timeout=5)
            if n == 0:
                view_commit.commit_view(
                    tmp_path,
                    write={"view.yaml": "metadata:\n  version_id: v1\n"},
                    remove=frozenset(),
                    audit_entry={"action": "extend", "version_id": "v1",
                                 "view_hash": view_commit.compute_view_hash({})},
                    expected_identity={"version_id": "v1"})
            else:
                view_commit.commit_view(
                    tmp_path, write={}, remove=frozenset(),
                    audit_entry={"action": "extend", "version_id": "v1", "note": "w1"},
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
    # view.yaml is only ever written by worker 0; if the transaction lock
    # failed to serialize the two commits, a torn/interleaved write here is
    # the most likely symptom.
    text = (tmp_path / "view.yaml").read_text(encoding="utf-8")
    assert text == "metadata:\n  version_id: v1\n"
    assert view_commit._load_view(tmp_path) == {"metadata": {"version_id": "v1"}}


def test_staging_failure_cleans_up_and_commits_nothing(tmp_path, monkeypatch):
    """Failure mid-staging: no rename has happened, so every tmp is removed
    and the previous artifacts are untouched."""
    _seed(tmp_path)
    (tmp_path / "provenance.yaml").write_text("old: 1\n", encoding="utf-8")
    original = (tmp_path / "view.yaml").read_bytes()
    calls = {"n": 0}
    real_fsync = view_commit.os.fsync

    def flaky_fsync(fd):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("no space left on device")
        return real_fsync(fd)

    monkeypatch.setattr(view_commit.os, "fsync", flaky_fsync)
    with pytest.raises(view_commit.CommitRejected):
        view_commit.commit_view(
            tmp_path,
            write={"view.yaml": "metadata:\n  version_id: v2\n",
                   "provenance.yaml": "a: 1\n"},
            remove=frozenset(),
            audit_entry=_row(view_hash=view_commit.compute_view_hash({})),
            expected_identity={"parent_version_id": "v1"})
    assert not list(tmp_path.glob("*.tmp.*")), "staged files leaked"
    assert (tmp_path / "view.yaml").read_bytes() == original, "committed despite failure"
    assert (tmp_path / "provenance.yaml").read_text() == "old: 1\n"


def test_rename_failure_keeps_completed_renames_and_cleans_the_rest(tmp_path, monkeypatch):
    """A completed rename cannot be undone; the rest must still be cleaned."""
    _seed(tmp_path)
    (tmp_path / "provenance.yaml").write_text("old: 1\n", encoding="utf-8")
    calls = {"n": 0}
    real_rename = view_commit.os.rename

    def flaky_rename(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("rename failed")
        return real_rename(src, dst)

    monkeypatch.setattr(view_commit.os, "rename", flaky_rename)
    with pytest.raises(view_commit.CommitPartiallyApplied):
        view_commit.commit_view(
            tmp_path,
            write={"view.yaml": "metadata:\n  version_id: v2\n",
                   "provenance.yaml": "a: 1\n"},
            remove=frozenset(),
            audit_entry=_row(view_hash=view_commit.compute_view_hash({})),
            expected_identity={"parent_version_id": "v1"})
    # First rename completed and must have kept its NEW bytes.
    assert "v2" in (tmp_path / "view.yaml").read_text()
    # The unrenamed one was cleaned up and its target left alone.
    assert not list(tmp_path.glob("*.tmp.*")), "unrenamed staging files leaked"
    assert (tmp_path / "provenance.yaml").read_text() == "old: 1\n"


def test_unsafe_version_id_is_rejected_and_writes_nothing(tmp_path):
    _seed(tmp_path)
    with pytest.raises(view_commit.CommitRejected):
        view_commit.commit_view(
            tmp_path, write={"view.yaml": "metadata:\n  version_id: v2\n"},
            remove=frozenset(),
            audit_entry=_row(version_id="../escape", view_hash=view_commit.compute_view_hash({})),
            expected_identity={"parent_version_id": "v1"})
    assert not list(tmp_path.glob("*.tmp.*"))
    assert "metadata:\n  version_id: v1\n  view_id: vw\n" == (tmp_path / "view.yaml").read_text()


def test_staged_files_are_created_0600_not_chmodded_after(tmp_path):
    _seed(tmp_path)
    content = "metadata:\n  version_id: v2\n"
    view_commit.commit_view(tmp_path, write={"view.yaml": content}, remove=frozenset(),
                            audit_entry=_row(view_hash=view_commit.compute_view_hash({})),
                            expected_identity={"parent_version_id": "v1"})
    assert (tmp_path / "view.yaml").stat().st_mode & 0o777 == 0o600


SHARED = str(view_commit._HOUSE_VIEW_DIR)


def _run(plan, mode, view_dir):
    return subprocess.run(
        [_sys.executable, "-m", "view_commit", "--mode", mode, "--dir", str(view_dir)],
        cwd=SHARED, input=json.dumps(plan), text=True, capture_output=True,
    )


def test_mode_spec_uses_the_hyphenated_action():
    """loader.md:250 pins `re-pair`; consumers MUST skip unrecognized actions,
    so `re_pair` would write rows --version-history silently drops."""
    assert view_commit.MODE_SPECS["re-pair"]["action"] == "re-pair"
    assert view_commit.MODE_SPECS["re-pair"]["identity_keys"] == ("view_hash", "prose_body_hash")
    assert view_commit.MODE_SPECS["clear"]["remove"] == tuple(sorted(view_commit.WRITABLE))


def test_cli_happy_path(tmp_path):
    _seed(tmp_path)
    plan = {"write": {}, "audit_entry": {"action": "extend", "version_id": "v1"},
            "expected_identity": {"version_id": "v1"}}
    result = _run(plan, "extend", tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["action"] == "extend"


def test_cli_rejected_key_exits_2_and_writes_nothing(tmp_path):
    _seed(tmp_path)
    before = (tmp_path / AUDIT).read_bytes()
    # expected_identity must be VALID here, or build_commit_args rejects on the
    # missing key first and we never reach the whitelist check under test.
    plan = {"write": {"audit.jsonl": {"inline": "x"}},
            "audit_entry": {"action": "save", "version_id": "v2"},
            "expected_identity": {"parent_version_id": "v1"}}
    result = _run(plan, "save", tmp_path)
    assert result.returncode == 2
    assert "append-only" in result.stderr
    assert (tmp_path / AUDIT).read_bytes() == before


def test_cli_reads_path_refs_from_outside_the_view_dir(tmp_path):
    _seed(tmp_path)
    staging = tmp_path.parent / "staging"
    staging.mkdir(exist_ok=True)
    src = staging / "view.yaml"
    src.write_text("metadata:\n  version_id: v2\n", encoding="utf-8")
    plan = {"write": {"view.yaml": {"path": str(src)}},
            "audit_entry": {"action": "save", "version_id": "v2",
                            "view_hash": view_commit.compute_view_hash({})},
            "expected_identity": {"parent_version_id": "v1"}}
    result = _run(plan, "save", tmp_path)
    assert result.returncode == 0, result.stderr
    assert not list(tmp_path.glob("*.tmp.*"))


def test_cli_refuses_a_path_ref_inside_the_view_dir(tmp_path):
    _seed(tmp_path)
    plan = {"write": {"view.yaml": {"path": str(tmp_path / "view.yaml")}},
            "audit_entry": {"action": "save", "version_id": "v2"},
            "expected_identity": {}}
    result = _run(plan, "save", tmp_path)
    assert result.returncode == 2
    assert "inside the view directory" in result.stderr


def test_cli_partial_apply_does_not_exit_2(tmp_path, monkeypatch):
    """Exit 2 is contracted to mean nothing was written, so a failure that
    landed one rename must not use it."""
    _seed(tmp_path)
    (tmp_path / "provenance.yaml").write_text("old: 1\n", encoding="utf-8")
    staging = tmp_path.parent / "staging_partial"
    staging.mkdir(exist_ok=True)
    (staging / "view.yaml").write_text("metadata:\n  version_id: v2\n", encoding="utf-8")
    (staging / "provenance.yaml").write_text("a: 1\n", encoding="utf-8")
    plan = {"write": {"view.yaml": {"path": str(staging / "view.yaml")},
                      "provenance.yaml": {"path": str(staging / "provenance.yaml")}},
            "audit_entry": {"action": "save", "version_id": "v2",
                            "view_hash": view_commit.compute_view_hash({})},
            "expected_identity": {"parent_version_id": "v1"}}
    # Drive the in-process path; the subprocess cannot be monkeypatched.
    calls = {"n": 0}
    real_rename = view_commit.os.rename

    def flaky_rename(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("rename failed")
        return real_rename(src, dst)

    monkeypatch.setattr(view_commit.os, "rename", flaky_rename)
    kwargs = view_commit.build_commit_args("save", plan, tmp_path)
    with pytest.raises(view_commit.CommitPartiallyApplied):
        view_commit.commit_view(tmp_path, **kwargs)
    # And confirm main() would not map this to 2.
    assert not issubclass(view_commit.CommitPartiallyApplied, view_commit.CommitRejected)
