#!/usr/bin/env python3
"""Integration tests for load-house-view skill workflow (Batch 5).

Simulates the Step 4 logic:
  1. Load manifest via manifest_cache.
  2. Determine calibration_status based on manifest provenance.
  3. Emit reasoning chain via chain_emit.

Run from `skills/_parallax/house-view/`:

    python3 tests/test_skill_integration.py
"""
from __future__ import annotations

import base64
import json
import sys
import tempfile
from pathlib import Path

import rfc8785
import yaml
from nacl.signing import SigningKey

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import manifest_cache  # noqa: E402
import chain_emit  # noqa: E402

TRUSTED_KEYS_PATH = HOUSE_VIEW_DIR / "signing" / "trusted_keys.json"
PRIV_KEY_PATH = HERE / "fixtures" / "test-signing-key.priv"

def _signing_key() -> SigningKey:
    return SigningKey(base64.b64decode(PRIV_KEY_PATH.read_text().strip(), validate=True))

def _test_kid() -> str:
    keys = json.loads(TRUSTED_KEYS_PATH.read_text())["keys"]
    return next(k["kid"] for k in keys if k.get("use") == "test-only")

def _build_signed_manifest(
    *,
    calibration_version: str = "test-2026-Q2.1",
    methodology: str | None = "Standard methodology",
    backtest_ref: str | None = "backtest-123",
) -> dict:
    sk = _signing_key()
    kid = _test_kid()
    body = {
        "schema_version": "1.0.0",
        "calibration_version": calibration_version,
        "org_id": "parallax-default",
        "issued_at": "2026-04-25T12:00:00Z",
        "manifest_expires_at": "2027-01-01T00:00:00Z",
        "signing_key_id": kid,
        "provenance": {
            "methodology_section": methodology,
            "backtest_ref": backtest_ref,
        },
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

def test_full_integration_flow():
    """Verify the skill's Step 4 programmatic flow."""
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        cache_dir = tmp_dir / "cache"
        chain_dir = tmp_dir / "chains"
        cache_dir.mkdir()
        chain_dir.mkdir()

        # 1. Setup manifest in cache
        manifest_data = _build_signed_manifest(
            methodology="Empirical calibration v1",
            backtest_ref="bt-789"
        )
        cache = manifest_cache.ManifestCache(cache_dir, TRUSTED_KEYS_PATH)
        cache.put(manifest_data)

        # --- SIMULATE SKILL STEP 4 ---
        view_hash = "abc123canonical"
        uploader_role = "CIO"
        basis_statement = "IC Meeting 2026-04"
        parent_version_id = None

        # Step 4.1a: Load manifest
        try:
            manifest = manifest_cache.load_manifest(
                fresh_manifest=None,
                cache=cache
            )
            status = "ACTIVE"
        except Exception as e:
            print(f"Manifest load failed (falling back to Phase 0): {e}")
            manifest = None
            status = "PHASE_0_FALLBACK"

        assert status == "ACTIVE"
        assert manifest["calibration_version"] == "test-2026-Q2.1"

        # Step 4.6b: Determine calibration_status
        prov = manifest.get("provenance", {})
        if (status == "ACTIVE" and 
            prov.get("methodology_section") != "GUESS" and 
            prov.get("backtest_ref") is not None):
            calibration_status = "empirical_phase1"
        else:
            calibration_status = "heuristic_phase0"
        
        assert calibration_status == "empirical_phase1"

        # Step 4.11a: Emit Reasoning Chain
        dummy_base_scores = {
            "response_inline": {},
            "response_hash": "0" * 64,
        }
        dummy_final_portfolio = {
            "weights": {},
        }
        run_id = "01HZ" + "0" * 22 # Dummy run_id
        skill_version = "parallax-load-house-view@0.5.0"

        if status == "ACTIVE":
            # In actual skill, manifest_ref_hash and signing_payload_hash would come from verify_manifest result
            import manifest_verify
            result = manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)
            
            chain_path = chain_emit.emit_chain(
                view=view_hash, # Using view_hash as dummy for the view content here
                base_scores=dummy_base_scores,
                final_portfolio=dummy_final_portfolio,
                run_id=run_id,
                skill_version=skill_version,
                manifest_dict=manifest,
                manifest_ref_hash=result["manifest_ref_hash"],
                signing_payload_hash=result["signing_payload_hash"],
                chain_dir=chain_dir
            )
        else:
            chain_path = chain_emit.emit_phase_0_chain(
                view=view_hash,
                base_scores=dummy_base_scores,
                final_portfolio=dummy_final_portfolio,
                run_id=run_id,
                skill_version=skill_version,
                chain_dir=chain_dir
            )
        
        # --- VERIFY OUTPUT ---
        assert chain_path.exists()
        
        with open(chain_path) as f:
            chain = yaml.safe_load(f)
        
        assert chain["view"] == view_hash
        assert chain["skill"] == "parallax-load-house-view"
        assert chain["manifest_ref"]["calibration_version"] == "test-2026-Q2.1"
        print(f"✓ Integration test passed. Chain emitted to {chain_path}")

def test_phase_0_fallback_flow():
    """Verify fallback to Phase 0 when no manifest is present."""
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        cache_dir = tmp_dir / "cache"
        chain_dir = tmp_dir / "chains"
        cache_dir.mkdir()
        chain_dir.mkdir()

        # No manifest in cache

        # --- SIMULATE SKILL STEP 4 ---
        view_hash = "abc123fallback"
        uploader_role = "PM"
        basis_statement = "Tactical adjustment"
        parent_version_id = "parent-uuid"

        # Step 4.1a: Load manifest (will fail to find anything)
        cache = manifest_cache.ManifestCache(cache_dir, TRUSTED_KEYS_PATH)
        try:
            manifest = manifest_cache.load_manifest(
                fresh_manifest=None,
                cache=cache
            )
            status = "ACTIVE"
        except Exception as e:
            # Expected path: DeadStateNoFallback or similar if cache is empty
            print(f"Manifest load failed (falling back to Phase 0): {e}")
            manifest = None
            status = "PHASE_0_FALLBACK"

        assert status == "PHASE_0_FALLBACK"
        assert manifest is None

        # Step 4.6b: Determine calibration_status
        prov = (manifest or {}).get("provenance", {})
        if (status == "ACTIVE" and 
            prov.get("methodology_section") != "GUESS" and 
            prov.get("backtest_ref") is not None):
            calibration_status = "empirical_phase1"
        else:
            calibration_status = "heuristic_phase0"
        
        assert calibration_status == "heuristic_phase0"

        # Step 4.11a: Emit Reasoning Chain
        dummy_base_scores = {
            "response_inline": {},
            "response_hash": "0" * 64,
        }
        dummy_final_portfolio = {
            "weights": {},
        }
        run_id = "01HZ" + "0" * 22 # Dummy run_id
        skill_version = "parallax-load-house-view@0.5.0"

        if status == "ACTIVE":
            # In actual skill, manifest_ref_hash and signing_payload_hash would come from verify_manifest result
            import manifest_verify
            result = manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)
            
            chain_path = chain_emit.emit_chain(
                view=view_hash, # Using view_hash as dummy for the view content here
                base_scores=dummy_base_scores,
                final_portfolio=dummy_final_portfolio,
                run_id=run_id,
                skill_version=skill_version,
                manifest_dict=manifest,
                manifest_ref_hash=result["manifest_ref_hash"],
                signing_payload_hash=result["signing_payload_hash"],
                chain_dir=chain_dir
            )
        else:
            chain_path = chain_emit.emit_phase_0_chain(
                view=view_hash,
                base_scores=dummy_base_scores,
                final_portfolio=dummy_final_portfolio,
                run_id=run_id,
                skill_version=skill_version,
                chain_dir=chain_dir
            )
        
        # --- VERIFY OUTPUT ---
        assert chain_path.exists()
        
        with open(chain_path) as f:
            chain = yaml.safe_load(f)
        
        assert chain["view"] == view_hash
        assert chain["manifest_ref"]["calibration_version"] == "phase-0-bundled"
        print(f"✓ Phase 0 fallback test passed. Chain emitted to {chain_path}")

if __name__ == "__main__":
    import yaml
    from datetime import datetime
    try:
        test_full_integration_flow()
        test_phase_0_fallback_flow()
        print("\nALL INTEGRATION TESTS PASSED")
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
