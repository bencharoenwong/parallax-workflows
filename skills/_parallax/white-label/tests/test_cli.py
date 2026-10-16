"""The one-line commands integration-pattern.md §2 documents: ``loader.py --json``
and ``rm_consumer.py --label/--resolve-audience``. Each runs as a subprocess
with HOME pointed at a temp dir, the way a skill's `run-shell` call runs it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_WHITE_LABEL_DIR = Path(__file__).resolve().parent.parent
LOADER = _WHITE_LABEL_DIR / "loader.py"
RM_CONSUMER = _WHITE_LABEL_DIR / "rm_consumer.py"


def _config(render: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "metadata": {
            "schema_version": 1,
            "client_name": "Acme Capital",
            "extracted_at": "2026-04-30T00:00:00Z",
            "source": {"type": "url",
                       "reference": "https://acme.example.com/internal/brand-kit",
                       "confidence": 0.95},
        },
        "branding": {
            "colors": {"primary": "#1A2B3C", "secondary": "#FFFFFF", "accent": "#FF6600",
                       "background": "#F5F5F5", "text": "#333333"},
            "logos": {"primary": "", "favicon": ""},
            "fonts": {"header": "Inter", "body": "Roboto", "monospace": "JetBrains Mono"},
        },
        "confidence_scores": {"primary_color": 0.99, "primary_logo": 0.85, "favicon": 0.85},
    }
    if render is not None:
        cfg["render"] = render
    return cfg


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path


def _onboard(home: Path, cfg: dict[str, Any]) -> None:
    path = home / ".parallax" / "client-branding" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")


def _run(home: Path, script: Path, *args: str) -> dict[str, Any]:
    env = {**os.environ, "HOME": str(home)}
    proc = subprocess.run([sys.executable, str(script), *args], env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("\n") == 1, proc.stdout  # one JSON line on stdout
    return json.loads(proc.stdout)


def test_loader_json_onboarded_prints_visual_keys_and_safe_source(home: Path) -> None:
    _onboard(home, _config())
    out = _run(home, LOADER, "--json")
    assert set(out) == {"client_name", "colors", "logos", "fonts", "error", "render",
                        "source_reference", "white_label_active"}
    assert out["client_name"] == "Acme Capital"
    assert out["white_label_active"] is True
    assert out["error"] is None
    assert out["colors"]["primary"] == "#1A2B3C"
    assert out["source_reference"] == "https://acme.example.com"
    assert "voice" not in out


def test_loader_json_never_prints_the_raw_source(home: Path) -> None:
    _onboard(home, _config())
    proc = subprocess.run([sys.executable, str(LOADER), "--json"],
                          env={**os.environ, "HOME": str(home)},
                          capture_output=True, text=True, timeout=60)
    assert "internal/brand-kit" not in proc.stdout


def test_loader_json_not_onboarded_is_inactive(home: Path) -> None:
    out = _run(home, LOADER, "--json")
    assert out["error"] == "config_not_found"
    assert out["white_label_active"] is False
    assert out["source_reference"] == ""


def test_loader_requires_the_json_flag(home: Path) -> None:
    proc = subprocess.run([sys.executable, str(LOADER)], env={**os.environ, "HOME": str(home)},
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert proc.stdout == ""


def test_rm_consumer_label_renders_header_and_about_lines(home: Path) -> None:
    _onboard(home, _config())
    out = _run(home, RM_CONSUMER, "--label", "portfolio review")
    assert out["header_lines"] == ["**Acme Capital** portfolio review"]
    assert out["about_lines"][0] == "Branding: white-label (source: https://acme.example.com)"
    assert out["resolved_audience"] == "internal_analyst"


def test_rm_consumer_label_not_onboarded_is_default_parallax(home: Path) -> None:
    out = _run(home, RM_CONSUMER, "--label", "desk call list")
    assert out["header_lines"] == []
    assert out["about_lines"][0] == "Branding: default Parallax"


def test_rm_consumer_audience_flag_reaches_the_context(home: Path) -> None:
    out = _run(home, RM_CONSUMER, "--label", "portfolio review", "--audience", "client_safe")
    assert out["resolved_audience"] == "client_safe"
    assert out["about_lines"][-1] == "Audience mode: client-safe"


def test_rm_consumer_resolve_audience_reads_config_default(home: Path) -> None:
    _onboard(home, _config(render={"audience_default": "client_safe"}))
    assert _run(home, RM_CONSUMER, "--resolve-audience") == {"mode": "client_safe",
                                                             "notice": None}


def test_rm_consumer_resolve_audience_flag_wins_and_bad_flag_notices(home: Path) -> None:
    _onboard(home, _config(render={"audience_default": "client_safe"}))
    assert _run(home, RM_CONSUMER, "--resolve-audience", "--audience",
                "internal_analyst")["mode"] == "internal_analyst"
    bad = _run(home, RM_CONSUMER, "--resolve-audience", "--audience", "everyone")
    assert bad["mode"] == "internal_analyst"
    assert bad["notice"] and "everyone" not in bad["notice"]


def test_rm_consumer_needs_exactly_one_mode(home: Path) -> None:
    for args in ([], ["--label", "x", "--resolve-audience"]):
        proc = subprocess.run([sys.executable, str(RM_CONSUMER), *args],
                              env={**os.environ, "HOME": str(home)},
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 2, args
