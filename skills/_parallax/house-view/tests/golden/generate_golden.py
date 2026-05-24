import sys
from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib
import yaml
import rfc8785

REPO = Path("/Users/bencharoenwong/parallax-workflows")
sys.path.insert(0, str(REPO / "skills" / "_parallax" / "house-view"))
import audit_chain
import chain_emit

def main():
    golden_dir = REPO / "skills" / "_parallax" / "house-view" / "tests" / "golden" / "pre_v2_house_view"
    golden_dir.mkdir(parents=True, exist_ok=True)
    
    view_data = {
        "metadata": {
            "view_name": "E2E Golden Baseline View",
            "view_id": "view-12345",
            "version_id": "ver-00001",
            "effective_date": "2026-04-26",
            "upload_timestamp": datetime.now(timezone.utc).isoformat()
        },
        "tilts": {
            "factors": {"low_volatility": 2, "momentum": -1},
            "sectors": {"consumer_staples": 1}
        }
    }

    provenance_data = {
        "schema_version": 1,
        "view_id": "view-12345",
        "version_id": "ver-00001",
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
    
    prov_hash = hashlib.sha256(rfc8785.dumps(provenance_data)).hexdigest()
    view_data["metadata"]["provenance_hash"] = prov_hash
    view_hash = hashlib.sha256(rfc8785.dumps(view_data["tilts"])).hexdigest()
    view_data["metadata"]["view_hash"] = view_hash
    
    (golden_dir / "view.yaml").write_text(yaml.safe_dump(view_data))
    (golden_dir / "provenance.yaml").write_text(yaml.safe_dump(provenance_data))
    (golden_dir / "prose.md").write_text("---\npaired_yaml_hash: " + view_hash + "\n---\nVerbatim prose body")
    
    audit_path = golden_dir / "audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()
        
    audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "view_id": "view-12345",
        "version_id": "ver-00001",
        "view_hash": view_hash,
        "action": "save",
        "applied": True,
        "provenance_hash": prov_hash
    }
    audit_chain.append_entry(audit_path, audit_entry)
    print("Golden baseline generated at", golden_dir)

if __name__ == "__main__":
    main()
