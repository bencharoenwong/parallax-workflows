#!/usr/bin/env python3
"""Block registered client names, maintainer-only paths and unreadable files from
this PUBLIC repo.

WHY. Client work starts as a build for one client and is later generalised into a
skill. The client's name rides along in fixtures, URLs, commit messages, branch
names, tags and PR descriptions, and each of those is public the moment it is
pushed or opened. ``scan_tracked_terms.py`` and ``scan_commit_messages.py`` match
exact spellings from a list only the maintainer holds; they cannot run in CI or
on a teammate's machine without publishing the list.

HOW THE LIST STAYS PRIVATE. ``.client-guard/registry.json`` is tracked and holds
only keyed hashes (HMAC-SHA256): one per normalised name, one per name's first
four characters (a prefilter), a key verifier, and the set of name lengths. The key
is NOT tracked: CI reads the ``CLIENT_GUARD_KEY`` secret; a teammate keeps it in
``~/.config/parallax/client-guard.key`` (or the same environment variable). A
missing or WRONG key fails closed. Register every form a name is written in --
legal name, short name, domain -- because a long registered form does not match
a shorter one.

TRUSTED COPY. With ``CLIENT_GUARD_TRUSTED_REV`` set (the pre-push hook sets it to
``origin/main``; CI to the PR base or to main), the registry and allowlist
committed at that revision are merged with the working copy, so a change cannot
weaken the check that judges it by deleting entries.

MATCHING. Text is NFKC-normalised, stripped of invisible characters, casefolded,
and common Cyrillic/Greek look-alikes are mapped to Latin. Letters and digits
separated by up to eight of `` ._+-&'"`~:/|*`` (and curly quotes, dashes, bullets,
middle dots), by ``%20``, or by up to two line breaks with an optional comment
prefix (``#``, ``//``, ``*``, ``>``, ``--``, ``;``) form one run; separators are
dropped. So "Acme & Widgets", "ACME-WIDGETS", "acme.widgets.com", "acme/widgets"
and a name wrapped across a comment block all reduce to ``acmewidgets``. A comma,
bracket or parenthesis ends a run. Names of eight characters or fewer must start
and end on a word boundary (a separator, a run edge, a lower-to-upper case change
or a letter/digit change), so a short name does not fire inside longer words;
longer names match anywhere. Each text is also scanned with HTML/XML entities,
``\\uXXXX`` escapes and ``%XX`` decoded, and with markup tags removed (so a name
split across Word runs is caught).

WHAT IS SCANNED. File contents (UTF-8, UTF-16, UTF-32), file paths, members and
comments of zip containers (.docx/.xlsx/.pptx/.zip), commit messages and
author/committer identities, merge commits against each parent, annotated tag
objects (nested too) and the blob or tree a tag points at, ref names, and free text (PR, issue, comment, review and
release text). FILES THE SCANNER CANNOT READ -- PDFs, legacy Office files,
images, compressed archives, nested archives, Git LFS pointers, anything binary --
ARE BLOCKED unless a key holder has allowlisted that exact content with
``client_guard.py allow <path>``. An unreadable file is not a clean one.

KNOWN LIMITS. Deliberate obfuscation (base64, reversal, letter substitution
outside the look-alike table) is not detected; the guard is built to stop
accidents. A pull request can still edit the workflow file itself; review
changes to ``.github/workflows/``.

OUTPUT. Rule ids and locations only, never the matched text. In CI, whose logs
are public, a location that itself contains a registered name is withheld.

Exit 0 clean, 1 on any hit, 2 when the scan cannot run.

Usage:
  client_guard.py add                     names on stdin, one per line
  client_guard.py allow PATH...           allowlist the current content of files
  client_guard.py scan-tree [REV]         every file in REV (default HEAD)
  client_guard.py scan-range [--ref R] REV...   commits/tags in a git-log range
  client_guard.py scan-text [--label L]   text on stdin (e.g. a PR body)
  client_guard.py scan-path DIR           a directory on disk, before promotion
  client_guard.py ci                      GitHub Actions entry point
"""
from __future__ import annotations

import hashlib
import hmac
import html
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(os.environ.get("CLIENT_GUARD_REPO_ROOT")
                 or Path(__file__).resolve().parents[3])
REGISTRY_REL = ".client-guard/registry.json"
ALLOW_REL = ".client-guard/allow-binary.txt"
REGISTRY_PATH = REPO_ROOT / REGISTRY_REL
ALLOW_PATH = REPO_ROOT / ALLOW_REL
KEY_ENV = "CLIENT_GUARD_KEY"
TRUSTED_ENV = "CLIENT_GUARD_TRUSTED_REV"
KEY_FILE = Path.home() / ".config" / "parallax" / "client-guard.key"
KEY_CHECK_INPUT = "client-guard registry key check v2"
PREFIX_LEN = 4
BOUNDARY_MAX = 8
MAX_BLOB_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
ZERO_SHA = "0" * 40

_INVISIBLE = re.compile("[\\u00ad\\u034f\\u061c\\u115f\\u1160\\u17b4\\u17b5\\u180e"
                        "\\u200b-\\u200f\\u202a-\\u202e\\u2060-\\u2064\\u2066-\\u206f\\ufeff]")
_CONFUSABLES = str.maketrans({
    "\u0430": "a", "\u0432": "b", "\u0435": "e", "\u043a": "k", "\u043c": "m",
    "\u043d": "h", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0442": "t",
    "\u0443": "y", "\u0445": "x", "\u0455": "s", "\u0456": "i", "\u0458": "j",
    "\u0501": "d", "\u051b": "q", "\u051d": "w", "\u04cf": "l", "\u03b1": "a",
    "\u03b2": "b", "\u03b5": "e", "\u03b9": "i", "\u03ba": "k", "\u03bd": "v",
    "\u03bf": "o", "\u03c1": "p", "\u03c4": "t", "\u03c5": "u", "\u03c7": "x",
    "\u03f2": "c",
})
_NL = r"(?:\r\n|\r|\n)[ \t]*(?:(?:#|//|\*|>|--|;)[ \t]*)?"
_SEP_CHARS = (" \\t\\u00a0._+\\-&'\"`~:/|*\\u2018\\u2019\\u201c\\u201d\\u00b7"
              "\\u2022\\u2212\\u2010-\\u2015")
_SEP = rf"(?:[{_SEP_CHARS}]{{1,8}}(?:{_NL}){{0,2}}|(?:{_NL}){{1,2}}|%20)"
_RUN = re.compile(rf"[^\W_]+(?:{_SEP}[^\W_]+)*")
_TOKEN = re.compile(r"[^\W_]+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
                    r"|(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])")
_NON_ALNUM = re.compile(r"[\W_]+")
_TAG = re.compile(r"<[^<>]*>")
_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")
_ALLOW_LINE = re.compile(r"^[0-9a-f]{40} [0-9a-f]{32}$")
_REGISTRY_KEYS = frozenset({"version", "algorithm", "normalization", "prefix_length",
                            "lengths", "prefixes", "digests", "verifier"})
_ZIP_SUFFIXES = (".docx", ".xlsx", ".pptx", ".zip", ".odt", ".ods", ".odp", ".docm", ".xlsm")
_OPAQUE_SUFFIXES = (
    ".pdf", ".doc", ".xls", ".ppt", ".rtf", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".rar", ".tar", ".zst", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".bmp", ".tif", ".tiff", ".heic", ".svgz", ".mp3", ".mp4", ".mov", ".wav",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pkl", ".parquet", ".db",
    ".sqlite", ".exe", ".dll", ".so", ".dylib", ".jar", ".class", ".wasm", ".ps",
)
_LFS_POINTER = b"version https://git-lfs.github.com/spec"

# Maintainer-only material. Never belongs in the public tree, whatever it contains.
_INTERNAL_DOC_NAMES = frozenset({
    "decisions.md", "learnings.md", "lessons.md", "plans.md", "session_log.md",
})
_INTERNAL_DOC_PREFIXES = ("docs/plans/", "docs/analysis/", "docs/superpowers/")
_CLIENT_DIRS = frozenset({"clients", "client-work"})
# Local tool caches never reach git; scan-path skips them.
_SKIP_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"})
_TEXT_EVENT_FIELDS = ("title", "body", "name", "tag_name")


class GuardError(RuntimeError):
    """The scan could not run. Never carries scanned text."""


def _mac(key: bytes, domain: str, s: str) -> str:
    return hmac.new(key, f"{domain}:{s}".encode("utf-8"), hashlib.sha256).hexdigest()


def _fold(text: str) -> str:
    return text.casefold().translate(_CONFUSABLES)


def normalize_name(name: str) -> str:
    clean = _INVISIBLE.sub("", unicodedata.normalize("NFKC", name))
    return _NON_ALNUM.sub("", _fold(clean))


def views(text: str) -> list[str]:
    """The text plus decoded forms that differ from it."""
    out = [text]
    decoded = text
    if "&" in decoded:
        decoded = html.unescape(decoded)
    if "\\u" in decoded:
        decoded = _UESC.sub(lambda m: chr(int(m.group(1), 16)), decoded)
    if "%" in decoded:
        decoded = urllib.parse.unquote(decoded)
    if decoded != text:
        out.append(decoded)
    if "<" in decoded and ">" in decoded:
        stripped = _TAG.sub("", decoded)
        if stripped != decoded:
            out.append(stripped)
    return out


def runs(text: str) -> list[tuple[str, frozenset[int]]]:
    """Joined runs, each with the offsets that are word boundaries in it."""
    clean = _INVISIBLE.sub("", unicodedata.normalize("NFKC", text))
    out = []
    for m in _RUN.finditer(clean):
        joined, bounds = [], {0}
        pos = 0
        for tok in _TOKEN.findall(m.group(0)):
            for piece in _CAMEL.split(tok):
                if not piece:
                    continue
                folded = _NON_ALNUM.sub("", _fold(piece))
                joined.append(folded)
                pos += len(folded)
                bounds.add(pos)
        out.append(("".join(joined), frozenset(bounds)))
    return out


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@dataclass
class Registry:
    digests: frozenset[str] = frozenset()
    prefixes: frozenset[str] = frozenset()
    lengths: tuple[int, ...] = ()
    key_check: str = ""

    @classmethod
    def parse(cls, raw: str, where: str) -> "Registry":
        try:
            data = json.loads(raw)
        except ValueError:
            raise GuardError(f"registry unreadable: {where}") from None
        if not isinstance(data, dict) or set(data) - _REGISTRY_KEYS:
            raise GuardError(f"registry has unexpected fields: {where}")
        if data.get("version") != 2 or data.get("algorithm") != "hmac-sha256":
            raise GuardError(f"registry has an unsupported version or algorithm: {where}")
        digests, prefixes = data.get("digests") or [], data.get("prefixes") or []
        lengths, check = data.get("lengths") or [], data.get("verifier") or ""
        if not digests or not prefixes or not lengths or not check:
            raise GuardError(f"registry is empty: {where}; refusing to report a clean scan")
        for value in [*digests, *prefixes, check]:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise GuardError(f"registry holds a malformed entry: {where}")
        return cls(frozenset(digests), frozenset(prefixes),
                   tuple(sorted({int(n) for n in lengths})), check)

    @classmethod
    def load(cls, path: Path | None = None) -> "Registry":
        path = REGISTRY_PATH if path is None else path
        try:
            return cls.parse(path.read_text(encoding="utf-8"), str(path))
        except FileNotFoundError:
            raise GuardError(f"registry not found: {path}") from None
        except OSError as exc:
            raise GuardError(f"registry unreadable: {path} ({type(exc).__name__})") from None

    @classmethod
    def at_rev(cls, rev: str) -> "Registry":
        res = _git("show", f"{rev}:{REGISTRY_REL}")
        if res.returncode != 0:
            raise GuardError(f"registry not found at {rev[:12]}")
        return cls.parse(res.stdout, f"{rev[:12]}:{REGISTRY_REL}")

    def verify(self, key: bytes) -> None:
        if not hmac.compare_digest(self.key_check, _mac(key, "check", KEY_CHECK_INPUT)):
            raise GuardError("the client-guard key does not match the registry; "
                             "get the current key from the maintainer")

    def union(self, other: "Registry") -> "Registry":
        return Registry(self.digests | other.digests, self.prefixes | other.prefixes,
                        tuple(sorted(set(self.lengths) | set(other.lengths))),
                        self.key_check or other.key_check)

    def save(self, path: Path | None = None) -> None:
        path = REGISTRY_PATH if path is None else path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "algorithm": "hmac-sha256",
            "normalization": "nfkc-casefold-confusables-alnum-runs",
            "prefix_length": PREFIX_LEN,
            "verifier": self.key_check,
            "lengths": sorted(self.lengths),
            "prefixes": sorted(self.prefixes),
            "digests": sorted(self.digests),
        }
        path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def load_key() -> bytes:
    raw = os.environ.get(KEY_ENV, "").strip()
    if not raw and KEY_FILE.is_file():
        if KEY_FILE.stat().st_mode & 0o077:
            raise GuardError(f"{KEY_FILE} is readable by other users; run chmod 600 on it")
        raw = KEY_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        raise GuardError(
            f"no key: set {KEY_ENV} or create {KEY_FILE} (ask the maintainer); "
            "the scan fails closed without it")
    return raw.encode("utf-8")


def parse_allowlist(key: bytes, raw: str, where: str) -> frozenset[str]:
    """Blob shas a key holder approved, one ``<sha> <mac>`` per line. Any other
    line, or an entry whose MAC does not verify, is an error."""
    ok = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        if not _ALLOW_LINE.match(line):
            raise GuardError(f"allowlist has a malformed line: {where}")
        sha, mac = line.split()
        if not hmac.compare_digest(mac, _mac(key, "allow", sha)[:32]):
            raise GuardError(f"allowlist entry not signed by this key: {where}")
        ok.add(sha)
    return frozenset(ok)


def decode_text(data: bytes) -> str | None:
    """Text, or None when the bytes are not text in any encoding read here."""
    for bom, enc in ((b"\x00\x00\xfe\xff", "utf-32-be"), (b"\xff\xfe\x00\x00", "utf-32-le"),
                     (b"\xef\xbb\xbf", "utf-8-sig"), (b"\xfe\xff", "utf-16-be"),
                     (b"\xff\xfe", "utf-16-le")):
        if data.startswith(bom):
            return data.decode(enc, "replace")
    head = data[:8192]
    if b"\0" in head:
        even, odd = head[0::2].count(0), head[1::2].count(0)
        if odd > len(head) // 4 and even < len(head) // 50:
            return data.decode("utf-16-le", "replace")
        if even > len(head) // 4 and odd < len(head) // 50:
            return data.decode("utf-16-be", "replace")
        return None
    text = data.decode("utf-8", "replace")
    # A few stray bytes (a legacy-encoded accent) still read as text; content
    # that is mostly undecodable is binary.
    if text.count("\ufffd") > max(8, len(text) // 100):
        return None
    return text


@dataclass
class Scanner:
    key: bytes
    registry: Registry
    allowed: frozenset[str] = frozenset()
    withhold: bool = False
    hits: list[tuple[str, str]] = field(default_factory=list)
    _prefix_cache: dict[str, bool] = field(default_factory=dict)

    def _prefix_ok(self, gram: str) -> bool:
        hit = self._prefix_cache.get(gram)
        if hit is None:
            hit = _mac(self.key, "prefix", gram) in self.registry.prefixes
            if len(self._prefix_cache) < 4_000_000:
                self._prefix_cache[gram] = hit
        return hit

    def _run_hits(self, run: str, bounds: frozenset[int]) -> bool:
        lengths = self.registry.lengths
        if len(run) < lengths[0]:
            return False
        for i in range(len(run) - PREFIX_LEN + 1):
            if not self._prefix_ok(run[i:i + PREFIX_LEN]):
                continue
            for n in lengths:
                if i + n > len(run):
                    break
                if n <= BOUNDARY_MAX and (i not in bounds or i + n not in bounds):
                    continue
                if _mac(self.key, "name", run[i:i + n]) in self.registry.digests:
                    return True
        return False

    def text_hits(self, text: str) -> bool:
        return any(self._run_hits(r, b) for v in views(text) for r, b in runs(v))

    def report(self, rule: str, where: str, context: str = "") -> None:
        if self.withhold and self.text_hits(where):
            safe = context if context and not self.text_hits(context) else "location"
            where = f"{safe}: location withheld (it contains a registered name)"
        self.hits.append((rule, where))

    def scan_text(self, text: str, where: str, context: str = "") -> None:
        if self.text_hits(text):
            self.report("client/name", where, context)

    def scan_path(self, path: str, where: str | None = None, context: str = "",
                  path_rules: bool = True) -> None:
        where = where or path
        if self.text_hits(path):
            self.report("client/name-in-path", where, context)
        if not path_rules:
            return
        lowered = path.replace("\\", "/").lower()
        parts = lowered.split("/")
        name = parts[-1]
        if (name in _INTERNAL_DOC_NAMES
                or (name.startswith("handoff") and name.endswith(".md"))
                or lowered.startswith(_INTERNAL_DOC_PREFIXES)
                or "notes" in parts[:-1]):
            self.report("path/internal-doc", where, context)
        if _CLIENT_DIRS.intersection(parts[:-1]):
            self.report("path/client-work", where, context)

    def scan_bytes(self, data: bytes, path: str, where: str, context: str = "",
                   depth: int = 0) -> None:
        if git_blob_sha(data) in self.allowed:
            return
        if len(data) > MAX_BLOB_BYTES:
            self.report("unscanned/too-large", where, context)
            return
        lowered = path.lower()
        if data.startswith(_LFS_POINTER):
            self.report("unscanned/lfs-pointer", where, context)
            return
        if lowered.endswith(_ZIP_SUFFIXES) or data[:4] == b"PK\x03\x04":
            if depth:
                self.report("unscanned/nested-archive", where, context)
            else:
                self._scan_archive(data, where, context)
            return
        if lowered.endswith(_OPAQUE_SUFFIXES):
            self.report("unscanned/opaque-file", where, context)
            return
        text = decode_text(data)
        if text is None:
            self.report("unscanned/binary", where, context)
            return
        self.scan_text(text, where, context)

    def _scan_archive(self, data: bytes, where: str, context: str) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                members = zf.infolist()
                if len(members) > MAX_ARCHIVE_MEMBERS or \
                        sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
                    self.report("unscanned/archive-too-large", where, context)
                    return
                if zf.comment:
                    self.scan_text(zf.comment.decode("utf-8", "replace"),
                                   f"{where} (archive comment)", context or where)
                for m in members:
                    inner = f"{where}!{m.filename}"
                    if self.text_hits(m.filename):
                        self.report("client/name-in-path", inner, context or where)
                    if m.comment:
                        self.scan_text(m.comment.decode("utf-8", "replace"), inner,
                                       context or where)
                    if not m.is_dir():
                        self.scan_bytes(zf.read(m), m.filename, inner, context or where, depth=1)
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, ValueError):
            self.report("unscanned/bad-archive", where, context)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                          capture_output=True, text=True, errors="replace")


def _cat_blobs(shas: list[str]) -> dict[str, bytes]:
    """Read many objects through one ``git cat-file --batch``. Every header's body
    is consumed whatever its type, and a missing object or a failed process is an
    error, never a silent skip."""
    out: dict[str, bytes] = {}
    if not shas:
        return out
    proc = subprocess.Popen(["git", "-C", str(REPO_ROOT), "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert proc.stdin and proc.stdout
    try:
        for sha in shas:
            proc.stdin.write((sha + "\n").encode())
            proc.stdin.flush()
            header = proc.stdout.readline().split()
            if len(header) != 3:
                raise GuardError(f"object {sha[:12]} could not be read")
            size = int(header[2])
            body = proc.stdout.read(size)
            proc.stdout.read(1)
            if len(body) != size:
                raise GuardError(f"object {sha[:12]} was truncated")
            if header[1] == b"blob":
                out[sha] = body
    finally:
        proc.stdin.close()
        rc = proc.wait()
    if rc != 0:
        raise GuardError("git cat-file failed")
    return out


def _object_exists(rev: str) -> bool:
    return _git("cat-file", "-e", f"{rev}^{{object}}").returncode == 0


def scan_tree(scanner: Scanner, rev: str = "HEAD") -> None:
    res = _git("ls-tree", "-r", "-z", "--full-tree", rev)
    if res.returncode != 0:
        raise GuardError(f"cannot list tree for {rev!r}")
    ctx = f"tree {rev[:12]}"
    entries = []
    for rec in res.stdout.split("\0"):
        if not rec:
            continue
        meta, path = rec.split("\t", 1)
        _mode, kind, sha = meta.split()
        scanner.scan_path(path, f"{rev}:{path}", ctx)
        if kind == "blob":
            entries.append((sha, path))
    blobs = _cat_blobs(sorted({sha for sha, _ in entries}))
    for sha, path in entries:
        scanner.scan_bytes(blobs[sha], path, f"{rev}:{path}", ctx)


def _positive_revs(revs: list[str]) -> list[str]:
    out = []
    for rev in revs:
        if rev.startswith("^"):
            continue
        out.append(rev.split("..", 1)[1] if ".." in rev else rev)
    return [r for r in out if r]


def _scan_tags(scanner: Scanner, rev: str) -> None:
    """Scan every annotated tag object reached by peeling ``rev``, and the content
    of the blob or tree it ends at. ``rev-list`` lists no commits for a blob or
    tree, so a tag pointing at one published content nothing else read."""
    for _ in range(32):
        kind = _git("cat-file", "-t", rev)
        if kind.returncode != 0:
            raise GuardError(f"object {rev[:12]} could not be read")
        obj = kind.stdout.strip()
        if obj == "blob":
            where = f"tagged blob {rev[:12]}"
            scanner.scan_bytes(_cat_blobs([rev])[rev], "", where, "tag")
            return
        if obj == "tree":
            scan_tree(scanner, rev)
            return
        if obj != "tag":
            return
        body = _git("cat-file", "-p", rev)
        if body.returncode != 0:
            raise GuardError(f"cannot read tag {rev[:12]}")
        scanner.scan_text(body.stdout, f"tag object {rev[:12]}", "tag")
        first = body.stdout.split("\n", 1)[0].split()
        if len(first) != 2 or first[0] != "object":
            return
        rev = first[1]
    raise GuardError("tag chain too deep")


def scan_range(scanner: Scanner, revs: list[str], ref: str | None = None) -> int:
    for rev in revs:
        if rev.startswith("-"):
            raise GuardError(f"revision selector {rev!r} looks like an option; refusing")
    if ref:
        scanner.scan_path(ref.removeprefix("refs/heads/").removeprefix("refs/tags/"),
                          f"ref {ref}", "pushed ref", path_rules=False)
    for rev in _positive_revs(revs):
        _scan_tags(scanner, rev)
    listed = _git("rev-list", *revs)
    if listed.returncode != 0:
        raise GuardError(f"cannot resolve range {' '.join(revs)!r}")
    commits = listed.stdout.split()
    for sha in commits:
        ctx = f"commit {sha[:12]}"
        msg = _git("log", "-1", "--format=%an%n%ae%n%cn%n%ce%n%B", sha)
        if msg.returncode != 0:
            raise GuardError(f"cannot read {ctx}")
        scanner.scan_text(msg.stdout, f"{ctx} message or identity", ctx)
        # -m diffs a merge against each parent; without it diff-tree prints
        # nothing for merges, and content added in the merge itself went unread.
        diff = _git("diff-tree", "-r", "-m", "-z", "--root", "--no-commit-id",
                    "--diff-filter=AMRCT", "--no-renames", sha)
        if diff.returncode != 0:
            raise GuardError(f"cannot diff {ctx}")
        fields = diff.stdout.split("\0")
        changed: list[tuple[str, str]] = []
        for i in range(0, len(fields) - 1, 2):
            meta, path = fields[i], fields[i + 1]
            parts = meta.split()
            if len(parts) < 4:
                continue
            scanner.scan_path(path, f"{ctx}:{path}", ctx)
            # 160000 is a gitlink (submodule commit), not content in this repo.
            if parts[1] != "160000" and parts[3] != ZERO_SHA:
                changed.append((parts[3], path))
        blobs = _cat_blobs(sorted({sha for sha, _ in changed}))
        for blob_sha, path in changed:
            scanner.scan_bytes(blobs[blob_sha], path, f"{ctx}:{path}", ctx)
    return len(commits)


def scan_dir(scanner: Scanner, root: Path) -> None:
    if not root.is_dir():
        raise GuardError(f"not a directory: {root}")
    for p in sorted(root.rglob("*")):
        parts = p.relative_to(root).parts
        if _SKIP_DIRS.intersection(parts) or not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(root).as_posix()
        scanner.scan_path(rel, rel, "directory")
        scanner.scan_bytes(p.read_bytes(), rel, rel, "directory")


def run_ci(scanner: Scanner) -> None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if not event_path:
        raise GuardError("GITHUB_EVENT_PATH not set; ci mode runs only in GitHub Actions")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    trusted = os.environ.get(TRUSTED_ENV, "").strip()
    if event_name.startswith("pull_request") and "pull_request" in event \
            and event_name != "pull_request_review" and event_name != "pull_request_review_comment":
        pr = event["pull_request"]
        n = pr["number"]
        scanner.scan_text(pr.get("title") or "", f"PR #{n} title", f"PR #{n}")
        scanner.scan_text(pr.get("body") or "", f"PR #{n} body", f"PR #{n}")
        scan_range(scanner, [pr["head"]["sha"], f"^{pr['base']['sha']}"],
                   ref=pr["head"]["ref"])
        scan_tree(scanner, pr["head"]["sha"])
    elif event_name == "push":
        after, before = event["after"], event.get("before") or ZERO_SHA
        ref = event.get("ref") or ""
        if after == ZERO_SHA:
            return  # a deletion publishes nothing
        tip = ref if ref.startswith("refs/tags/") and _object_exists(ref) else after
        if before != ZERO_SHA and _object_exists(before):
            revs = [tip, f"^{before}"]
        else:
            # New ref, or a force-push whose old tip is gone: scan what the ref
            # adds over the trusted base. `rev-list X ^X` is empty, which is right.
            revs = [tip] + ([f"^{trusted}"] if trusted else [])
        scan_range(scanner, revs, ref=ref)
        # A tag that ends at a blob has no tree; scan_range already read it.
        # A missing object is an error, never a skip.
        if not _object_exists(after):
            raise GuardError(f"pushed object {after[:12]} is not in this checkout")
        if _object_exists(f"{after}^{{tree}}"):
            scan_tree(scanner, after)
    else:
        for obj in ("issue", "comment", "review", "release", "discussion"):
            item = event.get(obj)
            if isinstance(item, dict):
                for key in _TEXT_EVENT_FIELDS:
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        scanner.scan_text(value, f"{event_name} {obj} {key}", event_name)
        if not any(isinstance(event.get(o), dict)
                   for o in ("issue", "comment", "review", "release", "discussion")):
            raise GuardError(f"unsupported event {event_name!r}")


_UNJOINED = re.compile(rf"[^\w{_SEP_CHARS}]")


def add_names(key: bytes, names: list[str], path: Path | None = None) -> int:
    path = REGISTRY_PATH if path is None else path
    check = _mac(key, "check", KEY_CHECK_INPUT)
    if path.exists():
        reg = Registry.load(path)
        reg.verify(key)
    else:
        reg = Registry(key_check=check)
    digests, prefixes, lengths = set(reg.digests), set(reg.prefixes), set(reg.lengths)
    before = len(digests)
    for name in names:
        norm = normalize_name(name)
        if len(norm) < PREFIX_LEN:
            raise GuardError(f"a name normalises to fewer than {PREFIX_LEN} letters/digits; "
                             "too short to match without false positives")
        if _UNJOINED.search(name):
            print("  ! a name contains punctuation that ends a run in text (such as a "
                  "comma); also register the forms it is written in without it",
                  file=sys.stderr)
        digests.add(_mac(key, "name", norm))
        prefixes.add(_mac(key, "prefix", norm[:PREFIX_LEN]))
        lengths.add(len(norm))
    Registry(frozenset(digests), frozenset(prefixes), tuple(sorted(lengths)), check).save(path)
    return len(digests) - before


def allow_files(key: bytes, paths: list[str]) -> int:
    existing = ALLOW_PATH.read_text(encoding="utf-8") if ALLOW_PATH.exists() else ""
    have = set(parse_allowlist(key, existing, ALLOW_REL))
    added = 0
    for p in paths:
        sha = git_blob_sha(Path(p).read_bytes())
        if sha not in have:
            have.add(sha)
            added += 1
    ALLOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALLOW_PATH.write_text("".join(f"{s} {_mac(key, 'allow', s)[:32]}\n" for s in sorted(have)),
                          encoding="utf-8")
    return added


def build_scanner(key: bytes, withhold: bool = False) -> Scanner:
    """Registry and allowlist from the working copy, merged with the copies
    committed at the trusted revision when one is set. Every registry found must
    verify against the key."""
    trusted = os.environ.get(TRUSTED_ENV, "").strip()
    registries, allowed = [], set()
    if REGISTRY_PATH.exists():
        registries.append(Registry.load())
    if ALLOW_PATH.exists():
        allowed |= parse_allowlist(key, ALLOW_PATH.read_text(encoding="utf-8"), ALLOW_REL)
    if trusted:
        registries.append(Registry.at_rev(trusted))
        res = _git("show", f"{trusted}:{ALLOW_REL}")
        if res.returncode == 0:
            allowed |= parse_allowlist(key, res.stdout, f"{trusted[:12]}:{ALLOW_REL}")
    if not registries:
        raise GuardError(f"registry not found: {REGISTRY_PATH}")
    for reg in registries:
        reg.verify(key)
    merged = registries[0]
    for reg in registries[1:]:
        merged = merged.union(reg)
    return Scanner(key, merged, frozenset(allowed), withhold=withhold)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, args = argv[0], argv[1:]
    try:
        key = load_key()
        if cmd == "add":
            names = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
            added = add_names(key, names)
            print(f"  \u2713 registry updated: {added} new name(s), "
                  f"{len(names) - added} already present")
            return 0
        if cmd == "allow":
            if not args:
                raise GuardError("allow needs at least one file")
            print(f"  \u2713 allowlisted {allow_files(key, args)} file(s); commit {ALLOW_REL}")
            return 0
        scanner = build_scanner(key, withhold=(cmd == "ci"))
        if cmd == "scan-tree":
            rev = args[0] if args else "HEAD"
            scan_tree(scanner, rev)
            what = f"tree {rev}"
        elif cmd == "scan-range":
            ref = None
            if args[:1] == ["--ref"]:
                if len(args) < 2:
                    raise GuardError("--ref needs a value")
                ref, args = args[1], args[2:]
            if not args:
                raise GuardError("scan-range needs at least one revision")
            what = f"{scan_range(scanner, args, ref=ref)} commit(s)"
        elif cmd == "scan-text":
            label = args[1] if args[:1] == ["--label"] and len(args) > 1 else "stdin"
            scanner.scan_text(sys.stdin.read(), label)
            what = "text"
        elif cmd == "scan-path":
            if not args:
                raise GuardError("scan-path needs a directory")
            scan_dir(scanner, Path(args[0]))
            what = "directory"
        elif cmd == "ci":
            run_ci(scanner)
            what = "event"
        else:
            raise GuardError(f"unknown command {cmd!r}")
    except GuardError as exc:
        print(f"[client-guard] FAIL: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - any crash must block, never pass
        print(f"[client-guard] FAIL: unexpected {type(exc).__name__}", file=sys.stderr)
        return 2
    if scanner.hits:
        for rule, where in sorted(set(scanner.hits)):
            print(f"  [client-guard] HIT [{rule}]: {where}", file=sys.stderr)
        print("[client-guard] BLOCKED: registered client name, maintainer-only path, or a "
              "file the guard cannot read. The match is not printed. Remove it locally "
              "(rename the fixture, reword the message, move client work to the private "
              "client repo), or have a key holder run `client_guard.py allow <path>` for "
              "a reviewed binary, and retry.", file=sys.stderr)
        return 1
    print(f"  \u2713 [client-guard] {what} \u2014 clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
