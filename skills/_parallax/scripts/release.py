#!/usr/bin/env python3
"""Prepare a date version or build verified release assets. Never publishes.

prepare YYYY.M.D updates the version, changelog heading, docs and plugin.
build requires a clean committed tree; --preview permits local review builds.
verify DIR checks asset inventory, hashes, archive structure and term scans.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import yaml

import build_bundle as bb
import distribution_docs

ROOT = bb.REPO_ROOT
REPOSITORY = "https://github.com/bencharoenwong/parallax-workflows"
VERSION_RE = re.compile(r"20\d{2}\.[1-9]\d?\.[1-9]\d?")


def date_version(value: str) -> date:
    """Accept calendar dates in semver-compatible YYYY.M.D form."""
    if not VERSION_RE.fullmatch(value):
        raise bb.BuildError("version must be YYYY.M.D without zero padding")
    try:
        return date(*map(int, value.split(".")))
    except ValueError as exc:
        raise bb.BuildError("version is not a calendar date") from exc


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_state() -> dict:
    """Fingerprint tracked working files, including local preview changes."""
    paths = git("ls-files", "-z").split("\0")
    h = hashlib.sha256()
    for rel in sorted(set(filter(None, paths))):
        path = ROOT / rel
        relative = Path(rel)
        if relative.parts[0] in {"skills", "examples"} and any(
                (ROOT / part).is_symlink() for part in (relative, *relative.parents)):
            raise bb.BuildError(f"release package source cannot contain symlinks: {rel}")
        h.update(rel.encode() + b"\0")
        if path.is_symlink():
            h.update(b"link\0" + os.readlink(path).encode())
        elif path.is_file():
            h.update(str(stat.S_IMODE(path.stat().st_mode)).encode() + b"\0")
            h.update(path.read_bytes())
        else:
            h.update(b"missing")
        h.update(b"\0")
    return {"commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--untracked-files=normal")),
            "tree_sha256": h.hexdigest()}


def require_full_scan() -> None:
    """Release tooling never accepts the developer-only partial-scan bypass."""
    if not bb.EXTRA_CANARY_FILE.is_file():
        raise bb.BuildError("release builds require the maintainer's full scan-term file")
    if not any(x.strip() and not x.lstrip().startswith("#")
               for x in bb.EXTRA_CANARY_FILE.read_text().splitlines()):
        raise bb.BuildError("release scan-term file is empty")
    bb.load_canary_terms()


def write_zip(destination: Path, entries: list[tuple[str, Path]]) -> None:
    """Write stable archive paths, timestamps and permissions."""
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(entries):
            if path.is_symlink():
                raise bb.BuildError("release archives cannot contain symlinks")
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes())


def unpack(archive: Path, target: Path) -> None:
    """Reject unsafe, duplicate, oversized or non-file ZIP members."""
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > 5000 or sum(i.file_size for i in infos) > 200 * 1024 * 1024:
            raise bb.BuildError("archive exceeds 5,000 files or 200 MB expanded")
        seen = set()
        for info in infos:
            p = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            canonical = p.as_posix()
            # Case-insensitive filesystems merge case or Unicode-form variants.
            key = unicodedata.normalize("NFC", canonical).casefold()
            if (not p.parts or p.is_absolute() or ".." in p.parts
                    or "\\" in info.filename or ":" in info.filename
                    or key in seen or stat.S_ISLNK(mode)
                    or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
                raise bb.BuildError("unsafe or duplicate archive member")
            seen.add(key)
            dest = target.joinpath(*p.parts)
            if info.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(info))


def entrypoint_metadata(text: str, name: str) -> dict:
    """Require usable skill metadata matching its packaged directory name."""
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise bb.BuildError("skill entrypoint is missing frontmatter")
    try:
        metadata = yaml.safe_load("\n".join(lines[1:lines.index("---", 1)]))
    except yaml.YAMLError as exc:
        raise bb.BuildError("skill entrypoint has invalid frontmatter") from exc
    if (not isinstance(metadata, dict) or metadata.get("name") != name
            or not isinstance(metadata.get("description"), str)
            or not metadata["description"].strip()):
        raise bb.BuildError("skill entrypoint has invalid name or description")
    return metadata


def verify_entrypoint(skill: Path) -> None:
    """Require usable skill metadata matching the packaged directory."""
    entrypoint_metadata((skill / "SKILL.md").read_text(encoding="utf-8"), skill.name)


def packaged_description(asset: Path, name: str) -> str:
    """Read discovery metadata from the package to which an index row points."""
    entry = (f"plugin/skills/{name}/SKILL.md" if asset.name == "parallax-plugin.zip"
             else f"{name}/SKILL.md")
    with zipfile.ZipFile(asset) as archive:
        text = archive.read(entry).decode("utf-8")
    return entrypoint_metadata(text, name)["description"]


def verify_text_tree(root: Path) -> None:
    """Require text the term scanner can read, including BOM-less encodings."""
    for member in root.rglob("*"):
        if not member.is_file():
            continue
        try:
            content = member.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise bb.BuildError("package files must be UTF-8 text") from exc
        if "\0" in content:
            raise bb.BuildError("package files must be UTF-8 text without NUL bytes")


def verify_asset(path: Path, version: str, plugin_skills: set[str] | None = None,
                 mcp_url: str | None = None) -> None:
    """Verify extracted bytes, including nested skill archives."""
    with tempfile.TemporaryDirectory(prefix="parallax-verify-") as tmp:
        root = Path(tmp)
        unpack(path, root)
        if path.name == "parallax-plugin.zip" or path.suffix == ".skill":
            verify_text_tree(root)
        if path.name == "parallax-plugin.zip":
            plugin = root / "plugin"
            if sorted(p.name for p in root.iterdir()) != ["plugin"]:
                raise bb.BuildError("plugin archive must contain only plugin/")
            if not (plugin / ".claude-plugin/plugin.json").is_file() or not (plugin / ".mcp.json").is_file():
                raise bb.BuildError("plugin is missing its manifest or connector")
            manifest = json.loads((plugin / ".claude-plugin/plugin.json").read_text())
            if (not isinstance(manifest, dict) or manifest.get("name") != "parallax"
                    or manifest.get("version") != version):
                raise bb.BuildError("plugin identity/version differs from release")
            connector = json.loads((plugin / ".mcp.json").read_text())
            expected_connector = {"mcpServers": {"parallax": {
                "type": "http", "url": mcp_url or bb.PARALLAX_MCP_URL}}}
            if connector != expected_connector:
                raise bb.BuildError("plugin connector differs from release")
            skills_root = plugin / "skills"
            packaged = {p.name for p in skills_root.iterdir()
                        if p.is_dir() and p.name != "_parallax"} if skills_root.is_dir() else set()
            if (not packaged or any(not (skills_root / name / "SKILL.md").is_file()
                                    for name in packaged)
                    or (plugin_skills is not None and packaged != plugin_skills)):
                raise bb.BuildError("plugin skill inventory differs from release")
            bb.canary_scan(plugin)
            for name in packaged:
                verify_entrypoint(skills_root / name)
            bb.resolution_check(plugin / "skills")
        elif path.name == "parallax-claude-ai-skills.zip":
            if not list(root.iterdir()):
                raise bb.BuildError("skill collection is empty")
            for child in root.iterdir():
                if not child.is_file() or child.suffix != ".skill":
                    raise bb.BuildError("skill collection contains a non-skill asset")
                verify_asset(child, version)
        elif path.suffix == ".skill":
            if sorted(p.name for p in root.iterdir()) != [path.stem]:
                raise bb.BuildError("skill archive has the wrong root directory")
            skill = root / path.stem
            if not (skill / "SKILL.md").is_file():
                raise bb.BuildError("skill archive is missing SKILL.md")
            bb.verify_package(root)
            verify_entrypoint(skill)
            bb.web_resolution_check(skill)
        else:
            raise bb.BuildError("unknown release asset")


def validate_index(index: dict) -> set[str]:
    """Validate the self-contained release contract, including historical indexes."""
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise bb.BuildError(f"invalid release index: {message}")

    require(isinstance(index, dict), "expected an object")
    require(type(index.get("schema_version")) is int and index["schema_version"] == 1,
            "unsupported schema_version")
    require(isinstance(index.get("version"), str), "missing version")
    date_version(index["version"])
    require(index.get("tag") == f"v{index['version']}", "tag/version mismatch")
    require(type(index.get("preview")) is bool, "preview must be boolean")
    source = index.get("source")
    require(isinstance(source, dict), "missing source provenance")
    for key, length in (("commit", 40), ("tree_sha256", 64)):
        require(isinstance(source.get(key), str)
                and re.fullmatch(rf"[0-9a-f]{{{length}}}", source[key]) is not None,
                f"invalid source {key}")
    require(type(source.get("dirty")) is bool, "source dirty must be boolean")
    require(index["preview"] or not source["dirty"], "non-preview source is dirty")
    require(isinstance(index.get("built_at"), str), "missing build timestamp")
    try:
        require(datetime.fromisoformat(index["built_at"]).utcoffset() is not None,
                "build timestamp requires a timezone")
    except ValueError as exc:
        raise bb.BuildError("invalid release index: build timestamp") from exc
    mcp = index.get("mcp")
    require(isinstance(mcp, dict) and mcp.get("required") is True, "missing MCP requirement")
    require(isinstance(mcp.get("url"), str), "missing MCP URL")
    url = urlsplit(mcp["url"])
    require(url.scheme == "https" and bool(url.netloc) and url.username is None
            and url.password is None, "invalid MCP URL")
    require(isinstance(mcp.get("authentication"), str) and bool(mcp["authentication"].strip()),
            "missing MCP authentication instructions")
    require(isinstance(index.get("assets"), list) and bool(index["assets"]), "empty assets")
    names = set()
    for asset in index["assets"]:
        require(isinstance(asset, dict), "invalid asset entry")
        name = asset.get("name")
        require(isinstance(name, str) and (name in {
            "parallax-plugin.zip", "parallax-claude-ai-skills.zip"}
            or re.fullmatch(r"[a-z0-9][a-z0-9-]*\.skill", name) is not None),
            "invalid asset name")
        require(name not in names, "duplicate asset name")
        names.add(name)
        require(type(asset.get("size")) is int and asset["size"] > 0, "invalid asset size")
        require(isinstance(asset.get("sha256"), str)
                and re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]) is not None,
                "invalid asset checksum")
        for key, base in (("url", f"{REPOSITORY}/releases/download/{index['tag']}"),
                          ("latest_url", f"{REPOSITORY}/releases/latest/download")):
            require(key in asset and asset[key] == (None if index["preview"] else f"{base}/{name}"),
                    "asset URL differs from release")
    require({"parallax-plugin.zip", "parallax-claude-ai-skills.zip"} <= names,
            "missing primary archives")
    require(isinstance(index.get("skills"), list) and bool(index["skills"]), "empty skills")
    seen, plugin_skills, uploads = set(), set(), set()
    for skill in index["skills"]:
        require(isinstance(skill, dict), "invalid skill entry")
        name = skill.get("name")
        require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) is not None
                and name not in seen, "invalid or duplicate skill name")
        seen.add(name)
        require(isinstance(skill.get("description"), str) and bool(skill["description"].strip()),
                "missing skill description")
        surfaces = skill.get("surfaces")
        require(isinstance(surfaces, list) and bool(surfaces)
                and all(s in ("plugin", "skill-upload") for s in surfaces)
                and len(set(surfaces)) == len(surfaces), "invalid skill surfaces")
        if "plugin" in surfaces:
            plugin_skills.add(name)
        if "skill-upload" in surfaces:
            uploads.add(f"{name}.skill")
        require(skill.get("asset") == (f"{name}.skill" if "skill-upload" in surfaces
                                      else "parallax-plugin.zip"), "invalid skill asset mapping")
    require(bool(plugin_skills), "empty plugin skills")
    require(bool(uploads) and uploads == {n for n in names if n.endswith(".skill")},
            "upload skill inventory differs from assets")
    return plugin_skills


def verify_release(directory: Path) -> dict:
    """Check every listed asset and reject extra or missing files."""
    require_full_scan()
    index = json.loads((directory / "index.json").read_text())
    plugin_skills = validate_index(index)
    names = [a["name"] for a in index["assets"]]
    expected = set(names) | {"index.json", "SHA256SUMS"}
    if {p.name for p in directory.iterdir()} != expected:
        raise bb.BuildError("release directory does not match asset inventory")
    for asset in index["assets"]:
        path = directory / asset["name"]
        if path.is_symlink() or digest(path) != asset["sha256"] or path.stat().st_size != asset["size"]:
            raise bb.BuildError(f"asset checksum/size mismatch: {asset['name']}")
        verify_asset(path, index["version"], plugin_skills, index["mcp"]["url"])
    for skill in index["skills"]:
        if skill["description"] != packaged_description(directory / skill["asset"], skill["name"]):
            raise bb.BuildError("skill description differs from its mapped release asset")
    collection = directory / "parallax-claude-ai-skills.zip"
    if collection.exists():
        with zipfile.ZipFile(collection) as zf:
            expected_skills = {n for n in names if n.endswith(".skill")}
            if set(zf.namelist()) != expected_skills:
                raise bb.BuildError("collection skill set differs from individual assets")
            for name in expected_skills:
                if zf.read(name) != (directory / name).read_bytes():
                    raise bb.BuildError("collection contains a different skill package")
    sums = "".join(f"{digest(directory / n)}  {n}\n" for n in sorted(set(names) | {"index.json"}))
    if (directory / "SHA256SUMS").read_text() != sums:
        raise bb.BuildError("SHA256SUMS does not match release assets")
    with tempfile.TemporaryDirectory() as tmp:
        metadata = Path(tmp) / "index.json"
        metadata.write_bytes((directory / "index.json").read_bytes())
        bb.canary_scan(Path(tmp))
    return index


def build(output: Path, preview: bool = False) -> Path:
    """Build into a temporary sibling; expose the result only after verification."""
    require_full_scan()
    version = bb.PLUGIN_VERSION
    date_version(version)
    before = source_state()
    if before["dirty"] and not preview:
        raise bb.BuildError("release requires a clean committed tree; use --preview for review")
    if not preview and f"## {version}\n" not in (ROOT / "CHANGELOG.md").read_text():
        raise bb.BuildError("prepare the release version and changelog before building")
    if output.exists():
        raise bb.BuildError("output already exists; choose a new directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    old = bb.PLUGIN_DIR, bb.MARKETPLACE_FILE, bb.WEB_OUT_DIR
    try:
        with tempfile.TemporaryDirectory(prefix=".release-", dir=output.parent) as tmp:
            staging = Path(tmp)
            assets = staging / "assets"
            assets.mkdir()
            bb.PLUGIN_DIR = staging / "plugin"
            bb.MARKETPLACE_FILE = staging / "marketplace.json"
            bb.WEB_OUT_DIR = assets
            bb.build_plugin()
            write_zip(assets / "parallax-plugin.zip", [
                ("plugin/" + p.relative_to(bb.PLUGIN_DIR).as_posix(), p)
                for p in bb.PLUGIN_DIR.rglob("*") if p.is_file()])
            if set(bb.WEB_SKILLS) & set(bb.skill_manifest.standalone_skills("release")):
                raise bb.BuildError("a skill cannot be both a web and a release-tier package")
            bb.build_web(bb.WEB_SKILLS)
            env = dict(os.environ, SKILL_BUILD_OUT_DIR=str(assets))
            subprocess.run(["bash", str(ROOT / "skills/build-skills.sh")],
                           cwd=ROOT, env=env, check=True)
            skill_files = sorted(assets.glob("*.skill"))
            names = set(bb.WEB_SKILLS) | set(bb.skill_manifest.standalone_skills("release"))
            if {p.stem for p in skill_files} != names:
                raise bb.BuildError("built skill set does not match release manifest")
            write_zip(assets / "parallax-claude-ai-skills.zip", [(p.name, p) for p in skill_files])
            base = f"{REPOSITORY}/releases/download/v{version}"
            latest = f"{REPOSITORY}/releases/latest/download"
            rows = []
            for path in sorted(assets.iterdir()):
                rows.append({"name": path.name, "size": path.stat().st_size,
                             "sha256": digest(path),
                             "url": None if preview else f"{base}/{path.name}",
                             "latest_url": None if preview else f"{latest}/{path.name}"})
            index = {"schema_version": 1, "version": version, "tag": f"v{version}",
                     "preview": preview, "source": before,
                     "built_at": datetime.now(timezone.utc).isoformat(),
                     "mcp": {"required": True, "url": bb.PARALLAX_MCP_URL,
                             "authentication": "Sign in with your Parallax account."},
                     "assets": rows, "skills": []}
            for name in sorted(set(bb.PLUGIN_SKILLS) | names):
                row = bb.skill_manifest.skills()[name]
                surfaces = (["plugin"] if row.get("plugin") else []) + (["skill-upload"] if name in names else [])
                asset = f"{name}.skill" if name in names else "parallax-plugin.zip"
                description = packaged_description(assets / asset, name)
                index["skills"].append({"name": name, "description": description,
                                        "surfaces": surfaces,
                                        "asset": asset})
            (assets / "index.json").write_text(json.dumps(index, indent=2) + "\n")
            (assets / "SHA256SUMS").write_text("".join(
                f"{digest(p)}  {p.name}\n" for p in sorted(assets.iterdir())))
            verify_release(assets)
            if source_state() != before:
                raise bb.BuildError("source changed during build; discard and rebuild")
            if output.exists():
                raise bb.BuildError("output appeared during build; refusing to replace it")
            assets.rename(output)
    finally:
        bb.PLUGIN_DIR, bb.MARKETPLACE_FILE, bb.WEB_OUT_DIR = old
    return output


def prepare(version: str) -> None:
    """Update the sole version source and regenerate its consumers for review."""
    if date_version(version) < date_version(bb.PLUGIN_VERSION):
        raise bb.BuildError("version cannot precede the current release date")
    require_full_scan()
    path = ROOT / "skills/_parallax/scripts/build_bundle.py"
    text, count = re.subn(r'^PLUGIN_VERSION = "[^"]+".*$',
                         f'PLUGIN_VERSION = "{version}"  # maintained by release.py prepare',
                         path.read_text(), flags=re.M)
    if count != 1:
        raise bb.BuildError("version source is missing or ambiguous")
    readme = ROOT / "README.md"
    rendered_readme = distribution_docs.render(readme.read_text())
    changelog = ROOT / "CHANGELOG.md"
    log = changelog.read_text()
    if f"## {version}\n" not in log:
        at = log.index("\n## ")
        log = log[:at] + f"\n## {version}\n\nRelease packages for the changes listed below.\n" + log[at:]
    path.write_text(text)
    bb.PLUGIN_VERSION = version
    changelog.write_text(log)
    readme.write_text(rendered_readme)
    bb.build_plugin()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("version")
    p = sub.add_parser("build")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--out", type=Path)
    p = sub.add_parser("verify")
    p.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args.version)
        elif args.command == "verify":
            index = verify_release(args.directory)
            print(f"Verified {len(index['assets'])} assets; preview={index['preview']}")
        else:
            suffix = "-preview" if args.preview else ""
            output = args.out or ROOT / "dist" / (bb.PLUGIN_VERSION + suffix)
            print(f"Built: {build(output.resolve(), args.preview)}")
    except (bb.BuildError, OSError, ValueError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
