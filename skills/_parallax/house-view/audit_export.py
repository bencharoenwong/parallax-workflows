"""Audit log export utility for regulator-grade bundles (Approach B).

Packages view artifacts and the hash-chained audit trail into a portable tarball.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rfc8785
import yaml

try:
    from . import audit_chain
except ImportError:
    import audit_chain

_BUNDLE_PREFIX = "parallax-audit"


class ExportError(Exception):
    error_code: str = "export_error"


def create_bundle(
    view_id: str,
    active_view_dir: Path,
    audit_path: Path,
    output_path: Path | None = None
) -> Path:
    """Create a compliance export bundle for a specific view_id."""
    
    # 1. Snapshot the live audit log to prevent TOCTOU corruption.
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        audit_snapshot = tmp_dir / "audit.jsonl"
        shutil.copy2(audit_path, audit_snapshot)

        # 2. Verify chain integrity on the snapshot.
        audit_chain.verify_chain(audit_snapshot)

        # 3. Collect artifacts
        view_yaml = active_view_dir / "view.yaml"
        prose_md = active_view_dir / "prose.md"
        provenance_yaml = active_view_dir / "provenance.yaml"

        if not view_yaml.exists():
            raise ExportError(f"Missing view.yaml in {active_view_dir}")
        if not provenance_yaml.exists():
            raise ExportError(f"Missing provenance.yaml in {active_view_dir} (required for Approach B)")

        # Validate view_id
        with open(view_yaml, "r") as f:
            view_data = yaml.safe_load(f)
            actual_id = view_data.get("metadata", {}).get("view_id")
            if actual_id != view_id:
                raise ExportError(f"Active view_id '{actual_id}' != requested '{view_id}'")

        # 4. Create Integrity Manifest
        manifest: dict[str, str] = {}

        def _add_to_manifest(path: Path, archive_name: str) -> None:
            if not path.exists():
                return
            h = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest[archive_name] = h

        _add_to_manifest(view_yaml, "view.yaml")
        _add_to_manifest(prose_md, "prose.md")
        _add_to_manifest(provenance_yaml, "provenance.yaml")
        _add_to_manifest(audit_snapshot, "audit.jsonl")

        # 5. Build the tarball
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if output_path is None:
            output_path = Path.cwd() / f"{_BUNDLE_PREFIX}-{view_id}-{ts}.tar.gz"

        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(view_yaml, arcname="view.yaml")
            if prose_md.exists():
                tar.add(prose_md, arcname="prose.md")
            tar.add(provenance_yaml, arcname="provenance.yaml")
            tar.add(audit_snapshot, arcname="audit.jsonl")
            
            manifest_data = json.dumps(manifest, indent=2).encode("utf-8")
            with tempfile.NamedTemporaryFile() as tmp:
                tmp.write(manifest_data)
                tmp.flush()
                tar.add(tmp.name, arcname="integrity_manifest.json")

    # Set permissions: 0600
    output_path.chmod(0o600)
    return output_path
