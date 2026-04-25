#!/usr/bin/env python3
"""Calibration manifest verifier — minimal vertical slice.

Implements the verification half of the calibration manifest spec triad
(notes/2026-04-24-manifest-{endpoint,schema-v1,reasoning-chain}-spec.md).

Scope of this module (Batch 3 minimal slice):
  - Parse a manifest JSON blob.
  - Look up `signing_key_id` in `signing/trusted_keys.json`.
  - Strip the `signature` field, JCS-canonicalize the remainder, verify
    the Ed25519 signature against the pinned pubkey.
  - Compute `manifest_ref.hash` (SHA-256 of full manifest INCLUDING
    `signature`) and assert it differs from the signing-payload hash
    (anti-collision guard per chain spec §3.2 / security audit A-1).
  - Return the parsed manifest dict + the chain-anchor hash on success.

Out of scope (deferred to Batch 3.5):
  - On-disk cache (~/.parallax/calibration/<org_id>_<calibration_version>.json),
    file-permission enforcement (0600/0700 per security audit B-1),
    monotonicity check on calibration_version.
  - Expiry handling (manifest_expires_at <= now() boundary) — caller
    today receives the manifest and decides; cache layer will own this.
  - Dead-state guard for expired-cache + key_id_unknown (security audit
    A-3) — applies once cache layer exists.
  - HTTP fetch from the endpoint — caller passes a pre-fetched dict or
    JSON path.

The entry point is `verify_manifest()`. All failure modes raise a typed
exception from `ManifestVerificationError`'s subclass hierarchy with the
error_code matching the spec's documented codes (`key_id_unknown`,
`signature_invalid`, `manifest_signature_missing`, etc.) so callers can
branch on machine-readable identifiers without parsing message strings.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import rfc8785
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "rfc8785 is required. Install: pip install -r "
        "skills/_parallax/house-view/requirements.txt"
    ) from e

try:
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "pynacl is required. Install: pip install -r "
        "skills/_parallax/house-view/requirements.txt"
    ) from e


# --- Error hierarchy --------------------------------------------------
# Error codes mirror schema spec §6.2 verification flow + chain spec §3.2.

class ManifestVerificationError(Exception):
    error_code: str = "manifest_verification_error"


class ManifestMalformed(ManifestVerificationError):
    error_code = "manifest_malformed"


class KeyIdUnknown(ManifestVerificationError):
    error_code = "key_id_unknown"


class KeyIdNotYetValid(ManifestVerificationError):
    error_code = "key_id_not_yet_valid"


class KeyIdExpired(ManifestVerificationError):
    error_code = "key_id_expired"


class SignatureInvalid(ManifestVerificationError):
    error_code = "signature_invalid"


class ManifestSignatureMissing(ManifestVerificationError):
    """Anti-collision guard tripped (chain spec §3.2): the chain's trust-
    anchor hash would be indistinguishable from the signing-payload hash.
    Indicates the signing layer did not append a `signature` field, or
    appended an empty one. Refuse to verify rather than emit a chain
    that auditors cannot distinguish from the unsigned payload.
    """
    error_code = "manifest_signature_missing"


# --- Trusted keys loader ----------------------------------------------

def _load_trusted_keys(trusted_keys_path: Path) -> dict[str, dict[str, Any]]:
    """Read trusted_keys.json and index by kid for O(1) lookup."""
    raw = json.loads(trusted_keys_path.read_text())
    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise ManifestMalformed(
            f"trusted_keys.json schema_version={schema_version!r}, expected 1"
        )
    keys = raw.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ManifestMalformed(
            "trusted_keys.json: `keys` must be a non-empty list"
        )
    indexed: dict[str, dict[str, Any]] = {}
    for entry in keys:
        kid = entry.get("kid")
        if not isinstance(kid, str) or not kid:
            raise ManifestMalformed(
                "trusted_keys.json: every key entry must have a non-empty `kid`"
            )
        if kid in indexed:
            raise ManifestMalformed(
                f"trusted_keys.json: duplicate kid {kid!r}"
            )
        indexed[kid] = entry
    return indexed


def _parse_iso8601(s: str) -> datetime:
    # Normalize Z → +00:00 for fromisoformat (Python ≤3.10 compatibility).
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _check_key_validity_window(entry: dict[str, Any], now: datetime) -> None:
    valid_from_s = entry.get("valid_from")
    if isinstance(valid_from_s, str):
        if now < _parse_iso8601(valid_from_s):
            raise KeyIdNotYetValid(
                f"Signing key {entry['kid']!r} is not yet valid "
                f"(valid_from={valid_from_s})"
            )
    valid_until_s = entry.get("valid_until")
    if isinstance(valid_until_s, str):
        if now >= _parse_iso8601(valid_until_s):
            raise KeyIdExpired(
                f"Signing key {entry['kid']!r} expired at {valid_until_s}"
            )


# --- Verification core ------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_manifest(
    manifest: dict[str, Any],
    trusted_keys_path: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify a calibration manifest dict.

    Args:
        manifest: parsed JSON dict (from endpoint response or cache file).
        trusted_keys_path: path to the skill's pinned trusted_keys.json.
        now: optional override for the current time (test injection).
            Defaults to UTC now.

    Returns:
        {
          "manifest": <input manifest dict, unchanged>,
          "manifest_ref_hash": <SHA-256 hex of JCS(full manifest including
              signature) — what the chain emitter will write into
              chain.manifest_ref.hash per chain spec §3.2>,
          "signing_payload_hash": <SHA-256 hex of JCS(manifest with
              signature stripped) — internal, included for diagnostics>,
          "kid": <signing_key_id used>,
        }

    Raises:
        ManifestMalformed: structural problems (missing fields, wrong types).
        KeyIdUnknown: signing_key_id not in trusted_keys.json.
        KeyIdNotYetValid / KeyIdExpired: kid found but outside its validity
            window. Distinct codes so callers (e.g., auditor replay) can
            distinguish "we never trusted this key" from "we trust(ed) this
            key but the window has elapsed".
        SignatureInvalid: cryptographic verification failed.
        ManifestSignatureMissing: anti-collision guard tripped — manifest
            has no usable signature so the chain hash would equal the
            signing payload hash.

    The function is pure: it does NOT touch the filesystem beyond reading
    `trusted_keys_path`, does NOT enforce expiry/monotonicity (cache
    layer's job), does NOT perform any HTTP. Caller controls those.
    """
    if not isinstance(manifest, dict):
        raise ManifestMalformed(f"manifest must be a JSON object, got {type(manifest).__name__}")

    kid = manifest.get("signing_key_id")
    if not isinstance(kid, str) or not kid:
        raise ManifestMalformed("manifest missing required field `signing_key_id`")

    signature_block = manifest.get("signature")
    if not isinstance(signature_block, dict):
        raise ManifestMalformed(
            "manifest missing required field `signature` (must be an object "
            "with `alg` and `value`)"
        )
    alg = signature_block.get("alg")
    sig_value = signature_block.get("value")
    if alg != "ed25519":
        raise ManifestMalformed(
            f"manifest signature.alg must be 'ed25519' for v1, got {alg!r}"
        )
    if not isinstance(sig_value, str) or not sig_value:
        # An empty / null sig value means signing was skipped or failed.
        # We refuse to verify rather than fall through to the
        # anti-collision guard — emit a clearer error code.
        raise ManifestMalformed(
            "manifest signature.value is empty; nothing to verify"
        )
    try:
        sig_bytes = base64.b64decode(sig_value, validate=True)
    except Exception as e:
        raise ManifestMalformed(f"signature.value is not valid base64: {e}") from e

    # Look up the kid in trusted_keys.json.
    trusted_keys_path = Path(trusted_keys_path)
    trusted = _load_trusted_keys(trusted_keys_path)
    entry = trusted.get(kid)
    if entry is None:
        raise KeyIdUnknown(
            f"Manifest signed with key {kid!r} not in {trusted_keys_path}. "
            "Skill update required."
        )
    if entry.get("alg") != "ed25519":
        raise ManifestMalformed(
            f"trusted_keys.json: key {kid!r} has alg "
            f"{entry.get('alg')!r}, expected 'ed25519'"
        )
    pubkey_b64 = entry.get("pubkey_b64")
    if not isinstance(pubkey_b64, str) or not pubkey_b64:
        raise ManifestMalformed(
            f"trusted_keys.json: key {kid!r} missing `pubkey_b64`"
        )
    try:
        pubkey_bytes = base64.b64decode(pubkey_b64, validate=True)
    except Exception as e:
        raise ManifestMalformed(
            f"trusted_keys.json: key {kid!r} pubkey_b64 not valid base64: {e}"
        ) from e

    # Validity-window check uses caller's `now` (or wall clock) — keeps
    # the function deterministic under test injection.
    effective_now = now if now is not None else datetime.now(timezone.utc)
    _check_key_validity_window(entry, effective_now)

    # JCS-canonicalize the manifest WITHOUT the signature field; that is
    # the signing payload per schema spec §6.2 step 3. Make a shallow
    # copy so we don't mutate the caller's dict.
    payload_for_signing = {k: v for k, v in manifest.items() if k != "signature"}
    signing_payload_bytes = rfc8785.dumps(payload_for_signing)

    # Verify Ed25519 signature.
    try:
        VerifyKey(pubkey_bytes).verify(signing_payload_bytes, sig_bytes)
    except BadSignatureError as e:
        raise SignatureInvalid(
            f"Ed25519 verification failed against key {kid!r}"
        ) from e

    # Compute both hashes and assert they differ (anti-collision guard,
    # chain spec §3.2 / security audit A-1).
    full_manifest_bytes = rfc8785.dumps(manifest)
    signing_payload_hash = _sha256_hex(signing_payload_bytes)
    manifest_ref_hash = _sha256_hex(full_manifest_bytes)
    if manifest_ref_hash == signing_payload_hash:
        raise ManifestSignatureMissing(
            "Anti-collision guard: manifest_ref.hash equals signing payload "
            "hash — the signature field was not appended or was identical "
            "to its absence under JCS canonicalization. Refuse to emit."
        )

    return {
        "manifest": manifest,
        "manifest_ref_hash": manifest_ref_hash,
        "signing_payload_hash": signing_payload_hash,
        "kid": kid,
    }


def verify_manifest_path(
    manifest_path: Path | str,
    trusted_keys_path: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Convenience wrapper for the file-on-disk case."""
    manifest_path = Path(manifest_path)
    raw = manifest_path.read_text()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ManifestMalformed(
            f"{manifest_path} is not valid JSON: {e}"
        ) from e
    return verify_manifest(manifest, trusted_keys_path, now=now)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    parser = argparse.ArgumentParser(description="Verify a calibration manifest.")
    parser.add_argument("manifest_path", help="Path to the manifest JSON file.")
    parser.add_argument(
        "--trusted-keys",
        default=str(Path(__file__).parent / "signing" / "trusted_keys.json"),
        help="Path to trusted_keys.json (default: bundled).",
    )
    args = parser.parse_args()
    try:
        result = verify_manifest_path(args.manifest_path, args.trusted_keys)
    except ManifestVerificationError as e:
        print(f"FAIL [{e.error_code}]: {e}")
        raise SystemExit(1)
    print(f"OK  kid={result['kid']}")
    print(f"    manifest_ref.hash  = sha256:{result['manifest_ref_hash']}")
    print(f"    signing_payload_h  = sha256:{result['signing_payload_hash']}")
