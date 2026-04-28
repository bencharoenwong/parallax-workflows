#!/usr/bin/env python3
"""Generate a signed test manifest fixture for manifest_verify round-trips.

PUBLIC — this script signs with the test-only key in
`tests/fixtures/test-signing-key.priv`, NOT a production key. The test-only
kid is labeled `use: "test-only"` in `signing/trusted_keys.json` and is
deliberately published so auditors can verify round-trip on a fresh clone.
Regenerate the fixture whenever the manifest schema changes.

Usage (from skills/_parallax/house-view/):

    python3 tests/_gen_test_fixture.py
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import rfc8785
from nacl.signing import SigningKey


HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
PRIV_KEY_PATH = HERE / "fixtures" / "test-signing-key.priv"
TRUSTED_KEYS_PATH = HOUSE_VIEW_DIR / "signing" / "trusted_keys.json"
OUTPUT_PATH = HERE / "fixtures" / "manifest-test-2026-Q2.1.json"


def _load_test_signing_key() -> SigningKey:
    raw = PRIV_KEY_PATH.read_text().strip()
    return SigningKey(base64.b64decode(raw, validate=True))


def _load_test_kid() -> str:
    """Pick the single test-only kid from trusted_keys.json (use=='test-only')."""
    keys = json.loads(TRUSTED_KEYS_PATH.read_text())["keys"]
    test_keys = [k for k in keys if k.get("use") == "test-only"]
    if len(test_keys) != 1:
        raise SystemExit(
            f"Expected exactly one use=='test-only' key in {TRUSTED_KEYS_PATH}, "
            f"found {len(test_keys)}"
        )
    return test_keys[0]["kid"]


def _build_manifest(kid: str) -> dict:
    """A minimal manifest body matching schema spec §2 envelope.

    Values block is intentionally tiny (just enough to round-trip) — the
    verifier doesn't inspect content semantics, only structure + signature.
    Real Batch 3.5+ tests will use richer fixtures derived from the spec
    triad's worked example.
    """
    return {
        "schema_version": "1.0.0",
        "calibration_version": "test-2026-Q2.1",
        "org_id": "parallax-default",
        "issued_at": "2026-04-25T12:00:00Z",
        "manifest_expires_at": "2026-07-25T12:00:00Z",
        "signing_key_id": kid,
        "values": {
            "sec-pillar-multipliers": {
                "active": True,
                "values": {
                    "econometrics_phase": 1.0,
                    "valuation_state": 1.0,
                    "market_entropy": 1.0,
                    "psychological_wavelength": 1.0,
                },
            },
            "sec-sensitivity-bands": {
                "warn_multiplier": 1.5,
                "bands": {
                    "default": {
                        "median_shift_min_bp": -25,
                        "median_shift_max_bp": 25,
                    },
                },
            },
            "sec-kill-criterion": {
                "median_shift_pct": 5.0,
                "applies_to_bundles": ["default"],
            },
        },
        "provenance": {
            "sec-pillar-multipliers": {
                "methodology_section": "GUESS",
                "backtest_ref": None,
                "notes": "test-only fixture; not for production",
            },
        },
    }


def main() -> None:
    sk = _load_test_signing_key()
    kid = _load_test_kid()
    manifest = _build_manifest(kid)

    # Sign over JCS canonicalization with `signature` field absent.
    signing_payload = rfc8785.dumps(manifest)
    sig = sk.sign(signing_payload).signature
    manifest["signature"] = {
        "alg": "ed25519",
        "value": base64.b64encode(sig).decode("ascii"),
    }

    # Write pretty-printed JSON (the file on disk is for humans to grep;
    # the verifier re-canonicalizes via JCS so on-disk formatting is
    # decorative). Keep stable key order to minimize diff churn.
    OUTPUT_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(f"Wrote {OUTPUT_PATH.relative_to(HOUSE_VIEW_DIR.parent.parent)}")
    print(f"  kid={kid}")
    print(f"  bytes_signed={len(signing_payload)}")
    print(f"  sig_b64_len={len(manifest['signature']['value'])}")


if __name__ == "__main__":
    main()
