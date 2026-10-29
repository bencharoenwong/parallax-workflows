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

REGISTERING A NAME. ``add`` checks new names before writing the registry.
It scans HEAD's tree, commits not yet on ``origin/main``, the index, and
tracked and untracked-not-ignored working files. Without ``origin/main``,
it scans all history reachable from HEAD. Without HEAD, it still checks
the index and working files. It refuses registration when a new name
already appears in those locations. Locations print locally because this
command runs only on a key holder's machine. Existing registered names
do not block this check. This prevents a newly registered name from first
being reported through a public CI log.

TRUSTED COPY. With ``CLIENT_GUARD_TRUSTED_REV`` set (the pre-push hook sets it to
``origin/main``; CI to the PR base or to main), the registry and allowlist
committed at that revision are merged with the working copy, so a change cannot
weaken the check that judges it by deleting entries.

CHANGED COPY. A change revision requires a trusted revision.
``pull_request_target`` CI checks out the trusted base as the
workspace and never the PR head, so the working copy never holds the PR's own
registry/allowlist edits. With ``CLIENT_GUARD_CHANGE_REV`` set to the PR tip,
those two files are read as git objects at that revision and merged in too. A
file simply absent there is skipped -- except the registry when the change's
fork point (its merge base with the trusted revision) has one: deleting it
outright is a shrink to nothing and fails closed exactly like dropping some of
its entries, since either way removal needs a key holder. Removal is judged
against the fork point, so a PR branched before a newer registration is not
blamed for lacking it; the full trusted copy is still merged into the scan. A
missing fork point, or a malformed or unsigned file, fails closed.

MATCHING. Text is NFKC-normalised, stripped of invisible characters, casefolded,
and common Cyrillic/Greek look-alikes are mapped to Latin. Letters and digits
separated by up to eight of `` ._+-&'"`~:/|*`` (and curly quotes, dashes, bullets,
middle dots), by backslashes, by ``%20``, or by up to two line breaks with an
optional comment prefix (``#``, ``//``, ``*``, ``>``, ``--``, ``;``) form one run; separators are
dropped. So "Acme & Widgets", "ACME-WIDGETS", "acme.widgets.com", "acme/widgets"
and a name wrapped across a comment block all reduce to ``acmewidgets``. A comma,
bracket or parenthesis ends a run. Names of eight characters or fewer must start
and end on a word boundary (a separator, a run edge, a lower-to-upper case change
or a letter/digit change), so a short name does not fire inside longer words;
longer names match anywhere. Each text is also scanned with HTML/XML entities,
``\\uXXXX`` escapes and ``%XX`` decoded, and with markup tags removed (so a name
split across Word runs is caught).

WHAT IS SCANNED. Private path rules apply to archive members as well as files.
File contents (UTF-8, UTF-16, UTF-32), file paths, members and
comments of zip containers (.docx/.xlsx/.pptx/.zip), commit messages and
author/committer identities (both the raw commit object and, so a non-UTF-8
``encoding`` header is honoured, ``git log``'s re-encoded view), merge commits
against each parent, annotated tag objects (nested too) and the blob or tree a
tag points at, ref names, free text (PR, issue, comment, review and release text -- an
``issue_comment`` event scans only the comment's own fields, never the
issue's title or body, since those are the issue author's text and an
outsider's comment on someone else's issue is not an endorsement of it),
``data:`` URIs decoded and routed by their declared mime type (image as an
image, PDF as opaque, text/JSON as text; a media type may be omitted
entirely per RFC 2397, defaulting to text/plain, and may carry a
JSON-escaped slash (``\\/``) when read as plain text out of a quoted JSON
string), and Jupyter notebook cell source, outputs and attachments (nbformat
3 and 4; ``application/javascript``, any ``*+json``/``*+xml`` mime and
``application/xml`` are scanned as text like ``text/*`` and
``application/json``; any mime that matches neither the text-like nor the
binary-like routing is reported ``unscanned/opaque-file`` rather than
silently skipped). FILES THE SCANNER CANNOT READ --
PDFs, legacy Office files, images, compressed archives, nested archives, Git
LFS pointers, anything binary -- ARE BLOCKED unless a key holder has
allowlisted that exact content with ``client_guard.py allow <path>``. An
unreadable file is not a clean one. A commit, tag or blob over 25 MB, or a
``data:`` URI payload over that same bound, is reported ``unscanned/too-large``
rather than read into memory -- unless its sha is already allowlisted, in
which case it is clean without ever being read, just as it was before this
size cap existed. A notebook (``.ipynb``) that fails to parse as JSON,
including one too deeply nested for the parser's recursion limit, or whose
``cells``, ``worksheets``, an output's ``outputs``, or an attachment's
``attachments`` holds a value of some type other than the list or dict
nbformat expects there, is reported ``unscanned/bad-notebook`` instead of
silently losing its structured scan; its raw bytes still get the
plain-text scan above.

KNOWN LIMITS. Deliberate obfuscation (reversal, letter substitution outside
the look-alike table, or base64 text standing alone rather than inside a
recognised ``data:`` URI or notebook output/attachment) is not detected; the
guard is built to stop accidents, not a determined circumvention. Base64 and
JSON payloads carried inside a ``data:`` URI, or a notebook's outputs and
attachments, ARE decoded and scanned (see WHAT IS SCANNED). A pull request
can still edit the workflow file itself; review changes to
``.github/workflows/``.

OUTPUT. Rule ids and locations only, never the matched text. In CI, whose logs
are public, a location that itself contains a registered name is withheld.

Exit 0 clean, 1 on any hit or a refused registration, 2 when the scan cannot run.

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

import base64
import binascii
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
import zlib
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
# pull_request_target keeps the trusted base checkout as the workspace and never
# checks out the PR head, so the registry/allowlist the PR itself edits must be
# read as git objects at the PR's own tip instead of from the working copy.
CHANGE_ENV = "CLIENT_GUARD_CHANGE_REV"
KEY_FILE = Path.home() / ".config" / "parallax" / "client-guard.key"
KEY_CHECK_INPUT = "client-guard registry key check v2"
PREFIX_LEN = 4
BOUNDARY_MAX = 8
MAX_BLOB_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
ZERO_SHA = "0" * 40

# Every Unicode Cf (format) code point as of Unicode 16 (verified against
# unicodedata.category(c) == "Cf" over the full code point range in a one-off
# script), plus invisible combining/filler marks and variation selectors. A
# name with one of these hidden inside it still matches after stripping them.
_INVISIBLE = re.compile(
    "[\\u00ad\\u034f\\u0600-\\u0605\\u061c\\u06dd\\u070f\\u0890-\\u0891\\u08e2"
    "\\u17b4\\u17b5\\u180b-\\u180d\\u180e\\u180f\\u200b-\\u200f"
    "\\u202a-\\u202e\\u2060-\\u2064\\u2066-\\u206f\\ufe00-\\ufe0f\\ufeff"
    "\\ufff9-\\ufffb"
    "\\U000110bd\\U000110cd\\U00013430-\\U0001343f\\U0001bca0-\\U0001bca3"
    "\\U0001d173-\\U0001d17a\\U000e0001\\U000e0020-\\U000e007f\\U000e0100-\\U000e01ef]"
)
# U+115F/U+1160 (Hangul jamo fillers) and U+3164/U+FFA0 (their full/halfwidth
# syllable-block forms) render as a blank but are Unicode letters (category
# Lo), not punctuation -- stripping them like whitespace would silently erase
# the visual gap they stand for. They live in _SEP_CHARS below instead, so a
# name split across one still joins into a single run with a real boundary
# recorded at the split, rather than vanishing into a contiguous word.
_HANGUL_FILLERS = "\\u115f\\u1160\\u3164\\uffa0"
_CONFUSABLES = str.maketrans({
    "\u0430": "a", "\u0432": "b", "\u0435": "e", "\u043a": "k", "\u043c": "m",
    "\u043d": "h", "\u043e": "o", "\u0440": "p", "\u0441": "c", "\u0442": "t",
    "\u0443": "y", "\u0445": "x", "\u0455": "s", "\u0456": "i", "\u0458": "j",
    "\u0501": "d", "\u051b": "q", "\u051d": "w", "\u04cf": "l", "\u03b1": "a",
    "\u03b2": "b", "\u03b5": "e", "\u03b9": "i", "\u03ba": "k", "\u03bd": "v",
    "\u03bf": "o", "\u03c1": "p", "\u03c4": "t", "\u03c5": "u", "\u03c7": "x",
    "\u03f2": "c",
})
# U+0085 (NEL) and U+000B/U+000C (VT/FF -- VT is PowerPoint's soft line break)
# are line breaks that NFKC does not normalise away, same reasoning as
# U+2028/U+2029 below.
_NL = r"(?:\r\n|\r|\n|\u0085|\u000b|\u000c)[ \t]*(?:(?:#|//|\*|>|--|;)[ \t]*)?"
# U+2028/U+2029 (Unicode line/paragraph separator) are not \r, \n or \r\n, so
# NFKC leaves them alone and they used to split a run in two; treat them as
# the plain separators they visually are. The Hangul fillers are Unicode
# letters that render as a blank (see _HANGUL_FILLERS above); listing them
# here, and excluding them from _TOKEN/_RUN's word-character class below,
# makes them act as a separator instead of a silently-stripped no-op.
_SEP_CHARS = (" \\t\\u00a0._+\\-&'\"`~:/|*\\u2018\\u2019\\u201c\\u201d\\u00b7"
              "\\u2022\\u2212\\u2010-\\u2015\\u2028\\u2029" + r"\\" + _HANGUL_FILLERS)
_SEP = rf"(?:[{_SEP_CHARS}]{{1,8}}(?:{_NL}){{0,2}}|(?:{_NL}){{1,2}}|%20)"
# [^\W_<fillers>]: a "word" character that is not underscore and not one of
# the filler letters above, which must end a token so _SEP gets a chance to
# treat them as the separator they display as (plain [^\W_] would absorb
# them into the token, since Unicode classes them as letters).
_WORDCHAR = rf"[^\W_{_HANGUL_FILLERS}]"
_RUN = re.compile(rf"{_WORDCHAR}+(?:{_SEP}{_WORDCHAR}+)*")
_TOKEN = re.compile(rf"{_WORDCHAR}+")
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
                    r"|(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])")
_NON_ALNUM = re.compile(r"[\W_]+")
_TAG = re.compile(r"<[^<>]*>")
_UESC = re.compile(r"\\u([0-9a-fA-F]{4})")
_QP_SOFTBREAK = re.compile(r"=\r\n|=\n")
# Scripts written without spaces between words. A short registered name never
# starts or ends on a boundary inside unspaced CJK/Thai/etc. prose, so every
# offset touching one of these characters is treated as a boundary instead
# (also covering a Latin/script transition, since that offset sits right next
# to the script character). This raises false-positive risk for short names
# inside these scripts: a boundary essentially exists everywhere.
_NO_SPACE_SCRIPT = re.compile(
    "[\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\U00020000-\\U0002ebef"
    "\\U00030000-\\U0003134f\\u3040-\\u309f\\u30a0-\\u30ff\\u31f0-\\u31ff"
    "\\uff66-\\uff9f\\u0e00-\\u0e7f\\u0e80-\\u0eff\\u1780-\\u17ff\\u1000-\\u109f]"
)
_ALLOW_LINE = re.compile(r"^[0-9a-f]{40} [0-9a-f]{32}$")
_REGISTRY_KEYS = frozenset({"version", "algorithm", "normalization", "prefix_length",
                            "lengths", "prefixes", "digests", "verifier"})
_ZIP_SUFFIXES = (".docx", ".xlsx", ".pptx", ".zip", ".odt", ".ods", ".odp", ".docm", ".xlsm")
_OPAQUE_SUFFIXES = (
    ".pdf", ".doc", ".xls", ".ppt", ".rtf", ".gz", ".tgz", ".bz2", ".xz", ".7z",
    ".rar", ".tar", ".zst", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
    ".bmp", ".tif", ".tiff", ".heic", ".svg", ".svgz", ".mp3", ".mp4", ".mov",
    ".wav", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".pkl", ".parquet", ".db",
    ".sqlite", ".exe", ".dll", ".so", ".dylib", ".jar", ".class", ".wasm", ".ps",
)
_LFS_POINTER = b"version https://git-lfs.github.com/spec"
# data:<type>/<subtype>[;param=value...];base64, -- the header only, never the
# payload (RFC 2397 allows parameters before the ``;base64`` marker, e.g. a
# charset, and allows the whole media type to be omitted, defaulting to
# text/plain). Case-insensitive: both the mime name and the ``base64`` token
# are written in any case in the wild. A JSON-escaped forward slash (``\/``)
# is accepted in the media type too, since that is what survives when a
# notebook's JSON-quoted string is read as plain text rather than parsed.
# The payload itself is walked separately (see _B64_PAYLOAD_RUN) with a hard
# cap, so a multi-megabyte payload is never captured by this regex and never
# fully materialised before the cap check.
#
# Every repeated group here is bounded -- param count (``{0,8}``), param
# name length (``{1,64}``), param value length (``{0,256}``) -- so a crafted
# header like ``"data:a/b;x=" * n`` cannot make the engine backtrack past
# that fixed bound while hunting for the ``;base64,`` marker that never
# arrives. The previous unbounded ``(?:;...=[^;,]*)*`` cost quadratic time on
# exactly that input (0.9s at 22 KB, 15s at 88 KB).
_DATA_URI_HEADER = re.compile(
    r"data:(?:([A-Za-z0-9.+-]+(?:/|\\/)[A-Za-z0-9.+-]+))?"
    r"(?:;[A-Za-z0-9.+-]{1,64}=[^;,\s]{0,256}){0,8};base64,",
    re.IGNORECASE,
)
# A base64 payload behind a header the strict pattern above does not parse
# (too many parameters, an unusual media type) is reported, so it is never left
# undecoded and unreported. Consume each candidate header up to its first
# comma or whitespace, then check the suffix outside the regex. With no
# required suffix in the regex, a long header is consumed once without
# backtracking or copying it. Short payloads and wrapped payloads count;
# code templates whose payload starts with a brace do not.
_LOOSE_HEADER = re.compile(r"data:[^,\s]*", re.IGNORECASE)
_B64_START = re.compile(r"(?:\s|\\n)*[A-Za-z0-9+/]")


def _loose_data_uri_ends(text: str) -> set[int]:
    ends = set()
    for header in _LOOSE_HEADER.finditer(text):
        end = header.end()
        if (text[end:end + 1] == ","
                and text[max(header.start(), end - 7):end].lower() == ";base64"
                and _B64_START.match(text, end + 1)):
            ends.add(end + 1)
    return ends


# The payload may be wrapped across real newlines (raw HTML/Markdown) or carry
# a literal JSON `\n` escape (the same bytes read as plain text out of a
# .ipynb's quoted string); both are cleaned before decode. A PLAIN character
# class (no alternation of single-char branches) so the regex engine walks it
# in one tight loop instead of pushing a backtrack frame per character --
# the difference between a bounded scan and multi-GB memory use on a large
# payload. A stray literal backslash survives into the match (it is later
# collapsed by the `\n`-escape cleanup before base64 decoding), so this never
# needs to itself distinguish `\` followed by `n` from any other escape.
_B64_PAYLOAD_RUN = re.compile(r"[A-Za-z0-9+/=\\\s]*")

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


class RegistrationBlocked(RuntimeError):
    """``add`` found a name just being registered already sitting in the
    tracked tree or the working tree, in plaintext. Exit 1 like an ordinary
    scan hit (something for the maintainer to go fix), never 2 like a scan
    that could not run at all. Never carries scanned text."""


def _mac(key: bytes, domain: str, s: str) -> str:
    return hmac.new(key, f"{domain}:{s}".encode("utf-8"), hashlib.sha256).hexdigest()


def _fold(text: str) -> str:
    return text.casefold().translate(_CONFUSABLES)


# Combining marks (Unicode category M: Thai and Indic vowel signs, Hebrew and
# Arabic points, accents NFKC cannot compose) are not word characters to the
# regex engine, so they used to end a run in the middle of a word, while
# normalize_name dropped them from the registered form. A registered Thai or
# Devanagari name therefore never matched. Both sides now drop them. A
# translate table, built once from the BMP and SMP (every assigned mark lives
# there), is roughly ten times faster than a character class over 300 ranges.
_MARKS = {cp: None for cp in range(0x20000)
          if unicodedata.category(chr(cp)).startswith("M")}


def normalize_name(name: str) -> str:
    clean = _INVISIBLE.sub("", unicodedata.normalize("NFKC", name)).translate(_MARKS)
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
    # Quoted-printable (mail transport, some export tools) wraps long lines
    # with a trailing `=` before the break; a name split across the wrap is
    # rejoined on the original text, independent of the other decodings.
    if "=\r\n" in text or "=\n" in text:
        unwrapped = _QP_SOFTBREAK.sub("", text)
        if unwrapped != text:
            out.append(unwrapped)
    return out


def runs(text: str) -> list[tuple[str, frozenset[int]]]:
    """Joined runs, each with the offsets that are word boundaries in it."""
    clean = _INVISIBLE.sub("", unicodedata.normalize("NFKC", text))
    if not clean.isascii():
        clean = clean.translate(_MARKS)
    out = []
    for m in _RUN.finditer(clean):
        joined, bounds = [], {0}
        pos = 0
        for tok in _TOKEN.findall(m.group(0)):
            for piece in _CAMEL.split(tok):
                if not piece:
                    continue
                # No-space scripts carry no camelCase/digit transitions to
                # split on, so every offset touching one of their characters
                # is a boundary too (cheap to skip: these are never ASCII).
                # Offsets are computed on the FOLDED text, character by
                # character -- casefold can expand a character (e.g. "ß" ->
                # "ss"), so the raw character index within `piece` drifts
                # away from its actual position in the folded run the
                # moment an earlier character in the same piece expands.
                if not piece.isascii():
                    local_off = 0
                    for ch in piece:
                        ch_folded_len = len(_NON_ALNUM.sub("", _fold(ch)))
                        if _NO_SPACE_SCRIPT.match(ch):
                            bounds.add(pos + local_off)
                            bounds.add(pos + local_off + ch_folded_len)
                        local_off += ch_folded_len
                folded = _NON_ALNUM.sub("", _fold(piece))
                joined.append(folded)
                pos += len(folded)
                bounds.add(pos)
        out.append(("".join(joined), frozenset(bounds)))
    return out


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _take_payload(text: str, start: int, cap: int) -> tuple[str, bool]:
    """The base64 payload text following a data-URI header, read at most
    ``cap + 1`` characters so an oversized payload is detected -- and the
    rest of ``text`` left alone -- without ever materialising it in full.
    Matching against a slice, not the whole string, also means the payload
    is never copied beyond the bound even when the regex itself is O(n)."""
    end = min(len(text), start + cap + 1)
    m = _B64_PAYLOAD_RUN.match(text, start, end)
    length = m.end() - start
    if length > cap:
        return "", True
    return text[start:m.end()], False


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
        # Older v2 readers used the fixed prefilter width even if this field
        # was absent. Preserve that default, but never accept another width.
        prefix_length = data.get("prefix_length", PREFIX_LEN)
        if type(prefix_length) is not int or prefix_length != PREFIX_LEN:
            raise GuardError(f"registry has an incompatible prefix_length: {where}")
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
    def at_rev(cls, rev: str, optional: bool = False) -> "Registry | None":
        """The registry committed at ``rev``. ``optional`` tells a missing file
        from a malformed one: the trusted-revision caller treats an absent
        registry as an error (a push with no trusted base is not trustworthy),
        while the change-revision caller treats a ``None`` result as nothing
        to merge when the change's fork point has no registry, or as a shrink
        to nothing (rejected by its own caller) when it has one -- a malformed
        or unsigned entry still raises either way."""
        if not _object_exists(rev):
            raise GuardError(f"revision {rev[:12]} is not available")
        if optional:
            entry = _git("ls-tree", "-z", rev, "--", REGISTRY_REL)
            if entry.returncode != 0:
                raise GuardError(f"cannot read registry tree at {rev[:12]}")
            if not entry.stdout:
                return None  # the readable tree confirms that the path is absent
        res = _git("show", f"{rev}:{REGISTRY_REL}")
        if res.returncode != 0:
            raise GuardError(f"registry unreadable at {rev[:12]}")
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
        self._scan_embedded_images(text, where, context, depth)
        if lowered.endswith(".ipynb"):
            self._scan_ipynb(text, where, context, depth)

    @staticmethod
    def _embedded_ext(subtype: str) -> str:
        subtype = subtype.lower()
        if subtype in ("svg+xml", "svg"):
            return ".svg"
        if subtype == "jpeg":
            return ".jpg"
        safe = re.sub(r"[^a-z0-9]", "", subtype)
        return f".{safe}" if safe else ".bin"

    def _scan_data_uri_payload(self, mime: str, raw_payload: str, where: str,
                               context: str, depth: int) -> None:
        """One data-URI payload (always base64, per the ``;base64,`` marker
        that got it here) routed by its declared mime type through scan_bytes
        with a synthetic path, so the opaque-file rule and the blob-sha
        allowlist apply to it exactly as to a real file."""
        if not raw_payload:
            return  # an empty payload is not an embedding worth scanning
        mime_l = mime.lower()
        mtype, _, subtype = mime_l.partition("/")
        label = "(embedded image)" if mtype == "image" else "(embedded data)"
        if depth:
            # A second level of embedding (an archive member's own text holds
            # one, or an already-decoded embedded payload holds another) is
            # refused rather than expanded without limit; fail closed like any
            # other nested-archive case.
            self.report("unscanned/nested-archive", f"{where} {label}", context or where)
            return
        # The payload may carry a literal JSON `\n` escape (two characters,
        # backslash then "n") when it was read as raw text out of a quoted
        # JSON string rather than parsed, plus ordinary whitespace either way.
        cleaned = re.sub(r"\\n|\s+", "", raw_payload)
        if not cleaned:
            return  # an empty payload is not an embedding worth scanning
        try:
            decoded = base64.b64decode(cleaned, validate=True)
        except (binascii.Error, ValueError):
            self.report("unscanned/bad-embedded-image", f"{where} {label}", context or where)
            return
        if subtype in ("svg+xml", "svg"):
            # Decode first -- hashing the base64 TEXT instead of the decoded
            # bytes (the old bug here) means the blob-sha allowlist can never
            # match a reviewed SVG's real content.
            self.scan_bytes(decoded, "embedded.svg", f"{where} {label}",
                            context or where, depth=depth + 1)
        elif mtype == "image":
            ext = self._embedded_ext(subtype)
            self.scan_bytes(decoded, f"embedded{ext}", f"{where} {label}",
                            context or where, depth=depth + 1)
        elif mime_l == "application/pdf":
            self.scan_bytes(decoded, "embedded.pdf", f"{where} {label}",
                            context or where, depth=depth + 1)
        elif mtype == "text" or mime_l in ("application/json", "application/xml"):
            self.scan_bytes(decoded, "embedded.txt", f"{where} {label}",
                            context or where, depth=depth + 1)
        else:
            self.scan_bytes(decoded, "embedded.bin", f"{where} {label}",
                            context or where, depth=depth + 1)

    def _scan_embedded_images(self, text: str, where: str, context: str, depth: int) -> None:
        strict = {m.end() for m in _DATA_URI_HEADER.finditer(text)}
        if _loose_data_uri_ends(text) - strict:
            self.report("unscanned/bad-embedded-image", f"{where} (embedded data)",
                        context or where)
        for m in _DATA_URI_HEADER.finditer(text):
            payload, too_large = _take_payload(text, m.end(), MAX_BLOB_BYTES)
            if too_large:
                self.report("unscanned/too-large", f"{where} (embedded data)", context or where)
                continue
            # RFC 2397: an omitted media type (``data:;base64,...``) defaults
            # to text/plain. A JSON-escaped slash in the captured type (read
            # as plain text out of a quoted JSON string) is normalised back
            # to a plain one before it is partitioned on "/" downstream.
            mime = (m.group(1) or "text/plain").replace("\\/", "/")
            self._scan_data_uri_payload(mime, payload, where, context, depth)

    def _scan_ipynb_mime_value(self, mime: str, value: object, where: str,
                               context: str, depth: int) -> None:
        """One output/attachment mime value. ``nbformat`` stores the
        text-representable kinds (``text/*``, ``application/json``, and --
        despite the ``image/`` mime -- ``image/svg+xml``) as native JSON text,
        never base64; only genuinely binary kinds (other ``image/*``,
        ``application/pdf``) are base64, the same contract as a data URI.
        ``application/javascript`` and any ``*+json``/``*+xml`` mime (e.g.
        ``application/vnd.plotly.v1+json``) are native JSON text too. Any
        mime matching none of those is reported ``unscanned/opaque-file``
        rather than silently skipped -- nbformat does not enumerate every
        mime a renderer may store, and an unrecognised one is not a reason
        to let its content pass unscanned."""
        mime_l = mime.lower()
        if mime_l in ("image/svg+xml", "image/svg") or mime_l.startswith("text/") \
                or mime_l in ("application/json", "application/javascript", "application/xml") \
                or mime_l.endswith(("+json", "+xml")):
            if isinstance(value, list):
                joined = "".join(v for v in value if isinstance(v, str))
            elif isinstance(value, str):
                joined = value
            else:
                joined = json.dumps(value) if value is not None else ""
            if not joined:
                return
            if mime_l in ("image/svg+xml", "image/svg"):
                self.scan_bytes(joined.encode("utf-8", "replace"), "embedded.svg",
                                f"{where} (embedded image)", context or where, depth=depth + 1)
            else:
                self.scan_text(joined, where, context)
                # A data URI wrapped across list entries only exists joined.
                self._scan_embedded_images(joined, where, context, depth)
            return
        if mime_l.startswith("image/") or mime_l == "application/pdf":
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                raw = "".join(value)
            elif isinstance(value, str):
                raw = value
            else:
                self.report("unscanned/bad-notebook", where, context)
                return
            if raw:
                self._scan_data_uri_payload(mime, raw, where, context, depth)
            return
        self.report("unscanned/opaque-file", where, context)

    # nbformat 3's short output keys, carried at the output's own top level
    # instead of nested under a "data" dict as nbformat 4 does.
    _V3_OUTPUT_MIME = {
        "text": "text/plain", "html": "text/html", "svg": "image/svg+xml",
        "png": "image/png", "jpeg": "image/jpeg", "json": "application/json",
        "pdf": "application/pdf", "latex": "text/latex",
        "javascript": "application/javascript",
    }

    def _typed(self, value: object, expected: type, where: str, context: str) -> object | None:
        """``value`` unchanged when it is absent (``None``) or already of the
        ``expected`` shape (``list`` or ``dict``); otherwise a malformed
        notebook structure that must be reported loudly
        (``unscanned/bad-notebook``) rather than silently losing the
        structured scan the caller was about to run over it -- e.g. a
        dict-shaped ``outputs`` or ``cells`` where nbformat always writes a
        list."""
        if value is None or isinstance(value, expected):
            return value
        self.report("unscanned/bad-notebook", where, context)
        return None

    def _scan_ipynb(self, text: str, where: str, context: str, depth: int) -> None:
        """Cell source (joined so a name split across source lines is caught),
        output and attachment payloads -- across both nbformat 4 (``cells``,
        output mimes nested under ``data``) and nbformat 3 (``worksheets``
        wrapping ``cells``, and output mimes as short keys at the output's own
        level). A malformed notebook already got the plain-text scan above;
        that is not a new failure here, but it is still reported as
        ``unscanned/bad-notebook`` rather than silently losing the structured
        scan. ``parse_int``/``parse_float`` are forced to ``str`` so a huge
        numeric literal never trips Python's integer-string-conversion limit
        (a ``ValueError`` indistinguishable, to this scan, from genuinely
        malformed JSON); a notebook nested deep enough to exhaust the parser's
        recursion limit raises ``RecursionError`` rather than ``ValueError``
        and is caught the same way."""
        try:
            notebook = json.loads(text, parse_int=str, parse_float=str)
        except (ValueError, RecursionError):
            self.report("unscanned/bad-notebook", where, context)
            return
        if not isinstance(notebook, dict):
            self.report("unscanned/bad-notebook", where, context)
            return
        cells = list(self._typed(notebook.get("cells"), list, where, context) or [])
        worksheets = self._typed(notebook.get("worksheets"), list, where, context) or []
        for ws in worksheets:
            if isinstance(ws, dict):
                cells.extend(self._typed(ws.get("cells"), list, where, context) or [])
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            source = cell.get("source")
            if source is None:
                source = cell.get("input")  # nbformat 3 code cells
            if isinstance(source, list):
                joined_source = "".join(s for s in source if isinstance(s, str))
            elif isinstance(source, str):
                joined_source = source
            else:
                joined_source = ""
            if joined_source:
                self.scan_text(joined_source, where, context)
                self._scan_embedded_images(joined_source, where, context, depth)
            outputs = self._typed(cell.get("outputs"), list, where, context) or []
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                data = self._typed(output.get("data"), dict, where, context)
                if isinstance(data, dict):
                    for mime, value in data.items():
                        self._scan_ipynb_mime_value(mime, value, where, context, depth)
                else:
                    for short_key, mime in self._V3_OUTPUT_MIME.items():
                        if short_key in output:
                            self._scan_ipynb_mime_value(mime, output[short_key],
                                                        where, context, depth)
            attachments = self._typed(cell.get("attachments"), dict, where, context)
            if attachments:
                for mimes in attachments.values():
                    if not isinstance(mimes, dict):
                        continue
                    for mime, value in mimes.items():
                        self._scan_ipynb_mime_value(mime, value, where, context, depth)

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
                    self.scan_path(m.filename, inner, context or where)
                    if m.comment:
                        self.scan_text(m.comment.decode("utf-8", "replace"), inner,
                                       context or where)
                    if not m.is_dir():
                        self.scan_bytes(zf.read(m), m.filename, inner, context or where, depth=1)
        # zlib.error surfaces unwrapped from ZipFile.read() on a corrupt
        # deflate stream (a bad CRC or a truncated local header raises
        # BadZipFile instead; both are a reason to fail closed, not to crash).
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, ValueError, zlib.error):
            self.report("unscanned/bad-archive", where, context)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                          capture_output=True, text=True, errors="replace")


def _discard(stream, size: int, chunk: int = 1 << 20) -> None:
    """Consume exactly ``size`` bytes from ``stream`` without retaining them,
    in bounded chunks -- the oversized-body counterpart of a normal read."""
    remaining = size
    while remaining > 0:
        got = stream.read(min(chunk, remaining))
        if not got:
            raise GuardError("object body truncated while discarding")
        remaining -= len(got)


def _cat_blobs(shas: list[str]) -> dict[str, bytes | None]:
    """Read many objects through one ``git cat-file --batch``. Every header's body
    is consumed whatever its type, and a missing object or a failed process is an
    error, never a silent skip. A blob body over ``MAX_BLOB_BYTES`` is read and
    discarded in chunks rather than held in memory; its map entry is ``None``,
    which the caller reports as ``unscanned/too-large`` instead of scanning --
    unless the sha is already allowlisted (see ``_report_oversized``), since
    its body is never read into memory to run the normal scan_bytes allowlist
    check against."""
    out: dict[str, bytes | None] = {}
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
            if size > MAX_BLOB_BYTES:
                _discard(proc.stdout, size)
                proc.stdout.read(1)
                if header[1] == b"blob":
                    out[sha] = None
                continue
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


def _file_blob_sha(path: Path) -> str:
    """git's blob sha of a file, streamed, so an oversized file is never held
    in memory just to check it against the allowlist."""
    h = hashlib.sha1(b"blob %d\0" % path.stat().st_size)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _report_oversized(scanner: "Scanner", sha: str, where: str, context: str) -> None:
    """A blob ``_cat_blobs`` discarded for being over ``MAX_BLOB_BYTES`` (its
    map entry is ``None``). Its body was never read into memory, so it never
    ran through scan_bytes's own allowlist check at the top; check the sha
    here instead, so a key holder's reviewed oversized binary stays clean."""
    if sha not in scanner.allowed:
        scanner.report("unscanned/too-large", where, context)


def _object_exists(rev: str) -> bool:
    return _git("cat-file", "-e", f"{rev}^{{object}}").returncode == 0


def _object_size(rev: str) -> int:
    res = _git("cat-file", "-s", rev)
    if res.returncode != 0:
        raise GuardError(f"object {rev[:12]} could not be read")
    return int(res.stdout.strip())


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
        where = f"{rev}:{path}"
        data = blobs[sha]
        if data is None:
            _report_oversized(scanner, sha, where, ctx)
        else:
            scanner.scan_bytes(data, path, where, ctx)


def _positive_revs(revs: list[str]) -> list[str]:
    out = []
    for rev in revs:
        if rev.startswith("^"):
            continue
        if "..." in rev:
            raise GuardError(f"symmetric range {rev!r} is not supported; use A..B")
        out.append(rev.split("..", 1)[1] if ".." in rev else rev)
    return [r for r in out if r]


# The `tree <sha>` line, every `parent <sha>` line, and a mergetag's own
# `mergetag object <sha>` line, each exactly a 40-hex-digit object id with
# nothing else on the line -- never a message a human wrote.
_COMMIT_HEADER_HEX_LINE = re.compile(r"^(?:tree|parent) [0-9a-f]{40}$"
                                     r"|^mergetag object [0-9a-f]{40}$")


def _commit_text_for_scan(raw: str) -> str:
    """The raw commit object (``git cat-file commit <sha>``) with its pure-hex
    header lines dropped, so an object id never feeds the name matcher. Author,
    committer, gpgsig and mergetag content survive -- ``%B`` alone never carried
    a mergetag's tag message (the text a merged, tagged branch brings along),
    so a name riding only there went unscanned. The hex lines are only ever
    looked for ahead of the blank line that separates headers from the message,
    so a message that happens to read like one is never dropped."""
    lines = raw.split("\n")
    try:
        header_end = lines.index("")
    except ValueError:
        header_end = len(lines)
    header = [ln for ln in lines[:header_end] if not _COMMIT_HEADER_HEX_LINE.match(ln)]
    return "\n".join(header + lines[header_end:])


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
            data = _cat_blobs([rev])[rev]
            if data is None:
                _report_oversized(scanner, rev, where, "tag")
            else:
                scanner.scan_bytes(data, "", where, "tag")
            return
        if obj == "tree":
            scan_tree(scanner, rev)
            return
        if obj != "tag":
            return
        tag_where = f"tag object {rev[:12]}"
        if _object_size(rev) > MAX_BLOB_BYTES:
            # Cannot safely parse the `object <sha>` line either, since that
            # would mean reading the oversized body first; stop the chain
            # here rather than materialise it.
            scanner.report("unscanned/too-large", tag_where, "tag")
            return
        body = _git("cat-file", "-p", rev)
        if body.returncode != 0:
            raise GuardError(f"cannot read tag {rev[:12]}")
        scanner.scan_text(body.stdout, tag_where, "tag")
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
        where = f"{ctx} message or identity"
        if _object_size(sha) > MAX_BLOB_BYTES:
            scanner.report("unscanned/too-large", where, ctx)
        else:
            obj = _git("cat-file", "commit", sha)
            if obj.returncode != 0:
                raise GuardError(f"cannot read {ctx}")
            scanner.scan_text(_commit_text_for_scan(obj.stdout), where, ctx)
            # `cat-file commit` prints the raw object bytes, so a non-UTF-8
            # `encoding` header (e.g. ISO-8859-1) is read with errors=replace
            # and a name split across a multi-byte sequence is garbled. `git
            # log` honours that header and re-encodes to UTF-8 for display,
            # so the same commit is scanned a second way to catch what the
            # raw bytes miss; same `where` label, so a hit from either path
            # dedups to one line of output.
            log = _git("log", "-1", "--format=%an%n%ae%n%cn%n%ce%n%B", sha)
            if log.returncode != 0:
                raise GuardError(f"cannot read {ctx} via git log")
            scanner.scan_text(log.stdout, where, ctx)
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
            blob_where = f"{ctx}:{path}"
            data = blobs[blob_sha]
            if data is None:
                _report_oversized(scanner, blob_sha, blob_where, ctx)
            else:
                scanner.scan_bytes(data, path, blob_where, ctx)
    return len(commits)


def scan_dir(scanner: Scanner, root: Path) -> None:
    if not root.is_dir():
        raise GuardError(f"not a directory: {root}")
    for p in sorted(root.rglob("*")):
        parts = p.relative_to(root).parts
        if _SKIP_DIRS.intersection(parts):
            continue
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            # A symlink can point at a client-named path or at an unreadable
            # file outside the tree; judge the link itself, never the target.
            scanner.scan_path(rel, rel, "directory")
            scanner.scan_text(os.readlink(p), rel, "directory")
            continue
        if not p.is_file():
            continue
        scanner.scan_path(rel, rel, "directory")
        if p.stat().st_size > MAX_BLOB_BYTES:
            _report_oversized(scanner, _file_blob_sha(p), rel, "directory")
            continue
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
        # issue_comment carries both "comment" (the text someone just posted)
        # and "issue" (the issue it was posted on, written by whoever opened
        # that issue -- possibly an outsider the comment author has no
        # relation to). The dedicated "issues" event covers an issue's own
        # title/body on its own trigger; scanning it again here, keyed off a
        # comment event, would scan an outsider's text under the wrong event.
        objs = ("comment",) if event_name == "issue_comment" \
            else ("issue", "comment", "review", "release", "discussion")
        found = False
        for obj in objs:
            item = event.get(obj)
            if isinstance(item, dict):
                found = True
                for key in _TEXT_EVENT_FIELDS:
                    value = item.get(key)
                    if isinstance(value, str) and value:
                        scanner.scan_text(value, f"{event_name} {obj} {key}", event_name)
        if not found:
            raise GuardError(f"unsupported event {event_name!r}")


_UNJOINED = re.compile(rf"[^\w{_SEP_CHARS}]")


def _scan_worktree_paths(scanner: "Scanner", context: str) -> None:
    """The working tree's tracked and untracked-not-ignored files, read from
    disk by path, so a name sitting only in a not-yet-committed file is
    caught. A symlink's path and target string are scanned without following
    it. Any git or read failure raises: ``add`` must not register a name on
    the strength of a scan that did not run."""
    res = _git("ls-files", "-co", "-z", "--exclude-standard")
    if res.returncode != 0:
        raise GuardError("cannot list the working tree before registering")
    for rel in res.stdout.split("\0"):
        if not rel:
            continue
        p = REPO_ROOT / rel
        if p.is_symlink():
            scanner.scan_path(rel, rel, context)
            scanner.scan_text(os.readlink(p), f"{rel} (symlink target)", context)
            continue
        if not p.is_file():
            continue
        scanner.scan_path(rel, rel, context)
        try:
            if p.stat().st_size > MAX_BLOB_BYTES:
                _report_oversized(scanner, _file_blob_sha(p), rel, context)
                continue
            data = p.read_bytes()
        except OSError:
            raise GuardError(f"cannot read a working-tree file before registering: {rel}") from None
        scanner.scan_bytes(data, rel, rel, context)


def _scan_index(scanner: "Scanner", context: str) -> None:
    """Staged content: a change added to the index and then reverted in the
    working tree is still what the next commit publishes."""
    res = _git("ls-files", "-s", "-z")
    if res.returncode != 0:
        raise GuardError("cannot read the index before registering")
    entries = []
    for rec in res.stdout.split("\0"):
        if not rec:
            continue
        meta, path = rec.split("\t", 1)
        mode, sha, _stage = meta.split()
        scanner.scan_path(path, f"index:{path}", context)
        if mode != "160000":
            entries.append((sha, path))
    blobs = _cat_blobs(sorted({sha for sha, _ in entries}))
    for sha, path in entries:
        where = f"index:{path}"
        if blobs.get(sha) is None:
            _report_oversized(scanner, sha, where, context)
            continue
        scanner.scan_bytes(blobs[sha], path, where, context)


def _public_name_hits(key: bytes, reg: "Registry") -> set[tuple[str, str]]:
    """Every ``client/name`` / ``client/name-in-path`` hit this registry
    finds in what CI will scan when the registry is pushed: HEAD's tree,
    the commits not yet on ``origin/main`` (all of history when there is no
    such ref), the index and the working tree. An empty registry (the very
    first ``add``) has nothing to match and is skipped. Not being inside a
    git repository is an error, never a clean scan."""
    if not reg.lengths:
        return set()
    if _git("rev-parse", "--git-dir").returncode != 0:
        raise GuardError(f"{REPO_ROOT} is not a git repository git can read; "
                         "cannot check the tree before registering")
    scanner = Scanner(key, reg)
    if _git("rev-parse", "--verify", "-q", "HEAD^{commit}").returncode == 0:
        scan_tree(scanner, "HEAD")
        published = "refs/remotes/origin/main"
        if _object_exists(published):
            scan_range(scanner, ["HEAD", f"^{published}"])
        else:
            scan_range(scanner, ["HEAD"])
    _scan_index(scanner, "index")
    _scan_worktree_paths(scanner, "working tree")
    return {(rule, where) for rule, where in scanner.hits
            if rule in ("client/name", "client/name-in-path")}


def _registration_conflicts(key: bytes, old_registry: "Registry",
                            new_registry: "Registry") -> list[tuple[str, str]]:
    """Hits that the names just being added cause -- present under
    ``new_registry`` but not under ``old_registry`` (the registry as it
    stood immediately before this ``add``). A hit already there under an
    EXISTING registered name is not this check's job to raise again; only
    genuinely new public exposure blocks the write."""
    return sorted(_public_name_hits(key, new_registry) - _public_name_hits(key, old_registry))


def add_names(key: bytes, names: list[str], path: Path | None = None) -> int:
    if not names:
        raise GuardError("no names given on stdin; nothing to register")
    path = REGISTRY_PATH if path is None else path
    check = _mac(key, "check", KEY_CHECK_INPUT)
    if path.exists():
        reg = Registry.load(path)
        reg.verify(key)
    else:
        reg = Registry(key_check=check)
    old_registry = reg
    digests, prefixes, lengths = set(reg.digests), set(reg.prefixes), set(reg.lengths)
    before = len(digests)
    for name in names:
        norm = normalize_name(name)
        if len(norm) < PREFIX_LEN:
            raise GuardError(f"a name normalises to fewer than {PREFIX_LEN} letters/digits; "
                             "too short to match without false positives")
        if _UNJOINED.search(name.translate(_MARKS)):
            print("  ! a name contains punctuation that ends a run in text (such as a "
                  "comma); also register the forms it is written in without it",
                  file=sys.stderr)
        digests.add(_mac(key, "name", norm))
        prefixes.add(_mac(key, "prefix", norm[:PREFIX_LEN]))
        lengths.add(len(norm))
    new_registry = Registry(frozenset(digests), frozenset(prefixes), tuple(sorted(lengths)), check)
    conflicts = _registration_conflicts(key, old_registry, new_registry)
    if conflicts:
        # Local and key-holder only: unlike CI, the locations are printed,
        # including a path that itself contains the name being registered.
        print("  ! refusing to register: the new name(s) already appear in this "
              "repository's history, index or working copy; remove them first, "
              "then retry:", file=sys.stderr)
        for rule, where in conflicts:
            print(f"      [{rule}] {where}", file=sys.stderr)
        raise RegistrationBlocked(
            "new name(s) already present in the tracked tree or working copy; "
            "registry not written")
    new_registry.save(path)
    return len(digests) - before


def allow_files(key: bytes, paths: list[str]) -> int:
    if REGISTRY_PATH.exists():
        Registry.load().verify(key)  # a wrong key would sign entries every scan rejects
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
    committed at the trusted revision when one is set, and with the copies at
    the change revision when that is set too (CI under ``pull_request_target``
    checks out the trusted base as the workspace and never the PR head, so the
    PR's own registry/allowlist edits must be read as git objects at its tip
    instead). A change revision requires a trusted revision. Every registry
    found must verify against the key; a file simply absent at the change
    revision is skipped, not an error -- except the
    registry itself when the change's fork point from the trusted revision has
    one: deleting it outright is a shrink to nothing and is rejected the same
    way a partial shrink is."""
    trusted = os.environ.get(TRUSTED_ENV, "").strip()
    change = os.environ.get(CHANGE_ENV, "").strip()
    if change and not trusted:
        raise GuardError("change revision requires a trusted revision")
    registries, allowed = [], set()
    if REGISTRY_PATH.exists():
        registries.append(Registry.load())
    if ALLOW_PATH.exists():
        allowed |= parse_allowlist(key, ALLOW_PATH.read_text(encoding="utf-8"), ALLOW_REL)
    trusted_registry: Registry | None = None
    if trusted:
        trusted_registry = Registry.at_rev(trusted)
        registries.append(trusted_registry)
        res = _git("show", f"{trusted}:{ALLOW_REL}")
        if res.returncode == 0:
            allowed |= parse_allowlist(key, res.stdout, f"{trusted[:12]}:{ALLOW_REL}")
    change_registry: Registry | None = None
    base_registry: Registry | None = None
    if change:
        change_registry = Registry.at_rev(change, optional=True)
        if trusted_registry is not None:
            res = _git("merge-base", trusted, change)
            if res.returncode != 0 or not res.stdout.strip():
                raise GuardError(f"no common ancestor of {trusted[:12]} and {change[:12]}; "
                                 "cannot check the change for registry removals")
            base_registry = Registry.at_rev(res.stdout.strip(), optional=True)
        if change_registry is not None:
            registries.append(change_registry)
        elif base_registry is not None:
            # The PR's own tip has no registry file at all. Treating that as
            # "nothing to merge" (the ordinary optional-file case) would let
            # a PR delete the registry outright to dodge the shrink check
            # just below -- a deletion is a shrink to nothing and needs a
            # key holder exactly like dropping some of its entries does.
            raise GuardError(
                "the change deletes the registry; removal needs a key holder (see CONTRIBUTING.md)")
        res = _git("show", f"{change}:{ALLOW_REL}")
        if res.returncode == 0:
            allowed |= parse_allowlist(key, res.stdout, f"{change[:12]}:{ALLOW_REL}")
    if not registries:
        raise GuardError(f"registry not found: {REGISTRY_PATH}")
    for reg in registries:
        reg.verify(key)
    # A pull_request_target run reads the PR's own registry edits only via
    # CLIENT_GUARD_CHANGE_REV (see the docstring above); the PR that edits it
    # can otherwise drop an entry from the copy it is itself judged by. The
    # change copy must be a superset of the one at its fork point, or a
    # removal there silently widens what that same PR is allowed to publish.
    # Names registered on the trusted side after the fork are not the PR's
    # removal, and stay in the scan through the trusted copy merged above.
    if base_registry is not None and change_registry is not None:
        if not (base_registry.digests <= change_registry.digests
                and base_registry.prefixes <= change_registry.prefixes):
            raise GuardError("the change removes registered names; removal needs a key holder "
                             "(see CONTRIBUTING.md)")
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
    except RegistrationBlocked as exc:
        # add_names already printed the locations itself (a local maintainer
        # command, unlike every other command here); exit 1 like an ordinary
        # scan hit, not 2 -- the scan ran fine, it just found something.
        print(f"[client-guard] BLOCKED: {exc}", file=sys.stderr)
        return 1
    except GuardError as exc:
        print(f"[client-guard] FAIL: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - any crash must block, never pass
        print(f"[client-guard] FAIL: unexpected {type(exc).__name__}", file=sys.stderr)
        return 2
    if scanner.hits:
        deduped = sorted(set(scanner.hits))
        for rule, where in deduped:
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
