#!/usr/bin/env python3
"""Round-trip + tamper tests for manifest_verify.py.

Covers the minimal-vertical-slice scope:
  1. The signed test fixture verifies cleanly and yields distinct
     manifest_ref / signing_payload hashes.
  2. Tampered values block fails with SignatureInvalid.
  3. Unknown signing_key_id fails with KeyIdUnknown.
  4. Manifest with `signature.value` empty fails before crypto runs
     (anti-collision guard upstream sanity check).
  5. Anti-collision guard fires when manifest_ref hash equals signing
     payload hash — synthesized by removing the `signature` field
     entirely AFTER signing (impossible in practice but proves the guard
     bites if a buggy emitter ever produces the collision).

Run from `skills/_parallax/house-view/`:

    python3 tests/test_manifest_verify.py

Exits non-zero on first failing assertion.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

# Allow running this file directly: add the parent (house-view/) to path
# so `import manifest_verify` resolves.
HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import manifest_verify  # noqa: E402

TRUSTED_KEYS_PATH = HOUSE_VIEW_DIR / "signing" / "trusted_keys.json"
FIXTURE_PATH = HERE / "fixtures" / "manifest-test-2026-Q2.1.json"


def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        raise SystemExit(
            f"Test fixture missing: {FIXTURE_PATH}. "
            "Generate it with: python3 tests/_gen_test_fixture.py"
        )
    return json.loads(FIXTURE_PATH.read_text())


def test_valid_round_trip() -> None:
    manifest = _load_fixture()
    result = manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)
    assert result["kid"] == manifest["signing_key_id"], (
        f"verifier returned kid={result['kid']!r} but manifest has "
        f"signing_key_id={manifest['signing_key_id']!r}"
    )
    # Anti-collision guard: the two hashes MUST differ.
    assert result["manifest_ref_hash"] != result["signing_payload_hash"], (
        "manifest_ref_hash == signing_payload_hash; anti-collision "
        "guard should have refused but the hashes collided in production"
    )
    # Both are 64-char hex (sha256).
    assert len(result["manifest_ref_hash"]) == 64
    assert len(result["signing_payload_hash"]) == 64
    print(f"PASS  test_valid_round_trip (manifest_ref_hash={result['manifest_ref_hash'][:12]}...)")


def test_tampered_values_block() -> None:
    manifest = _load_fixture()
    # Mutate the warn_multiplier post-signature: signature was over the
    # original bytes, so verification MUST fail.
    manifest["values"]["sec-sensitivity-bands"]["warn_multiplier"] = 99.0
    try:
        manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)
    except manifest_verify.SignatureInvalid as e:
        assert e.error_code == "signature_invalid", (
            f"expected error_code='signature_invalid', got {e.error_code!r}"
        )
        print("PASS  test_tampered_values_block (raised SignatureInvalid as expected)")
        return
    raise AssertionError("Tampered manifest verified successfully — that's a bug.")


def test_unknown_kid() -> None:
    manifest = _load_fixture()
    manifest["signing_key_id"] = "test-deadbeefdeadbeef-not-in-trusted-keys"
    try:
        manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)
    except manifest_verify.KeyIdUnknown as e:
        assert e.error_code == "key_id_unknown", (
            f"expected error_code='key_id_unknown', got {e.error_code!r}"
        )
        print("PASS  test_unknown_kid (raised KeyIdUnknown as expected)")
        return
    raise AssertionError("Manifest with unknown kid verified successfully — that's a bug.")


def test_empty_signature_value() -> None:
    manifest = _load_fixture()
    manifest["signature"]["value"] = ""
    try:
        manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)
    except manifest_verify.ManifestMalformed as e:
        # ManifestMalformed catches the empty-sig case BEFORE we attempt
        # crypto verification, which is the intended ordering: structural
        # validation precedes crypto. Confirms the spec's "reject if
        # malformed" step in §6.2 step 1.
        assert "signature.value is empty" in str(e), (
            f"expected message about empty signature, got: {e}"
        )
        print("PASS  test_empty_signature_value (raised ManifestMalformed as expected)")
        return
    raise AssertionError("Empty signature value verified successfully — that's a bug.")


def test_anti_collision_guard_synthetic() -> None:
    """Force the anti-collision guard to fire by constructing a manifest
    whose signing-payload hash equals its full-manifest hash.

    Approach: monkey-patch the SHA-256 helper to return a constant string,
    so both hashes collide regardless of input. We do NOT remove the
    `signature` field from the manifest itself — the verifier requires a
    valid signature to even reach the anti-collision step, so we keep the
    real signed fixture and just override the hash function temporarily.

    This proves the guard bites if a real emitter bug ever produced
    colliding hashes (e.g., a buggy JCS that ignored the signature field
    silently).
    """
    manifest = _load_fixture()
    original_sha256_hex = manifest_verify._sha256_hex
    manifest_verify._sha256_hex = lambda data: "deadbeef" * 8  # 64 hex chars
    try:
        manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)
    except manifest_verify.ManifestSignatureMissing as e:
        assert e.error_code == "manifest_signature_missing", (
            f"expected error_code='manifest_signature_missing', got {e.error_code!r}"
        )
        print("PASS  test_anti_collision_guard_synthetic (guard fired as expected)")
        return
    finally:
        manifest_verify._sha256_hex = original_sha256_hex
    raise AssertionError(
        "Anti-collision guard did not fire under forced hash collision — "
        "this means the chain spec §3.2 normative assertion is unenforced."
    )


def main() -> int:
    tests = [
        test_valid_round_trip,
        test_tampered_values_block,
        test_unknown_kid,
        test_empty_signature_value,
        test_anti_collision_guard_synthetic,
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
            failures += 1
    if failures:
        print(f"\n{failures} test(s) failed.")
        return 1
    print(f"\nAll {len(tests)} tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
