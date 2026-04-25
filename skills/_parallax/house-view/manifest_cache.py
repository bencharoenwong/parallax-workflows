#!/usr/bin/env python3
"""Calibration manifest on-disk cache + load orchestrator (Batch 3.5).

Layered on top of `manifest_verify.py`. This module owns:

  - Disk I/O: read / atomic-write of cached manifests under the cache
    directory (default `~/.parallax/calibration/`), with file-mode 0600
    and parent-dir mode 0700 enforced at write time AND verified at every
    read (security audit B-1, schema spec §7.1 + §7.2 step 3).

  - Expiry boundary: strict `manifest_expires_at <= now()` rejects, per
    schema spec §6.2 step 5 / §7.3 (security audit NEW-4).

  - Monotonicity: rejects any incoming manifest whose `calibration_version`
    is strictly less than the highest already-accepted version for the
    same `org_id` — prevents rollback attacks (schema spec §6.2 step 6).

  - A-3 dead-state guard: if the fresh manifest's signing_key_id is not
    in trusted_keys.json AND the cached manifest for the same
    `(org_id, current_calibration_version)` is also expired, the
    orchestrator hard-errors `DeadStateNoFallback` (security audit A-3,
    schema spec §6.2 step 2 dead-state guard).

  - `load_manifest()` orchestrator: composes verify + expiry +
    monotonicity + cache fallback into a single call. The intended
    integration point for load-house-view consumer skills.

What this module does NOT do (deferred):
  - HTTP fetch from the endpoint. Caller passes a pre-fetched manifest
    dict (or `None` to force cache-only). HTTP wiring lands when Batch 2
    server is available — until then, callers can stub by reading a
    fresh manifest off disk.
  - Session pinning of `version=latest` (schema spec §7.5). The orches-
    trator returns the resolved calibration_version; callers cache that
    in their session state.
  - Concurrent-safety: the atomic write is process-safe (rename is atomic
    on POSIX) but no inter-process locking. Two parallel writes of the
    same `(org_id, cv)` pair race the rename; whoever loses gets clobbered
    by the winner. Both produce identical bytes when both verified, so
    the race is benign in practice. Document if it ever bites.
"""
from __future__ import annotations

import json
import logging
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running this module directly: add the parent (house-view/) to
# path so `import manifest_verify` resolves when invoked as a script
# from outside the directory.
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import manifest_verify  # noqa: E402

logger = logging.getLogger(__name__)


DEFAULT_CACHE_DIR = Path.home() / ".parallax" / "calibration"

# Permission rules from schema spec §7.1 + §7.2 step 3 (security audit B-1).
_FILE_MODE = 0o600
_DIR_MODE = 0o700
# Mask for "broader than 0600" check on file mode. Any bit outside owner
# rw makes the file "unsafe" per the spec.
_FILE_MODE_MASK = 0o777 & ~_FILE_MODE  # bits that must be zero
_DIR_MODE_MASK = 0o777 & ~_DIR_MODE


# --- Error hierarchy --------------------------------------------------

class ManifestCacheError(Exception):
    error_code: str = "manifest_cache_error"


class ManifestExpired(ManifestCacheError):
    """`manifest_expires_at <= now()` (boundary inclusive per schema §6.2 step 5).

    Distinct from KeyIdExpired: that's about the signing key being out of
    its validity window; this is about the manifest content's stated
    expiry. A manifest can have an unexpired signing key but be expired
    itself, or vice versa.
    """
    error_code = "manifest_expired"


class MonotonicityViolation(ManifestCacheError):
    """Incoming `calibration_version` is strictly less than a previously-
    accepted version for the same `org_id`. Rollback attempt — refuse.
    """
    error_code = "monotonicity_violation"


class DeadStateNoFallback(ManifestCacheError):
    """A-3 dead-state: fresh manifest has unknown signing_key_id AND
    cached manifest is also expired (or absent). No valid manifest
    available; skill update required to proceed.
    """
    error_code = "key_id_unknown_no_fallback"


class CacheCorrupt(ManifestCacheError):
    """Cached file exists but is unreadable / fails verification on
    re-read. Cache integrity broken; treat as cache miss for fallback
    decisions.
    """
    error_code = "cache_corrupt"


# --- Helpers ----------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso8601(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _cache_filename(org_id: str, calibration_version: str) -> str:
    """Per schema spec §7.1: `<org_id>_<calibration_version>.json`."""
    # Defensive: reject path-traversal characters before they reach the
    # filesystem. The spec's identifiers are already constrained
    # (org_id is a URL-safe slug, calibration_version is a semver-ish
    # token), so anything weirder is a programmer error or an attack.
    for label, value in (("org_id", org_id), ("calibration_version", calibration_version)):
        if not value or "/" in value or "\\" in value or value.startswith(".") or "\x00" in value:
            raise ManifestCacheError(
                f"unsafe {label}={value!r} would escape cache directory"
            )
    return f"{org_id}_{calibration_version}.json"


def check_expiry(manifest: dict[str, Any], now: datetime | None = None) -> None:
    """Raise ManifestExpired if `manifest_expires_at <= now()`.

    Boundary inclusive per schema spec §6.2 step 5: a manifest with
    `manifest_expires_at == now()` is rejected. The emergency-rotation
    re-sign path uses `manifest_expires_at = now()` to force immediate
    re-fetch, so accepting at-the-boundary would defeat that.
    """
    expires_s = manifest.get("manifest_expires_at")
    if not isinstance(expires_s, str):
        raise manifest_verify.ManifestMalformed(
            "manifest missing required field `manifest_expires_at`"
        )
    expires_at = _parse_iso8601(expires_s)
    effective_now = now if now is not None else _utcnow()
    if expires_at <= effective_now:
        raise ManifestExpired(
            f"manifest_expires_at={expires_s} <= now={effective_now.isoformat()}; "
            "reject and re-fetch"
        )


# --- Cache class ------------------------------------------------------

class ManifestCache:
    """On-disk cache for verified calibration manifests.

    Reads return None on cache miss (use `get`) or raise CacheCorrupt
    when the file exists but is unparseable / unverifiable. Writes are
    atomic via rename-from-tempfile in the same directory.

    Permissions: every write applies 0600 (file) and 0700 (directory).
    Every read verifies the same and emits a warning via the module
    logger if either is broader.
    """

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        trusted_keys_path: Path | str | None = None,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
        if trusted_keys_path is None:
            trusted_keys_path = _HERE / "signing" / "trusted_keys.json"
        self.trusted_keys_path = Path(trusted_keys_path)

    # ----- Permission helpers -----

    def _ensure_dir(self) -> None:
        """Create the cache dir if missing; set mode 0700 either way."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.cache_dir, _DIR_MODE)
        except OSError as e:
            logger.warning(
                "cache_permissions_unsafe: cannot chmod %s to 0%o: %s",
                self.cache_dir, _DIR_MODE, e,
            )

    def _check_perms(self, path: Path) -> None:
        """Emit `cache_permissions_unsafe` warnings if file or parent dir
        is broader than the spec's mode. Never raises — the warning is
        the contract per security audit B-1, since a hard-fail on a
        misconfigured machine would be worse than degraded operation.
        """
        try:
            file_mode = stat.S_IMODE(path.stat().st_mode)
        except OSError as e:
            logger.warning(
                "cache_permissions_unsafe: cannot stat %s: %s", path, e
            )
            return
        if file_mode & _FILE_MODE_MASK:
            logger.warning(
                "cache_permissions_unsafe: %s mode 0%o exceeds 0%o — "
                "chmod recommended.",
                path, file_mode, _FILE_MODE,
            )
        try:
            dir_mode = stat.S_IMODE(self.cache_dir.stat().st_mode)
        except OSError:
            return
        if dir_mode & _DIR_MODE_MASK:
            logger.warning(
                "cache_permissions_unsafe: %s mode 0%o exceeds 0%o — "
                "chmod recommended.",
                self.cache_dir, dir_mode, _DIR_MODE,
            )

    # ----- Core ops -----

    def path_for(self, org_id: str, calibration_version: str) -> Path:
        return self.cache_dir / _cache_filename(org_id, calibration_version)

    def get(
        self,
        org_id: str,
        calibration_version: str,
        *,
        verify: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Return the cached manifest dict, or None on cache miss.

        Re-verifies the signature on read (defense-in-depth: a tampered
        cache file should not survive a load even if verification was
        clean at write time). Emits cache_permissions_unsafe warnings if
        the on-disk perms drifted broader than 0600/0700.
        """
        path = self.path_for(org_id, calibration_version)
        if not path.exists():
            return None
        self._check_perms(path)
        try:
            raw = path.read_text()
            manifest = json.loads(raw)
        except (OSError, json.JSONDecodeError) as e:
            raise CacheCorrupt(f"cannot read {path}: {e}") from e
        if verify:
            try:
                manifest_verify.verify_manifest(
                    manifest, self.trusted_keys_path, now=now
                )
            except manifest_verify.ManifestVerificationError as e:
                raise CacheCorrupt(
                    f"{path} failed re-verification: [{e.error_code}] {e}"
                ) from e
        return manifest

    def put(self, manifest: dict[str, Any]) -> Path:
        """Atomic write of a verified manifest to the cache.

        Caller's responsibility to verify before calling put — this
        method does NOT verify (the orchestrator does, then writes).
        Writes via tempfile + rename so partial writes never expose a
        truncated cache file.
        """
        org_id = manifest.get("org_id")
        cv = manifest.get("calibration_version")
        if not isinstance(org_id, str) or not isinstance(cv, str):
            raise manifest_verify.ManifestMalformed(
                "manifest missing org_id or calibration_version; cannot cache"
            )
        self._ensure_dir()
        dest = self.path_for(org_id, cv)
        # Write to a temp file in the same directory, then rename — keeps
        # the rename atomic on POSIX. mkstemp opens with mode 0600 by
        # default; we re-chmod to be explicit and portable.
        fd, tmp_path = tempfile.mkstemp(
            prefix=".tmp-", suffix=".json", dir=self.cache_dir
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(manifest, f, sort_keys=True, indent=2)
                f.write("\n")
            os.chmod(tmp_path, _FILE_MODE)
            os.replace(tmp_path, dest)
        except Exception:
            # Best-effort cleanup of the temp file on any failure.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        # The directory may have existed pre-call with looser perms;
        # tighten on every successful put.
        try:
            os.chmod(self.cache_dir, _DIR_MODE)
        except OSError:
            pass
        return dest

    def list_versions(self, org_id: str) -> list[str]:
        """Return all cached calibration_versions for an org, unsorted."""
        if not self.cache_dir.exists():
            return []
        prefix = f"{org_id}_"
        versions: list[str] = []
        for p in self.cache_dir.iterdir():
            name = p.name
            if name.startswith(prefix) and name.endswith(".json") and not name.startswith(".tmp-"):
                versions.append(name[len(prefix):-len(".json")])
        return versions

    def latest_accepted(self, org_id: str) -> str | None:
        """Lex-max calibration_version for the org, or None.

        v1 uses simple string compare. The spec doesn't pin a comparison
        rule, so the contract is: orgs MUST use a versioning scheme that
        sorts lexicographically in chronological order (`2026-Q2.1` <
        `2026-Q3.1`, `1.2.3` < `1.10.0` is broken — semver users must
        zero-pad). Document at the consumer-skill layer.
        """
        versions = self.list_versions(org_id)
        return max(versions) if versions else None


def check_monotonicity(cache: ManifestCache, manifest: dict[str, Any]) -> None:
    """Raise MonotonicityViolation if the incoming version is older than
    a previously-accepted one for the same org.
    """
    org_id = manifest["org_id"]
    incoming = manifest["calibration_version"]
    latest = cache.latest_accepted(org_id)
    if latest is not None and incoming < latest:
        raise MonotonicityViolation(
            f"incoming calibration_version={incoming!r} < latest accepted "
            f"{latest!r} for org_id={org_id!r}; rollback rejected"
        )


# --- Orchestrator -----------------------------------------------------

def load_manifest(
    *,
    fresh_manifest: dict[str, Any] | None,
    cache: ManifestCache | None = None,
    org_id: str = "parallax-default",
    pinned_calibration_version: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compose verify + expiry + monotonicity + cache fallback.

    Args:
        fresh_manifest: a manifest dict freshly fetched (or None if no
            fresh fetch was attempted, e.g. offline). When provided, it
            is verified, expiry-checked, monotonicity-checked, and
            cached on success.
        cache: ManifestCache instance (auto-instantiated to defaults if None).
        org_id: which org's calibration to load. v1: always "parallax-default".
        pinned_calibration_version: when set, force loading this exact
            version from cache (ignores fresh_manifest's version). Used
            by replay tooling and by `version_id`-pinned client sessions.
            When None, the orchestrator prefers `fresh_manifest`'s version
            (or the latest cached version if no fresh).
        now: optional time injection for tests.

    Returns the manifest dict that the caller should USE (cached or fresh).

    Raises typed errors describing why no usable manifest is available:
        ManifestVerificationError subclasses (signature, kid, malformed)
        ManifestExpired, MonotonicityViolation, DeadStateNoFallback
    """
    if cache is None:
        cache = ManifestCache()
    effective_now = now if now is not None else _utcnow()

    # ---- Fresh-manifest path ----
    if fresh_manifest is not None:
        try:
            manifest_verify.verify_manifest(
                fresh_manifest, cache.trusted_keys_path, now=effective_now
            )
        except manifest_verify.KeyIdUnknown:
            # Schema spec §6.2 step 2: do NOT discard the cached manifest
            # — fall back to it if still valid.
            cv = pinned_calibration_version or cache.latest_accepted(org_id)
            if cv is None:
                # Nothing in cache at all. A-3 dead-state subset.
                raise DeadStateNoFallback(
                    f"signing_key_id={fresh_manifest.get('signing_key_id')!r} "
                    f"not in trusted_keys.json and no cached manifest "
                    f"available for org_id={org_id!r}. Skill update required."
                )
            cached = cache.get(org_id, cv, now=effective_now)
            if cached is None:
                raise DeadStateNoFallback(
                    f"signing_key_id={fresh_manifest.get('signing_key_id')!r} "
                    f"unknown and cache miss on (org_id={org_id!r}, "
                    f"calibration_version={cv!r}). Skill update required."
                )
            try:
                check_expiry(cached, effective_now)
            except ManifestExpired:
                # The full A-3 dead state: cached is also expired.
                raise DeadStateNoFallback(
                    f"signing_key_id={fresh_manifest.get('signing_key_id')!r} "
                    f"unknown and cached manifest "
                    f"(org_id={org_id!r}, calibration_version={cv!r}) "
                    f"already expired. Skill update required."
                )
            return cached

        # Fresh signature was good. Now check expiry and monotonicity.
        check_expiry(fresh_manifest, effective_now)
        check_monotonicity(cache, fresh_manifest)
        cache.put(fresh_manifest)
        return fresh_manifest

    # ---- Cache-only path (no fresh fetch attempted) ----
    cv = pinned_calibration_version or cache.latest_accepted(org_id)
    if cv is None:
        raise DeadStateNoFallback(
            f"no fresh manifest provided and no cached manifest for "
            f"org_id={org_id!r}. Cannot load."
        )
    cached = cache.get(org_id, cv, now=effective_now)
    if cached is None:
        raise DeadStateNoFallback(
            f"cache miss on (org_id={org_id!r}, calibration_version={cv!r}) "
            f"and no fresh manifest provided."
        )
    # Note: we do NOT raise on cached-expired in the cache-only path.
    # Per schema spec §7.3, expired-and-offline emits a warning and
    # proceeds — fail-closed would break offline CIO workflows. The
    # caller decides whether to use the manifest given the warning.
    try:
        check_expiry(cached, effective_now)
    except ManifestExpired as e:
        logger.warning(
            "manifest_expired_offline: using expired cached manifest "
            "(org_id=%s, calibration_version=%s); reconnect to refresh: %s",
            org_id, cv, e,
        )
    return cached
