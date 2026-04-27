"""Unit tests for audit_chain logic (Approach B)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import audit_chain  # noqa: E402


def test_hash_determinism():
    """Verify that compute_entry_hash is deterministic (JCS rules)."""
    entry1 = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
    entry2 = {"a": 2, "z": 1, "m": {"a": 4, "b": 3}}
    
    h1 = audit_chain.compute_entry_hash(entry1)
    h2 = audit_chain.compute_entry_hash(entry2)
    
    assert h1 == h2
    # Verify exact JCS behavior (no whitespace, sorted keys)
    assert h1 == "e45c30b44d3d323ad520c1705dc1debea784800c25887d83cc182f4895836442"


def test_append_and_verify_chain(tmp_path: Path):
    """Verify full append and verification flow."""
    audit_path = tmp_path / "audit.jsonl"
    
    # 1. Append root
    r1 = audit_chain.append_entry(audit_path, {"action": "root"})
    assert r1["chain_root"] is True
    assert "prev_entry_hash" not in r1
    
    # 2. Append second
    r2 = audit_chain.append_entry(audit_path, {"action": "second"})
    assert "prev_entry_hash" in r2
    assert r2["prev_entry_hash"] == audit_chain.compute_entry_hash(r1)
    
    # 3. Verify
    entries = audit_chain.verify_chain(audit_path)
    assert len(entries) == 2
    assert entries[0]["action"] == "root"
    assert entries[1]["action"] == "second"


def test_migration_boundary(tmp_path: Path):
    """Verify transition from unchained legacy entries to chained entries."""
    audit_path = tmp_path / "audit.jsonl"
    
    # Pre-populate with legacy
    legacy = {"schema_version": 1, "ts": "2026-04-01", "action": "legacy"}
    with open(audit_path, "w") as f:
        f.write(json.dumps(legacy) + "\n")
        
    # Append new (should trigger migration)
    r1 = audit_chain.append_entry(audit_path, {"action": "first_chained"})
    assert r1["chain_root"] is True
    assert "prev_entry_hash" not in r1
    
    # Append next
    r2 = audit_chain.append_entry(audit_path, {"action": "next"})
    assert r2["prev_entry_hash"] == audit_chain.compute_entry_hash(r1)
    
    # Verify whole file
    entries = audit_chain.verify_chain(audit_path)
    assert len(entries) == 3
    assert entries[0]["action"] == "legacy"
    assert entries[1]["action"] == "first_chained"
    assert entries[1]["chain_root"] is True


def test_broken_chain_detection(tmp_path: Path):
    """Verify that tampering with an entry breaks verification."""
    audit_path = tmp_path / "audit.jsonl"
    
    audit_chain.append_entry(audit_path, {"action": "root"})
    audit_chain.append_entry(audit_path, {"action": "child"})
    
    # Tamper with the file
    lines = audit_path.read_text().splitlines()
    # Modify the 'root' entry (change action name)
    root_entry = json.loads(lines[0])
    root_entry["action"] = "tampered"
    lines[0] = json.dumps(root_entry)
    audit_path.write_text("\n".join(lines) + "\n")
    
    # Verify should fail
    try:
        audit_chain.verify_chain(audit_path)
        assert False, "Verification should have failed"
    except audit_chain.AuditChainBroken as e:
        assert "Hash chain break" in str(e)


def test_missing_link_detection(tmp_path: Path):
    """Verify that missing prev_entry_hash in chained section is caught."""
    audit_path = tmp_path / "audit.jsonl"
    
    audit_chain.append_entry(audit_path, {"action": "root"})
    
    # Manually append an unchained entry after root
    with open(audit_path, "a") as f:
        f.write(json.dumps({"action": "rogue"}) + "\n")
        
    try:
        audit_chain.verify_chain(audit_path)
        assert False, "Verification should have caught missing link"
    except audit_chain.AuditChainBroken as e:
        assert "Missing prev_entry_hash" in str(e)


def _worker_append(audit_path_str: str, idx: int) -> None:
    """Worker entrypoint for concurrent-write test; module-level so fork can pickle."""
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
    import audit_chain as _ac
    _ac.append_entry(_Path(audit_path_str), {"action": "concurrent", "idx": idx})


def test_concurrent_first_write_no_truncation(tmp_path: Path):
    """Bug regression: 10 processes racing on a fresh audit path must
    produce 10 entries, not silently lose entries to wb+ truncation."""
    import multiprocessing
    audit_path = tmp_path / "audit.jsonl"
    n = 10
    ctx = multiprocessing.get_context("fork")
    procs = [
        ctx.Process(target=_worker_append, args=(str(audit_path), i))
        for i in range(n)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0, f"worker exited with {p.exitcode}"

    lines = [ln for ln in audit_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == n, f"expected {n} entries, got {len(lines)}"
    entries = [json.loads(ln) for ln in lines]
    seen_idx = sorted(e["idx"] for e in entries)
    assert seen_idx == list(range(n))
    # Chain must still verify after the race
    audit_chain.verify_chain(audit_path)


def test_large_entry_tail_read(tmp_path: Path):
    """Bug regression: an entry larger than the legacy 32KB tail buffer
    must not cause the next append to lose the chain anchor and emit a
    second chain_root."""
    audit_path = tmp_path / "audit.jsonl"

    # Root entry
    audit_chain.append_entry(audit_path, {"action": "root"})

    # Second entry with >32KB payload (well past the legacy bound)
    big_blob = "x" * (64 * 1024)
    r2 = audit_chain.append_entry(
        audit_path, {"action": "big", "version_diff": {"payload": big_blob}}
    )
    assert "prev_entry_hash" in r2
    assert "chain_root" not in r2

    # Third entry — this is where the legacy bug manifested: tail read
    # of the >32KB middle entry returned [], is_chained went False,
    # append emitted a second chain_root.
    r3 = audit_chain.append_entry(audit_path, {"action": "third"})
    assert "prev_entry_hash" in r3
    assert "chain_root" not in r3
    assert r3["prev_entry_hash"] == audit_chain.compute_entry_hash(r2)

    # Whole-file verification must succeed.
    entries = audit_chain.verify_chain(audit_path)
    assert len(entries) == 3
    chain_roots = [e for e in entries if e.get("chain_root") is True]
    assert len(chain_roots) == 1, "exactly one chain_root expected"


def test_tail_read_ceiling_raises(tmp_path: Path, monkeypatch):
    """Bug regression: oversized entry beyond ceiling raises
    AuditTailReadFailed rather than silently corrupting the chain."""
    audit_path = tmp_path / "audit.jsonl"
    audit_chain.append_entry(audit_path, {"action": "root"})

    monkeypatch.setattr(audit_chain, "_TAIL_READ_INITIAL_BYTES", 256)
    monkeypatch.setattr(audit_chain, "_TAIL_READ_MAX_BYTES", 1024)

    # Directly append an oversized line, bypassing append_entry
    oversized = json.dumps({"action": "huge", "blob": "x" * 4096}) + "\n"
    with open(audit_path, "ab") as f:
        f.write(oversized.encode("utf-8"))

    try:
        audit_chain.append_entry(audit_path, {"action": "next"})
    except audit_chain.AuditTailReadFailed as e:
        assert "exceeded" in str(e).lower() or "ceiling" in str(e).lower()
    else:
        assert False, "expected AuditTailReadFailed"


if __name__ == "__main__":
    # Manual run support
    import pytest
    sys.exit(pytest.main([__file__]))
