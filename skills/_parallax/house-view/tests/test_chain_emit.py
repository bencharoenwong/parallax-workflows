#!/usr/bin/env python3
"""Tests for chain_emit.py + chain_prune.py (Batch 4).

Coverage:
  Emit:
    1. Verified-manifest path → chain.yaml has live manifest_ref values.
    2. Phase-0 path → manifest_ref carries the bundled placeholder.
    3. Anti-collision defensive guard fires when caller passes equal hashes.
    4. sections_touched suppresses anchors with `active: false`.
    5. run_id collision refuses to overwrite by default.
    6. Atomic write applies 0600 file mode + 0700 month-dir mode.
    7. Phase-0 wrapper records the heuristic_phase0 notes.

  Prune:
    8. Dry-run lists candidates without deleting.
    9. --confirm deletes pre-cutoff chains, leaves post-cutoff intact.
   10. Symlinked chain_dir refuses to operate.
   11. --before YYYY-MM-DD parses correctly; bad format errors out.

Run from `skills/_parallax/house-view/`:

    python3 tests/test_chain_emit.py
"""
from __future__ import annotations

import base64
import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rfc8785
import yaml
from nacl.signing import SigningKey

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import chain_emit  # noqa: E402
import chain_prune  # noqa: E402
import manifest_verify  # noqa: E402

TRUSTED_KEYS_PATH = HOUSE_VIEW_DIR / "signing" / "trusted_keys.json"
PRIV_KEY_PATH = HERE / "fixtures" / "test-signing-key.priv"


# --- Helpers ---------------------------------------------------------

def _signing_key() -> SigningKey:
    return SigningKey(base64.b64decode(PRIV_KEY_PATH.read_text().strip(), validate=True))


def _test_kid() -> str:
    keys = json.loads(TRUSTED_KEYS_PATH.read_text())["keys"]
    return next(k["kid"] for k in keys if k.get("use") == "test-only")


def _build_signed_manifest(
    *,
    sections_with_active_false: list[str] = (),
    calibration_version: str = "test-2026-Q2.1",
) -> dict:
    sk = _signing_key()
    kid = _test_kid()
    values = {
        "sec-sensitivity-bands": {
            "warn_multiplier": 1.5,
            "bands": {"default": {"median_shift_min_bp": -25, "median_shift_max_bp": 25}},
        },
    }
    for s in sections_with_active_false:
        values[s] = {"active": False, "values": {}}
    body = {
        "schema_version": "1.0.0",
        "calibration_version": calibration_version,
        "org_id": "parallax-default",
        "issued_at": "2026-04-25T12:00:00Z",
        "manifest_expires_at": "2027-01-01T00:00:00Z",
        "signing_key_id": kid,
        "values": values,
    }
    payload = rfc8785.dumps(body)
    sig = sk.sign(payload).signature
    body["signature"] = {"alg": "ed25519", "value": base64.b64encode(sig).decode("ascii")}
    return body


def _verify(manifest: dict) -> dict:
    return manifest_verify.verify_manifest(manifest, TRUSTED_KEYS_PATH)


def _minimal_emit_kwargs(tmpdir: Path) -> dict:
    return {
        "view": {"metadata": {"view_name": "T"}, "tilts": {"factors": {}}},
        "base_scores": {
            "response_inline": {"scores": {"AAPL.O": 7.5}},
            "response_hash": "0" * 64,
        },
        "final_portfolio": {
            "weights": {"AAPL.O": 1.0},
            "sensitivity_band_check": {"status": "PASS"},
        },
        "run_id": "01HZTEST" + os.urandom(4).hex().upper(),
        "skill_version": "parallax-load-house-view@0.0.0-test",
        "chain_dir": tmpdir,
    }


# --- Emit tests ------------------------------------------------------

def test_emit_with_verified_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        m = _build_signed_manifest()
        result = _verify(m)
        kwargs = _minimal_emit_kwargs(Path(tmpdir))
        kwargs.update(
            manifest_dict=m,
            manifest_ref_hash=result["manifest_ref_hash"],
            signing_payload_hash=result["signing_payload_hash"],
            sections_touched=["sec-sensitivity-bands"],
        )
        path = chain_emit.emit_chain(**kwargs)
        assert path.exists()
        chain = yaml.safe_load(path.read_text())
        ref = chain["manifest_ref"]
        assert ref["calibration_version"] == "test-2026-Q2.1"
        assert ref["hash"] == f"sha256:{result['manifest_ref_hash']}"
        assert ref["signing_key_id"] == m["signing_key_id"]
        assert ref["sections_touched"] == ["sec-sensitivity-bands"]
        assert chain["signature"] == {"alg": "none", "value": None}
        assert chain["org_id"] == "parallax-default"
    print("PASS  test_emit_with_verified_manifest")


def test_emit_phase_0() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        kwargs = _minimal_emit_kwargs(Path(tmpdir))
        path = chain_emit.emit_phase_0_chain(
            view=kwargs["view"],
            base_scores=kwargs["base_scores"],
            final_portfolio=kwargs["final_portfolio"],
            run_id=kwargs["run_id"],
            skill_version=kwargs["skill_version"],
            chain_dir=Path(tmpdir),
        )
        chain = yaml.safe_load(path.read_text())
        ref = chain["manifest_ref"]
        assert ref["calibration_version"] == "phase-0-bundled"
        assert ref["hash"] is None
        assert ref["signing_key_id"] is None
        assert chain["org_id"] == chain_emit.PHASE_0_ORG_ID
        assert "phase-0-bundled" in (ref["notes"] or "")
    print("PASS  test_emit_phase_0")


def test_anti_collision_defensive_guard() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        m = _build_signed_manifest()
        kwargs = _minimal_emit_kwargs(Path(tmpdir))
        kwargs.update(
            manifest_dict=m,
            manifest_ref_hash="a" * 64,
            signing_payload_hash="a" * 64,  # forced equal
        )
        try:
            chain_emit.emit_chain(**kwargs)
        except chain_emit.ChainAntiCollisionTripped as e:
            assert e.error_code == "manifest_signature_missing"
            print("PASS  test_anti_collision_defensive_guard")
            return
    raise AssertionError("anti-collision guard did not fire on equal hashes")


def test_sections_touched_suppresses_active_false() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        m = _build_signed_manifest(
            sections_with_active_false=["sec-pillar-to-factor-routing"]
        )
        result = _verify(m)
        kwargs = _minimal_emit_kwargs(Path(tmpdir))
        kwargs.update(
            manifest_dict=m,
            manifest_ref_hash=result["manifest_ref_hash"],
            signing_payload_hash=result["signing_payload_hash"],
            sections_touched=[
                "sec-sensitivity-bands",
                "sec-pillar-to-factor-routing",  # has active=false
            ],
        )
        path = chain_emit.emit_chain(**kwargs)
        chain = yaml.safe_load(path.read_text())
        sections = chain["manifest_ref"]["sections_touched"]
        assert "sec-sensitivity-bands" in sections
        assert "sec-pillar-to-factor-routing" not in sections, (
            f"active=false anchor leaked into chain: {sections}"
        )
    print("PASS  test_sections_touched_suppresses_active_false")


def test_run_id_collision_refuses_overwrite() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        kwargs = _minimal_emit_kwargs(Path(tmpdir))
        chain_emit.emit_chain(**kwargs)
        try:
            chain_emit.emit_chain(**kwargs)  # same run_id, no overwrite
        except FileExistsError:
            print("PASS  test_run_id_collision_refuses_overwrite")
            return
    raise AssertionError("second emit with same run_id silently overwrote")


def test_atomic_write_perms() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        kwargs = _minimal_emit_kwargs(Path(tmpdir))
        path = chain_emit.emit_chain(**kwargs)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, "chain file mode != 0600"
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700, "month dir mode != 0700"
    print("PASS  test_atomic_write_perms")


def test_phase_0_notes_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        kwargs = _minimal_emit_kwargs(Path(tmpdir))
        path = chain_emit.emit_phase_0_chain(
            view=kwargs["view"],
            base_scores=kwargs["base_scores"],
            final_portfolio=kwargs["final_portfolio"],
            run_id=kwargs["run_id"],
            skill_version=kwargs["skill_version"],
            chain_dir=Path(tmpdir),
        )
        chain = yaml.safe_load(path.read_text())
        assert "phase-0-bundled" in chain["manifest_ref"]["notes"]
    print("PASS  test_phase_0_notes_default")


# --- Prune tests ----------------------------------------------------

def _plant_chain_at(chain_dir: Path, ymd: tuple[int, int, int], run_id: str) -> Path:
    """Write a chain file and back-date its mtime to ymd noon UTC."""
    y, m, d = ymd
    month_dir = chain_dir / f"{y}-{m:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)
    month_dir.chmod(0o700)
    p = month_dir / f"{run_id}.yaml"
    p.write_text("placeholder: true\n")
    p.chmod(0o600)
    target = datetime(y, m, d, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    os.utime(p, (target, target))
    return p


def test_prune_dry_run_does_not_delete() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cd = Path(tmpdir)
        old = _plant_chain_at(cd, (2025, 1, 15), "01HZOLD" + "A" * 8)
        new = _plant_chain_at(cd, (2026, 4, 20), "01HZNEW" + "B" * 8)
        rc = chain_prune.main(["--before", "2026-01-01", "--chain-dir", str(cd)])
        assert rc == 0
        # Both still on disk.
        assert old.exists()
        assert new.exists()
    print("PASS  test_prune_dry_run_does_not_delete")


def test_prune_confirm_deletes_pre_cutoff() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cd = Path(tmpdir)
        # Sleep briefly so the planted mtimes are firmly < process_start
        # (the concurrency guard refuses to delete files modified after
        # process start; planting at 2025-* mtime is far before that, fine).
        old = _plant_chain_at(cd, (2025, 1, 15), "01HZOLD" + "C" * 8)
        new = _plant_chain_at(cd, (2026, 4, 20), "01HZNEW" + "D" * 8)
        rc = chain_prune.main(
            ["--before", "2026-01-01", "--chain-dir", str(cd), "--confirm"]
        )
        assert rc == 0
        assert not old.exists(), "pre-cutoff chain should have been deleted"
        assert new.exists(), "post-cutoff chain should have been preserved"
    print("PASS  test_prune_confirm_deletes_pre_cutoff")


def test_prune_refuses_symlinked_chain_dir() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        real = Path(tmpdir) / "real"
        real.mkdir()
        link = Path(tmpdir) / "link"
        link.symlink_to(real)
        try:
            chain_prune.main(["--before", "2026-01-01", "--chain-dir", str(link)])
        except SystemExit as e:
            assert e.code != 0
            print("PASS  test_prune_refuses_symlinked_chain_dir")
            return
    raise AssertionError("prune did not refuse symlinked chain_dir")


def test_prune_bad_date_format() -> None:
    try:
        chain_prune.main(["--before", "April 2026", "--chain-dir", "/nonexistent"])
    except SystemExit as e:
        assert e.code != 0
        print("PASS  test_prune_bad_date_format")
        return
    raise AssertionError("prune accepted invalid --before date")


# --- Runner ----------------------------------------------------------

def main() -> int:
    tests = [
        test_emit_with_verified_manifest,
        test_emit_phase_0,
        test_anti_collision_defensive_guard,
        test_sections_touched_suppresses_active_false,
        test_run_id_collision_refuses_overwrite,
        test_atomic_write_perms,
        test_phase_0_notes_default,
        test_prune_dry_run_does_not_delete,
        test_prune_confirm_deletes_pre_cutoff,
        test_prune_refuses_symlinked_chain_dir,
        test_prune_bad_date_format,
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
