"""Release integrity regressions using actual archive bytes."""
import json
import stat
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bundle as bb
import distribution_docs as docs
import release
from canary_fixture import hermetic_extra_terms  # noqa: F401


@pytest.mark.parametrize("value", ["2026.02.1", "2026.2.29", "2026.13.1", "2026.1.32", "../../x", "1.2.3"])
def test_invalid_release_dates(value):
    with pytest.raises(bb.BuildError):
        release.date_version(value)


def test_leap_date():
    assert release.date_version("2028.2.29").isoformat() == "2028-02-29"


@pytest.mark.parametrize("name", ["../outside.md", "/tmp/outside.md", "x/../../out.md", "x\\out.md", "C:/out.md"])
def test_zip_cannot_escape_extraction(tmp_path, name):
    archive = tmp_path / "bad.skill"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "bad")
    with pytest.raises(bb.BuildError):
        release.unpack(archive, tmp_path / "out")


def test_zip_symlink_is_rejected(tmp_path):
    archive = tmp_path / "bad.skill"
    with zipfile.ZipFile(archive, "w") as z:
        info = zipfile.ZipInfo("link")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "../outside")
    with pytest.raises(bb.BuildError):
        release.unpack(archive, tmp_path / "out")


def test_partial_scan_cannot_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "EXTRA_CANARY_FILE", tmp_path / "absent")
    monkeypatch.setenv(bb.PARTIAL_SCAN_ENV, "1")
    with pytest.raises(bb.BuildError, match="full scan-term"):
        release.require_full_scan()


def test_empty_scan_terms_cannot_publish(tmp_path, monkeypatch):
    terms = tmp_path / "terms"
    terms.write_text("# comments only\n")
    monkeypatch.setattr(bb, "EXTRA_CANARY_FILE", terms)
    with pytest.raises(bb.BuildError, match="empty"):
        release.require_full_scan()


def test_dirty_tree_refused_before_build(tmp_path, monkeypatch):
    monkeypatch.setattr(release, "source_state", lambda: {"dirty": True})
    with pytest.raises(bb.BuildError, match="clean committed"):
        release.build(tmp_path / "release")
    assert not (tmp_path / "release").exists()


def test_existing_output_preserved(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep").write_text("previous release")
    monkeypatch.setattr(release, "source_state", lambda: {"dirty": True})
    with pytest.raises(bb.BuildError, match="already exists"):
        release.build(out, preview=True)
    assert (out / "keep").read_text() == "previous release"


def refresh_checksums(out, index):
    for asset in index["assets"]:
        path = out / asset["name"]
        asset.update(size=path.stat().st_size, sha256=release.digest(path))
    (out / "index.json").write_text(json.dumps(index))
    (out / "SHA256SUMS").write_text("".join(
        f"{release.digest(p)}  {p.name}\n" for p in sorted(out.iterdir())
        if p.name != "SHA256SUMS"))


def make_release(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("---\nname: demo\ndescription: A demo\n---\nDemo\n")
    out = tmp_path / "release"
    out.mkdir()
    archive = out / "demo.skill"
    release.write_zip(archive, [("demo/SKILL.md", source)])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"name": "parallax", "version": "2026.10.8"}))
    connector = tmp_path / "connector.json"
    connector.write_text(json.dumps({"mcpServers": {"parallax": {
        "type": "http", "url": bb.PARALLAX_MCP_URL}}}))
    release.write_zip(out / "parallax-plugin.zip", [
        ("plugin/.claude-plugin/plugin.json", manifest),
        ("plugin/.mcp.json", connector), ("plugin/skills/demo/SKILL.md", source)])
    release.write_zip(out / "parallax-claude-ai-skills.zip", [(archive.name, archive)])
    index = {"schema_version": 1, "version": "2026.10.8", "tag": "v2026.10.8", "preview": True,
             "source": {"commit": "a" * 40, "dirty": True, "tree_sha256": "b" * 64},
             "built_at": "2026-10-08T00:00:00+00:00",
             "mcp": {"required": True, "url": bb.PARALLAX_MCP_URL, "authentication": "Sign in."},
             "skills": [{"name": "demo", "description": "A demo",
                         "surfaces": ["plugin", "skill-upload"], "asset": "demo.skill"}],
             "assets": [{"name": p.name, "url": None, "latest_url": None}
                        for p in sorted(out.iterdir())]}
    refresh_checksums(out, index)
    return out


def test_actual_release_checksums_and_extra_files(tmp_path):
    out = make_release(tmp_path)
    assert release.verify_release(out)["preview"]
    (out / "unexpected.txt").write_text("extra")
    with pytest.raises(bb.BuildError, match="inventory"):
        release.verify_release(out)


def test_changed_asset_fails_verification(tmp_path):
    out = make_release(tmp_path)
    with (out / "demo.skill").open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(bb.BuildError, match="checksum"):
        release.verify_release(out)


def test_changed_index_fails_verification(tmp_path):
    out = make_release(tmp_path)
    p = out / "index.json"
    p.write_text(p.read_text() + "\n")
    with pytest.raises(bb.BuildError, match="SHA256SUMS"):
        release.verify_release(out)


def test_nested_collection_is_scanned(tmp_path):
    source = tmp_path / "source.md"
    source.write_text(bb.CANARY_TERMS[0])
    inner = tmp_path / "demo.skill"
    release.write_zip(inner, [("demo/SKILL.md", source)])
    outer = tmp_path / "parallax-claude-ai-skills.zip"
    release.write_zip(outer, [(inner.name, inner)])
    with pytest.raises(bb.BuildError, match="term scan"):
        release.verify_asset(outer, "2026.10.8")


def test_wrong_skill_root_rejected(tmp_path):
    source = tmp_path / "s.md"
    source.write_text("demo")
    archive = tmp_path / "demo.skill"
    release.write_zip(archive, [("other/SKILL.md", source)])
    with pytest.raises(bb.BuildError, match="root directory"):
        release.verify_asset(archive, "2026.10.8")


def test_document_tables_match_manifest():
    text = (bb.REPO_ROOT / "README.md").read_text()
    assert docs.render(text) == text
    tables = docs.sections()
    assert "Held: native review pending" in tables["distributions"]
    for name in bb.skill_manifest.skills():
        assert f"[{name}]" in tables["distributions"]


def test_document_marker_corruption_fails():
    with pytest.raises(bb.BuildError, match="marker"):
        docs.render("no generated markers")


@pytest.fixture
def small_build(tmp_path, monkeypatch):
    """Exercise real release assembly/verification with tiny builder inputs."""
    root = tmp_path / "repo"
    skill = root / "skills/demo"
    skill.mkdir(parents=True)
    source = skill / "SKILL.md"
    source.write_text("---\nname: demo\ndescription: A demo\n---\nDemo\n")
    (root / "CHANGELOG.md").write_text(f"# Changes\n\n## {bb.PLUGIN_VERSION}\n")
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(bb, "SKILLS_DIR", root / "skills")
    monkeypatch.setattr(bb, "WEB_SKILLS", ["demo"])
    monkeypatch.setattr(bb, "PLUGIN_SKILLS", ["demo"])
    monkeypatch.setattr(bb.skill_manifest, "standalone_skills", lambda tier: [])
    monkeypatch.setattr(bb.skill_manifest, "skills", lambda: {"demo": {"web": True, "plugin": True}})
    monkeypatch.setattr(release.subprocess, "run", lambda *a, **k: None)

    def plugin():
        path = bb.PLUGIN_DIR / ".claude-plugin"
        path.mkdir(parents=True)
        (path / "plugin.json").write_text(json.dumps({"name": "parallax", "version": bb.PLUGIN_VERSION}))
        (bb.PLUGIN_DIR / ".mcp.json").write_text(json.dumps({"mcpServers": {
            "parallax": {"type": "http", "url": bb.PARALLAX_MCP_URL}}}))
        (bb.PLUGIN_DIR / "skills/demo").mkdir(parents=True)
        (bb.PLUGIN_DIR / "skills/demo/SKILL.md").write_bytes(source.read_bytes())

    def web(names):
        release.write_zip(bb.WEB_OUT_DIR / "demo.skill", [("demo/SKILL.md", source)])

    monkeypatch.setattr(bb, "build_plugin", plugin)
    monkeypatch.setattr(bb, "build_web", web)
    return root


@pytest.mark.parametrize("preview", [False, True])
def test_build_records_provenance_and_download_urls(small_build, monkeypatch, preview):
    state = {"commit": "a" * 40, "dirty": preview, "tree_sha256": "b" * 64}
    monkeypatch.setattr(release, "source_state", lambda: state)
    output = small_build / "dist/output"
    release.build(output, preview=preview)
    index = release.verify_release(output)
    assert index["source"] == state
    assert index["preview"] is preview
    assert {a["name"] for a in index["assets"]} == {
        "demo.skill", "parallax-plugin.zip", "parallax-claude-ai-skills.zip"}
    for asset in index["assets"]:
        assert (asset["url"] is None) == preview
        if not preview:
            assert f"/v{bb.PLUGIN_VERSION}/" in asset["url"]


def test_source_change_during_build_exposes_no_output(small_build, monkeypatch):
    states = iter([{"commit": "a" * 40, "dirty": True, "tree_sha256": "b" * 64},
                   {"commit": "a" * 40, "dirty": True, "tree_sha256": "c" * 64}])
    monkeypatch.setattr(release, "source_state", lambda: next(states))
    output = small_build / "dist/output"
    old_plugin_dir = bb.PLUGIN_DIR
    with pytest.raises(bb.BuildError, match="source changed"):
        release.build(output, preview=True)
    assert not output.exists()
    assert not list(output.parent.iterdir())
    assert bb.PLUGIN_DIR == old_plugin_dir


def test_prepare_is_repeatable_and_updates_one_version_source(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    script = root / "skills/_parallax/scripts/build_bundle.py"
    script.parent.mkdir(parents=True)
    script.write_text('PLUGIN_VERSION = "2026.10.7"  # old\n')
    (root / "CHANGELOG.md").write_text("# Changes\n\n## 2026-10-07\nPrevious changes.\n")
    (root / "README.md").write_text(
        "<!-- roles:begin -->\n<!-- roles:end -->\n"
        "<!-- distributions:begin -->\n<!-- distributions:end -->\n")
    monkeypatch.setattr(release, "ROOT", root)
    monkeypatch.setattr(bb, "PLUGIN_VERSION", "2026.10.7")
    versions = []
    monkeypatch.setattr(bb, "build_plugin", lambda: versions.append(bb.PLUGIN_VERSION))
    release.prepare("2026.10.8")
    first = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    release.prepare("2026.10.8")
    assert first == {p: p.read_bytes() for p in first}
    assert versions == ["2026.10.8", "2026.10.8"]
    assert 'PLUGIN_VERSION = "2026.10.8"' in script.read_text()
    with pytest.raises(bb.BuildError, match="precede"):
        release.prepare("2026.10.7")


@pytest.mark.parametrize("field", ["schema_version", "source", "preview", "tag", "built_at",
                                  "mcp", "skills", "assets"])
def test_missing_release_contract_fields_rejected(tmp_path, field):
    out = make_release(tmp_path)
    index = json.loads((out / "index.json").read_text())
    del index[field]
    (out / "index.json").write_text(json.dumps(index))
    with pytest.raises(bb.BuildError, match="invalid release index"):
        release.verify_release(out)


@pytest.mark.parametrize("path,value", [
    (("assets",), []), (("skills",), []), (("preview",), "false"),
    (("schema_version",), True), (("tag",), "v2026.10.9"),
    (("source", "commit"), "unknown"), (("source", "tree_sha256"), "bad"),
    (("source", "dirty"), "false"), (("built_at",), "2026-10-08"),
    (("assets", 0, "url"), "https://example.com/package"),
    (("assets", 0, "latest_url"), "https://example.com/package"),
    (("skills", 0, "surfaces"), ["unknown"]),
    (("skills", 0, "asset"), "wrong.skill"),
    (("skills", 0, "surfaces"), ["plugin"]),
])
def test_invalid_release_contract_rejected(tmp_path, path, value):
    out = make_release(tmp_path)
    index = json.loads((out / "index.json").read_text())
    entry = index
    for key in path[:-1]:
        entry = entry[key]
    entry[path[-1]] = value
    (out / "index.json").write_text(json.dumps(index))
    with pytest.raises(bb.BuildError, match="invalid release index"):
        release.verify_release(out)


def test_nonpreview_requires_clean_source_and_pinned_urls(tmp_path):
    out = make_release(tmp_path)
    index = json.loads((out / "index.json").read_text())
    index["preview"] = False
    for asset in index["assets"]:
        asset["url"] = f"{release.REPOSITORY}/releases/download/{index['tag']}/{asset['name']}"
        asset["latest_url"] = f"{release.REPOSITORY}/releases/latest/download/{asset['name']}"
    refresh_checksums(out, index)
    with pytest.raises(bb.BuildError, match="non-preview source is dirty"):
        release.verify_release(out)
    index["source"]["dirty"] = False
    refresh_checksums(out, index)
    assert release.verify_release(out)["preview"] is False
    index["assets"][0]["url"] = index["assets"][0]["url"].replace("v2026.10.8", "v2026.10.7")
    refresh_checksums(out, index)
    with pytest.raises(bb.BuildError, match="URL differs"):
        release.verify_release(out)


@pytest.mark.parametrize("removed", ["parallax-plugin.zip", "parallax-claude-ai-skills.zip"])
def test_missing_primary_archive_rejected(tmp_path, removed):
    out = make_release(tmp_path)
    index = json.loads((out / "index.json").read_text())
    index["assets"] = [a for a in index["assets"] if a["name"] != removed]
    (out / removed).unlink()
    refresh_checksums(out, index)
    with pytest.raises(bb.BuildError, match="missing primary archives"):
        release.verify_release(out)


@pytest.mark.parametrize("change", ["missing-connector", "wrong-connector", "missing-skill",
                                   "extra-skill", "wrong-name"])
def test_plugin_contract_checked_after_rehashing(tmp_path, change):
    out = make_release(tmp_path)
    archive = out / "parallax-plugin.zip"
    with zipfile.ZipFile(archive) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    if change == "missing-connector":
        del files["plugin/.mcp.json"]
    elif change == "wrong-connector":
        files["plugin/.mcp.json"] = b'{"mcpServers": {}}'
    elif change == "missing-skill":
        del files["plugin/skills/demo/SKILL.md"]
    elif change == "extra-skill":
        files["plugin/skills/extra/SKILL.md"] = files["plugin/skills/demo/SKILL.md"]
    else:
        files["plugin/.claude-plugin/plugin.json"] = b'{"name":"wrong","version":"2026.10.8"}'
    with zipfile.ZipFile(archive, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    index = json.loads((out / "index.json").read_text())
    refresh_checksums(out, index)
    with pytest.raises(bb.BuildError):
        release.verify_release(out)


def test_historical_membership_independent_of_current_manifest(tmp_path, monkeypatch):
    out = make_release(tmp_path)
    monkeypatch.setattr(bb, "PLUGIN_SKILLS", ["current-only"])
    monkeypatch.setattr(bb, "WEB_SKILLS", ["current-only"])
    assert release.verify_release(out)["skills"][0]["name"] == "demo"


@pytest.mark.parametrize("content", ["", "---\n- item\n---\n", "---\nname: other\ndescription: Demo\n---\n",
                                     "---\nname: demo\ndescription: '  '\n---\n",
                                     "---\nname: demo\ndescription: [Demo]\n---\n",
                                     "---\nname: [\n---\n"])
@pytest.mark.parametrize("surface", ["plugin", "upload"])
def test_invalid_packaged_skill_metadata_rejected(tmp_path, content, surface):
    out = make_release(tmp_path)
    path = out / ("parallax-plugin.zip" if surface == "plugin" else "demo.skill")
    with zipfile.ZipFile(path) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    entry = "plugin/skills/demo/SKILL.md" if surface == "plugin" else "demo/SKILL.md"
    files[entry] = content.encode()
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    with pytest.raises(bb.BuildError, match="skill entrypoint"):
        release.verify_asset(path, "2026.10.8")


def test_nonobject_plugin_manifest_rejected(tmp_path):
    out = make_release(tmp_path)
    path = out / "parallax-plugin.zip"
    with zipfile.ZipFile(path) as zf:
        files = {name: zf.read(name) for name in zf.namelist()}
    files["plugin/.claude-plugin/plugin.json"] = b'[]'
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    with pytest.raises(bb.BuildError, match="identity"):
        release.verify_asset(path, "2026.10.8")


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32"])
@pytest.mark.parametrize("surface", ["plugin", "upload"])
def test_release_scan_refuses_nontext_encodings(tmp_path, encoding, surface):
    out = make_release(tmp_path)
    archive = out / ("parallax-plugin.zip" if surface == "plugin" else "demo.skill")
    prefix = "plugin/skills/demo" if surface == "plugin" else "demo"
    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr(f"{prefix}/references/extra.txt", bb.CANARY_TERMS[0].encode(encoding))
    if surface == "upload":
        release.write_zip(out / "parallax-claude-ai-skills.zip", [(archive.name, archive)])
    index = json.loads((out / "index.json").read_text())
    refresh_checksums(out, index)
    with pytest.raises(bb.BuildError, match="UTF-8 text"):
        release.verify_release(out)


@pytest.mark.parametrize("link_kind", ["file", "directory"])
@pytest.mark.parametrize("source_kind", ["skill", "example"])
def test_build_refuses_symlinked_package_source(small_build, monkeypatch, link_kind, source_kind):
    entrypoint = small_build / "skills/demo/SKILL.md"
    source = entrypoint
    tracked = "skills/demo/SKILL.md\0"
    if source_kind == "example":
        source = small_build / "examples/demo.md"
        source.parent.mkdir()
        source.write_text("Example\n")
        tracked += "examples/demo.md\0"
        original_plugin = bb.build_plugin

        def plugin():
            original_plugin()
            target = bb.PLUGIN_DIR / "examples/demo.md"
            target.parent.mkdir()
            target.write_bytes(source.read_bytes())

        monkeypatch.setattr(bb, "build_plugin", plugin)
    outside = small_build.parent / "external"
    if link_kind == "file":
        source.rename(outside)
        source.symlink_to(outside)
    else:
        source.parent.rename(outside)
        source.parent.symlink_to(outside, target_is_directory=True)
    # Git metadata is controlled; the linked bytes and builder are real files.
    replies = {("ls-files", "-z"): tracked,
               ("rev-parse", "HEAD"): "a" * 40,
               ("status", "--porcelain", "--untracked-files=normal"): ""}
    monkeypatch.setattr(release, "git", lambda *args: replies[args])

    def web(names):
        # The real web builder copies source bytes before it writes the ZIP.
        copied = small_build.parent / "copied.md"
        copied.write_bytes(entrypoint.read_bytes())
        release.write_zip(bb.WEB_OUT_DIR / "demo.skill", [("demo/SKILL.md", copied)])

    monkeypatch.setattr(bb, "build_web", web)
    output = small_build / "dist/output"
    with pytest.raises(bb.BuildError, match="symlink"):
        release.build(output)
    assert not output.exists()


def test_documentation_symlink_can_remain_in_source_fingerprint(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "audit.md").write_text("Audit record\n")
    (root / "audit-latest.md").symlink_to("audit.md")
    monkeypatch.setattr(release, "ROOT", root)
    replies = {("ls-files", "-z"): "audit.md\0audit-latest.md\0",
               ("rev-parse", "HEAD"): "a" * 40,
               ("status", "--porcelain", "--untracked-files=normal"): ""}
    monkeypatch.setattr(release, "git", lambda *args: replies[args])
    assert release.source_state()["dirty"] is False


@pytest.mark.parametrize("upload", [True, False])
def test_index_description_matches_mapped_package(small_build, monkeypatch, upload):
    state = {"commit": "a" * 40, "dirty": True, "tree_sha256": "b" * 64}
    monkeypatch.setattr(release, "source_state", lambda: state)
    original_plugin = bb.build_plugin
    original_web = bb.build_web

    def plugin():
        original_plugin()
        entry = bb.PLUGIN_DIR / "skills/demo/SKILL.md"
        entry.write_text(entry.read_text().replace("A demo", "Plugin description"))
        if not upload:
            other = bb.PLUGIN_DIR / "skills/plugin-only"
            other.mkdir()
            (other / "SKILL.md").write_text(
                "---\nname: plugin-only\ndescription: Plugin-only description\n---\nDemo\n")

    def web(names):
        original_web(names)
        archive = bb.WEB_OUT_DIR / "demo.skill"
        with zipfile.ZipFile(archive) as zf:
            content = zf.read("demo/SKILL.md").replace(b"A demo", b"Upload description")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("demo/SKILL.md", content)

    monkeypatch.setattr(bb, "build_plugin", plugin)
    monkeypatch.setattr(bb, "build_web", web)
    if not upload:
        monkeypatch.setattr(bb, "PLUGIN_SKILLS", ["demo", "plugin-only"])
        monkeypatch.setattr(bb.skill_manifest, "skills", lambda: {
            "demo": {"web": True, "plugin": True}, "plugin-only": {"plugin": True}})
        source = small_build / "skills/plugin-only"
        source.mkdir()
        (source / "SKILL.md").write_text(
            "---\nname: plugin-only\ndescription: Source description\n---\nDemo\n")
    output = small_build / "dist/output"
    release.build(output, preview=True)
    index = release.verify_release(output)
    rows = {row["name"]: row for row in index["skills"]}
    if not upload:
        assert rows["plugin-only"]["description"] == "Plugin-only description"
    assert rows["demo"]["description"] == "Upload description"


def test_rehashed_index_with_wrong_description_rejected(tmp_path):
    out = make_release(tmp_path)
    index = json.loads((out / "index.json").read_text())
    index["skills"][0]["description"] = "A capability absent from the package"
    refresh_checksums(out, index)
    with pytest.raises(bb.BuildError, match="description"):
        release.verify_release(out)
