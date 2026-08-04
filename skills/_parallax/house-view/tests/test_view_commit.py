import pytest
import sys
from pathlib import Path

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import view_commit  # noqa: E402


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
