"""Unit tests for view_status."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
HOUSE_VIEW_DIR = HERE.parent
sys.path.insert(0, str(HOUSE_VIEW_DIR))

import view_status  # noqa: E402


def _write_view(tmp_path: Path, meta: dict) -> Path:
    view_dir = tmp_path / "active-house-view"
    view_dir.mkdir()
    (view_dir / "view.yaml").write_text(yaml.safe_dump({"metadata": meta}))
    return view_dir


def test_none_when_dir_missing(tmp_path: Path):
    s = view_status.compute_status(view_dir=tmp_path / "does_not_exist")
    assert s.state == "none"
    assert s.tilts_apply is False
    assert "No active house view" in s.banner


def test_active_well_inside_window(tmp_path: Path):
    today = date(2026, 5, 1)
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "active"
    assert s.tilts_apply is True
    assert s.days_remaining == 60
    assert "Q2 2026" in s.banner


def test_warning_boundary_at_13_days(tmp_path: Path):
    today = date(2026, 6, 17)  # 13 days before 2026-06-30
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "warning"
    assert s.tilts_apply is True
    assert s.days_remaining == 13


def test_critical_at_9_days_prompts_refresh(tmp_path: Path):
    today = date(2026, 6, 21)  # 9 days before 2026-06-30
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "critical"
    assert s.tilts_apply is True
    assert s.days_remaining == 9
    assert "updated CIO view" in s.banner


def test_critical_exact_boundary_10_days_is_warning(tmp_path: Path):
    today = date(2026, 6, 20)  # 10 days before 2026-06-30
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "warning"
    assert s.days_remaining == 10


def test_warning_exact_boundary_14_days_is_active(tmp_path: Path):
    today = date(2026, 6, 16)  # 14 days before 2026-06-30
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "active"
    assert s.days_remaining == 14


def test_expired(tmp_path: Path):
    today = date(2026, 7, 5)  # 5 days past 2026-06-30
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "expired"
    assert s.tilts_apply is False
    assert "expired 5 day(s) ago" in s.banner


def test_not_yet_effective(tmp_path: Path):
    today = date(2026, 3, 20)
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "not_yet_effective"
    assert s.tilts_apply is False


def test_malformed_both_dates_null(tmp_path: Path):
    view_dir = _write_view(tmp_path, {
        "view_name": "Bad View",
        "effective_date": None,
        "valid_through": None,
    })
    s = view_status.compute_status(view_dir=view_dir, today=date(2026, 5, 1))
    assert s.state == "malformed"
    assert s.tilts_apply is False


def test_auto_expire_days_fallback(tmp_path: Path):
    today = date(2026, 5, 1)  # 30 days after effective
    view_dir = _write_view(tmp_path, {
        "view_name": "Q2 2026",
        "effective_date": "2026-04-01",
        "valid_through": None,
        "auto_expire_days": 90,
    })
    s = view_status.compute_status(view_dir=view_dir, today=today)
    assert s.state == "active"
    assert s.valid_through == "2026-06-30"
    assert s.days_remaining == 60


def test_malformed_unreadable_yaml(tmp_path: Path):
    view_dir = tmp_path / "active-house-view"
    view_dir.mkdir()
    (view_dir / "view.yaml").write_text("not: valid: yaml: [unclosed")
    s = view_status.compute_status(view_dir=view_dir, today=date(2026, 5, 1))
    assert s.state == "malformed"
    assert s.tilts_apply is False


def test_env_var_override(tmp_path: Path, monkeypatch):
    view_dir = _write_view(tmp_path, {
        "view_name": "Env Test",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    monkeypatch.setenv("PARALLAX_HOUSE_VIEW_DIR", str(view_dir))
    s = view_status.compute_status(today=date(2026, 5, 1))
    assert s.state == "active"
    assert s.view_name == "Env Test"


def test_json_round_trip(tmp_path: Path):
    view_dir = _write_view(tmp_path, {
        "view_name": "JSON Test",
        "effective_date": "2026-04-01",
        "valid_through": "2026-06-30",
    })
    s = view_status.compute_status(view_dir=view_dir, today=date(2026, 5, 1))
    d = s.to_dict()
    assert d["state"] == "active"
    assert d["view_name"] == "JSON Test"
    assert d["days_remaining"] == 60
    assert d["tilts_apply"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
