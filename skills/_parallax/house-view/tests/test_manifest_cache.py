#!/usr/bin/env python3
"""Cache-layer tests for manifest_cache.py (Batch 3.5).

Covers:
  1. Cache round-trip (put → get returns the same dict).
  2. Atomic writes set 0600 / 0700 at write time.
  3. Loose perms on disk emit cache_permissions_unsafe via logger
     (security audit B-1 contract: warn, do not raise).
  4. Expiry boundary is strict: manifest_expires_at == now → expired.
  5. Monotonicity check rejects rollback to an older calibration_version.
  6. A-3 dead state: fresh has unknown kid AND cached is expired →
     DeadStateNoFallback.
  7. Orchestrator: fresh manifest with new version writes to cache and
     returns it.
  8. Orchestrator: cache-only path (fresh=None) returns cached manifest.
  9. Orchestrator: cache-only on expired cache emits warning but
     returns the cached manifest (offline-friendly per schema §7.3).

Tests sign manifests on the fly with the same test key in
`tests/fixtures/test-signing-key.priv` so we can construct manifests
with arbitrary expiry / version values without committing 9 fixtures.

Run from `skills/_parallax/house-view/`:

    python3 tests/test_manifest_cache.py
"""
from __future__ import annotations

import base64
import json
import logging
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rfc8785
from nacl.signing import SigningKey

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import manifest_verify  # noqa: E402
import manifest_cache  # noqa: E402

TRUSTED_KEYS_PATH = HOUSE_VIEW_DIR / "signing" / "trusted_keys.json"
PRIV_KEY_PATH = HERE / "fixtures" / "test-signing-key.priv"


# --- Test helpers ------------------------------------------------------

def _signing_key() -> SigningKey:
    return SigningKey(base64.b64decode(PRIV_KEY_PATH.read_text().strip(), validate=True))


def _test_kid() -> str:
    keys = json.loads(TRUSTED_KEYS_PATH.read_text())["keys"]
    test_keys = [k for k in keys if k.get("use") == "test-only"]
    return test_keys[0]["kid"]


def _build_signed_manifest(
    *,
    calibration_version: str = "test-2026-Q2.1",
    expires_at: str = "2027-01-01T00:00:00Z",
    org_id: str = "parallax-default",
    issued_at: str = "2026-04-25T12:00:00Z",
) -> dict:
    """Build a minimal valid signed manifest for tests."""
    sk = _signing_key()
    kid = _test_kid()
    body = {
        "schema_version": "1.0.0",
        "calibration_version": calibration_version,
        "org_id": org_id,
        "issued_at": issued_at,
        "manifest_expires_at": expires_at,
        "signing_key_id": kid,
        "values": {
            "sec-sensitivity-bands": {
                "warn_multiplier": 1.5,
                "bands": {"default": {"median_shift_min_bp": -25, "median_shift_max_bp": 25}},
            },
        },
    }
    payload = rfc8785.dumps(body)
    sig = sk.sign(payload).signature
    body["signature"] = {"alg": "ed25519", "value": base64.b64encode(sig).decode("ascii")}
    return body


def _new_cache(tmpdir: Path) -> manifest_cache.ManifestCache:
    return manifest_cache.ManifestCache(
        cache_dir=tmpdir, trusted_keys_path=TRUSTED_KEYS_PATH
    )


# --- Tests -------------------------------------------------------------

def test_cache_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = _new_cache(Path(tmpdir))
        m = _build_signed_manifest()
        cache.put(m)
        got = cache.get(m["org_id"], m["calibration_version"])
        assert got is not None, "cache miss after put"
        assert got["signature"]["value"] == m["signature"]["value"], "round-trip body mismatch"
    print("PASS  test_cache_round_trip")


def test_atomic_write_sets_permissions() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        # Pre-set the parent dir to looser perms; put should tighten back.
        Path(tmpdir).chmod(0o755)
        cache = _new_cache(Path(tmpdir))
        m = _build_signed_manifest()
        path = cache.put(m)
        file_mode = stat.S_IMODE(path.stat().st_mode)
        dir_mode = stat.S_IMODE(Path(tmpdir).stat().st_mode)
        assert file_mode == 0o600, f"file mode {oct(file_mode)} != 0o600"
        assert dir_mode == 0o700, f"dir mode {oct(dir_mode)} != 0o700"
    print("PASS  test_atomic_write_sets_permissions")


def test_loose_perms_emit_warning() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = _new_cache(Path(tmpdir))
        m = _build_signed_manifest()
        path = cache.put(m)
        # Manually loosen perms to simulate drift.
        path.chmod(0o644)
        # Capture log records during get().
        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger("manifest_cache").addHandler(handler)
        try:
            cache.get(m["org_id"], m["calibration_version"])
        finally:
            logging.getLogger("manifest_cache").removeHandler(handler)
        msgs = [r.getMessage() for r in records]
        assert any("cache_permissions_unsafe" in msg for msg in msgs), (
            f"expected cache_permissions_unsafe warning, got: {msgs}"
        )
    print("PASS  test_loose_perms_emit_warning")


def test_expiry_boundary_strict() -> None:
    fixed_now = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)
    # Build a manifest expiring AT exactly fixed_now — boundary inclusive
    # rejection per schema §6.2 step 5.
    m = _build_signed_manifest(expires_at=fixed_now.isoformat().replace("+00:00", "Z"))
    try:
        manifest_cache.check_expiry(m, now=fixed_now)
    except manifest_cache.ManifestExpired as e:
        assert e.error_code == "manifest_expired"
        # And one second AFTER expiry must also fail.
        try:
            manifest_cache.check_expiry(m, now=fixed_now + timedelta(seconds=1))
        except manifest_cache.ManifestExpired:
            pass
        else:
            raise AssertionError("expected expiry to fail past the boundary too")
        # Validate that one second BEFORE is fine (cross-check).
        manifest_cache.check_expiry(m, now=fixed_now - timedelta(seconds=1))
        print("PASS  test_expiry_boundary_strict")
        return
    raise AssertionError("manifest at exact-boundary expiry was accepted; should reject")


def test_monotonicity_blocks_rollback() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = _new_cache(Path(tmpdir))
        # Accept newer first.
        newer = _build_signed_manifest(calibration_version="test-2026-Q3.1")
        cache.put(newer)
        # Then attempt to install older.
        older = _build_signed_manifest(calibration_version="test-2026-Q2.1")
        try:
            manifest_cache.check_monotonicity(cache, older)
        except manifest_cache.MonotonicityViolation as e:
            assert e.error_code == "monotonicity_violation"
            print("PASS  test_monotonicity_blocks_rollback")
            return
    raise AssertionError("rollback to older calibration_version was accepted; should reject")


def test_dead_state_guard() -> None:
    """A-3: fresh manifest has unknown kid AND cached is expired →
    DeadStateNoFallback. Most subtle case in the orchestrator.
    """
    fixed_now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = _new_cache(Path(tmpdir))
        # Plant an expired cached manifest (expired well before fixed_now).
        expired_cached = _build_signed_manifest(
            calibration_version="test-2026-Q1.1",
            expires_at="2026-03-01T00:00:00Z",  # < fixed_now
        )
        cache.put(expired_cached)
        # Fresh manifest signed by a kid we don't trust. Build it by
        # forging a NEW Ed25519 key and putting its kid into the signed
        # body (verifier will look up that kid in trusted_keys.json
        # and miss).
        forger = SigningKey.generate()
        body = {
            "schema_version": "1.0.0",
            "calibration_version": "test-2026-Q3.1",
            "org_id": "parallax-default",
            "issued_at": "2026-05-25T12:00:00Z",
            "manifest_expires_at": "2026-09-01T00:00:00Z",
            "signing_key_id": "test-rotated-out-deadbeef",  # NOT in trusted_keys
            "values": {},
        }
        body["signature"] = {
            "alg": "ed25519",
            "value": base64.b64encode(
                forger.sign(rfc8785.dumps(body)).signature
            ).decode("ascii"),
        }
        try:
            manifest_cache.load_manifest(
                fresh_manifest=body, cache=cache, now=fixed_now
            )
        except manifest_cache.DeadStateNoFallback as e:
            assert e.error_code == "key_id_unknown_no_fallback"
            print("PASS  test_dead_state_guard")
            return
    raise AssertionError("dead-state guard did not fire; should have raised DeadStateNoFallback")


def test_orchestrator_writes_new_version_to_cache() -> None:
    fixed_now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = _new_cache(Path(tmpdir))
        fresh = _build_signed_manifest(calibration_version="test-2026-Q3.1")
        result = manifest_cache.load_manifest(
            fresh_manifest=fresh, cache=cache, now=fixed_now
        )
        assert result["calibration_version"] == "test-2026-Q3.1"
        assert cache.path_for("parallax-default", "test-2026-Q3.1").exists(), (
            "fresh manifest was not persisted to cache"
        )
    print("PASS  test_orchestrator_writes_new_version_to_cache")


def test_orchestrator_uses_cache_when_fresh_none() -> None:
    fixed_now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = _new_cache(Path(tmpdir))
        m = _build_signed_manifest()
        cache.put(m)
        result = manifest_cache.load_manifest(
            fresh_manifest=None, cache=cache, now=fixed_now
        )
        assert result["calibration_version"] == m["calibration_version"]
    print("PASS  test_orchestrator_uses_cache_when_fresh_none")


def test_orchestrator_offline_expired_cache_warns_returns() -> None:
    """Offline + expired cache: per schema §7.3, emit warning but proceed.
    The dead-state guard does NOT fire here — that's only for the
    fresh-manifest-with-unknown-kid path.
    """
    fixed_now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = _new_cache(Path(tmpdir))
        expired = _build_signed_manifest(expires_at="2026-03-01T00:00:00Z")
        cache.put(expired)
        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger("manifest_cache").addHandler(handler)
        try:
            result = manifest_cache.load_manifest(
                fresh_manifest=None, cache=cache, now=fixed_now
            )
        finally:
            logging.getLogger("manifest_cache").removeHandler(handler)
        assert result is expired or result["signature"] == expired["signature"]
        msgs = [r.getMessage() for r in records]
        assert any("manifest_expired_offline" in msg for msg in msgs), (
            f"expected manifest_expired_offline warning, got: {msgs}"
        )
    print("PASS  test_orchestrator_offline_expired_cache_warns_returns")


# --- Runner ------------------------------------------------------------

def main() -> int:
    tests = [
        test_cache_round_trip,
        test_atomic_write_sets_permissions,
        test_loose_perms_emit_warning,
        test_expiry_boundary_strict,
        test_monotonicity_blocks_rollback,
        test_dead_state_guard,
        test_orchestrator_writes_new_version_to_cache,
        test_orchestrator_uses_cache_when_fresh_none,
        test_orchestrator_offline_expired_cache_warns_returns,
    ]
    failures = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failures += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            failures += 1
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print(f"\nAll {len(tests)} tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
