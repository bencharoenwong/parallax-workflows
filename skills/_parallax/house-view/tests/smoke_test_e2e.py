"""E2E Smoke Test for Approach B (Compliance Audit).

Simulates the full flow of load-house-view SKILL.md:
1. "Extraction" (Mocked)
2. Provenance Generation
3. Provenance Hashing
4. View Injection
5. View Hashing
6. Chained Audit Append
7. Reasoning Chain Emission
8. Export Validation
"""
import sys
import json
import hashlib
import shutil
import tarfile
from pathlib import Path
from datetime import datetime, timezone

import yaml
import rfc8785

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import audit_chain
import audit_export
import chain_emit
import gap_detect
import gap_suggest

def test_e2e_compliance_flow():
    tmp_base = Path("/tmp/parallax-e2e-test")
    if tmp_base.exists():
        shutil.rmtree(tmp_base)
    tmp_base.mkdir(parents=True)
    
    active_dir = tmp_base / "active"
    active_dir.mkdir()
    audit_path = tmp_base / "audit.jsonl"
    chains_dir = tmp_base / "chains"
    chains_dir.mkdir()
    cache_dir = tmp_base / "cache"
    cache_dir.mkdir()
    
    # --- STEP 1 & 2: MOCK EXTRACTION ---
    view_data = {
        "metadata": {
            "view_name": "E2E Smoke Test View",
            "view_id": "view-123",
            "version_id": "ver-001",
            "effective_date": "2026-04-26",
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        },
        "tilts": {
            "factors": {"low_volatility": 2, "momentum": -1},
            "sectors": {"consumer_staples": 1}
        }
    }
    
    # --- STEP 3: GENERATE PROVENANCE (Approach B) ---
    provenance_data = {
        "schema_version": 1,
        "view_id": "view-123",
        "version_id": "ver-001",
        "tilts": {
            "tilts.factors.low_volatility": {
                "value": 2,
                "derivation": [{
                    "type": "prose_extraction",
                    "source_span": "Strong overweight defensive factor exposure",
                    "confidence": 0.95
                }]
            }
        }
    }
    
    # --- STEP 4: HASHING SEQUENCE (Patch logical flaw check) ---
    # 1. Provenance Hash
    prov_hash = hashlib.sha256(rfc8785.dumps(provenance_data)).hexdigest()
    
    # 2. Inject into view
    view_data["metadata"]["provenance_hash"] = prov_hash
    
    # 3. View Hash (Simplified canonicalization for smoke test)
    view_hash = hashlib.sha256(rfc8785.dumps(view_data["tilts"])).hexdigest()
    view_data["metadata"]["view_hash"] = view_hash
    
    # --- STEP 5: WRITE FILES ---
    (active_dir / "view.yaml").write_text(yaml.safe_dump(view_data))
    (active_dir / "provenance.yaml").write_text(yaml.safe_dump(provenance_data))
    (active_dir / "prose.md").write_text("---\npaired_yaml_hash: " + view_hash + "\n---\nVerbatim prose body")
    
    # --- STEP 6: CHAINED AUDIT APPEND ---
    audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "view_id": "view-123",
        "version_id": "ver-001",
        "view_hash": view_hash,
        "action": "save",
        "applied": True,
        "provenance_hash": prov_hash
    }
    audit_chain.append_entry(audit_path, audit_entry)
    
    # --- STEP 7: REASONING CHAIN EMISSION ---
    chain_emit.emit_phase_0_chain(
        view=view_hash,
        base_scores={"response_inline": {}, "response_hash": "0"*64},
        final_portfolio={"weights": {}},
        run_id="01HZSMOKETEST00000000000",
        skill_version="parallax-load-house-view@1.0.0",
        chain_dir=chains_dir
    )
    
    # --- STEP 8: EXPORT ---
    bundle_path = audit_export.create_bundle(
        view_id="view-123",
        active_view_dir=active_dir,
        audit_path=audit_path,
        output_path=tmp_base / "bundle.tar.gz"
    )
    
    # --- VALIDATION ---
    assert bundle_path.exists()
    assert (chains_dir / datetime.now(timezone.utc).strftime("%Y-%m") / "01HZSMOKETEST00000000000.yaml").exists()
    
    # Verify Audit Chain
    entries = audit_chain.verify_chain(audit_path)
    assert len(entries) == 1
    assert entries[0]["chain_root"] is True
    assert entries[0]["provenance_hash"] == prov_hash
    
    # Verify Bundle Manifest
    with tarfile.open(bundle_path, "r:gz") as tar:
        manifest_f = tar.extractfile("integrity_manifest.json")
        manifest = json.loads(manifest_f.read())
        assert "provenance.yaml" in manifest
        assert "audit.jsonl" in manifest
        
    print("✓ E2E Smoke Test Passed: Provenance -> Hash -> Chain -> Export")
    shutil.rmtree(tmp_base)




if __name__ == "__main__":
    try:
        test_e2e_compliance_flow()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
