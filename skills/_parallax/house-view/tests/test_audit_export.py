"""Unit tests for audit_export logic (Approach B)."""
from __future__ import annotations

import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import audit_chain  # noqa: E402
import audit_export  # noqa: E402


def test_create_bundle(tmp_path: Path):
    """Verify bundle creation and contents."""
    active_dir = tmp_path / "active"
    active_dir.mkdir()
    
    view_id = "test-view-123"
    view_yaml = active_dir / "view.yaml"
    view_yaml.write_text(f"metadata:\n  view_id: {view_id}\ntilts: {{}}")
    
    provenance_yaml = active_dir / "provenance.yaml"
    provenance_yaml.write_text("schema_version: 1\ntilts: {}")
    
    prose_md = active_dir / "prose.md"
    prose_md.write_text("Verbatim narrative")
    
    audit_path = tmp_path / "audit.jsonl"
    audit_chain.append_entry(audit_path, {"action": "save", "view_id": view_id})
    
    output_bundle = tmp_path / "bundle.tar.gz"
    
    # Create bundle
    bundle_path = audit_export.create_bundle(
        view_id=view_id,
        active_view_dir=active_dir,
        audit_path=audit_path,
        output_path=output_bundle
    )
    
    assert bundle_path.exists()
    assert bundle_path == output_bundle
    
    # Verify contents
    with tarfile.open(bundle_path, "r:gz") as tar:
        names = tar.getnames()
        assert "view.yaml" in names
        assert "prose.md" in names
        assert "audit.jsonl" in names
        assert "integrity_manifest.json" in names
        
        # Verify manifest correctness
        manifest_file = tar.extractfile("integrity_manifest.json")
        manifest = json.loads(manifest_file.read())
        assert "view.yaml" in manifest
        assert "audit.jsonl" in manifest


def test_export_broken_chain_refusal(tmp_path: Path):
    """Verify that export refuses to run on a broken audit log."""
    active_dir = tmp_path / "active"
    active_dir.mkdir()
    view_id = "v1"
    (active_dir / "view.yaml").write_text(f"metadata:\n  view_id: {view_id}\ntilts: {{}}")
    
    audit_path = tmp_path / "audit.jsonl"
    audit_chain.append_entry(audit_path, {"action": "root"})
    
    # Tamper
    with open(audit_path, "a") as f:
        f.write('{"action": "tampered", "prev_entry_hash": "bad"}\n')
        
    try:
        audit_export.create_bundle(view_id, active_dir, audit_path)
        assert False, "Export should have failed on broken chain"
    except audit_chain.AuditChainBroken:
        pass


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__]))
