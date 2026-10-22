"""Tests for render_judge.render_markdown_report + render_json_sidecar."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import render_judge


def _kwargs(**overrides):
    base = dict(
        view_meta={"view_name": "Test View"},
        judged_view_id="vid-123",
        judged_version_id="ver-456",
        view_age_days=42,
        parallax_age_days=3,
        severity="drift_minor",
        severity_details={
            "divergent_count": 1,
            "denominator": 10,
            "divergent_pct": 0.10,
            "pillar_divergence": False,
            "macro_sign_flip": False,
            "magnitude_escalated": False,
            "max_magnitude": 0,
            "view_age_days": 42,
        },
        drift_summary={
            "aligned_count": 8,
            "drift_minor_count": 1,
            "drift_material_count": 0,
            "drift_breaking_count": 0,
            "parallax_silent_count": 1,
            "uncovered_count": 0,
        },
        resolutions=[
            {"dim": "tilts.sectors.health_care", "state": "ALIGNED", "cio_tilt": 1, "parallax_view": 1, "market": None},
        ],
        recommendations=[],
        trigger="on_demand",
        judged_at=datetime.datetime(2026, 5, 24, 12, 0, tzinfo=datetime.timezone.utc),
    )
    base.update(overrides)
    return base


def test_render_minor_drift_includes_header_and_verdict():
    md = render_judge.render_markdown_report(**_kwargs())
    assert "# House View Judge Report" in md
    assert "drift_minor" in md
    assert "Minor drift detected" in md
    assert "Test View" in md


def test_render_material_drift_banner():
    md = render_judge.render_markdown_report(**_kwargs(severity="drift_material"))
    assert "drift_material" in md
    assert "Material drift detected" in md


def test_render_includes_pillar_callout_when_present():
    md = render_judge.render_markdown_report(**_kwargs(
        severity="drift_material",
        severity_details={
            "divergent_count": 1, "denominator": 10, "divergent_pct": 0.10,
            "pillar_divergence": True,
            "pillar_cells": ["tilts.pillars.econometrics_phase"],
            "macro_sign_flip": False, "magnitude_escalated": False,
            "max_magnitude": 0, "view_age_days": 42,
        },
    ))
    assert "Pillar divergence" in md
    assert "tilts.pillars.econometrics_phase" in md


def test_pillars_only_suppresses_per_cell_table():
    md_full = render_judge.render_markdown_report(**_kwargs())
    md_pillars = render_judge.render_markdown_report(**_kwargs(pillars_only=True))
    assert "Per-cell resolution" in md_full
    assert "Per-cell resolution" not in md_pillars


def test_render_includes_no_recommendations_when_empty():
    md = render_judge.render_markdown_report(**_kwargs())
    assert "No per-cell recommendations" in md


def test_render_includes_recommendations_table():
    recs = [
        {
            "path": "tilts.regions.japan",
            "recommended_value": -1,
            "confidence": 0.78,
            "rationale": "Japan tactical view has reversed; underweight warranted.",
            "declined": False,
        },
        {
            "path": "tilts.sectors.information_technology",
            "recommended_value": None,
            "confidence": 0.0,
            "rationale": "judge declined to recommend (citation check failed)",
            "declined": True,
        },
    ]
    md = render_judge.render_markdown_report(**_kwargs(
        severity="drift_material",
        recommendations=recs,
    ))
    assert "Recommendations" in md
    assert "tilts.regions.japan" in md
    assert "tilts.sectors.information_technology" in md
    # Decline marker visible.
    assert "declined" in md.lower()
    assert "1 recommendation(s); 1 declined" in md


def test_json_sidecar_round_trips():
    payload = render_judge.render_json_sidecar(**{
        k: v for k, v in _kwargs().items() if k != "pillars_only"
    })
    parsed = json.loads(payload)
    assert parsed["severity"] == "drift_minor"
    assert parsed["view_id"] == "vid-123"
    assert parsed["report_version"] == 1
    assert parsed["judged_at"].endswith("Z")


def test_write_report_bundle_creates_files(tmp_path: Path):
    out = tmp_path / "bundle-xyz"
    files = render_judge.write_report_bundle(
        output_dir=out,
        markdown="# hello\n",
        json_sidecar='{"a": 1}',
    )
    assert files["report.md"].exists()
    assert files["report.json"].exists()
    assert files["report.md"].read_text() == "# hello\n"
    assert json.loads(files["report.json"].read_text())["a"] == 1
