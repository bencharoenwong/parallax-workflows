"""Unit tests for grade_corpus pure helpers — no live data, no filesystem.

Guards the two behaviors that matter: (1) infra failures (auth/empty/connector) are detected
and never mistaken for skill output, and (2) the variance signals are extracted the same way
the tier-1 checks read them (adjacency-bound glyphs)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from grade_corpus import (  # noqa: E402
    detect_infra_failure,
    extract_readings,
    id_from_filename,
    stability,
)

_INIT_OK = '{"type":"system","subtype":"init","mcp_servers":[{"name":"claude_ai_Parallax"}]}'
_RESULT = '{"type":"result","subtype":"success","result":"# report"}'


# --- detect_infra_failure --------------------------------------------------

def test_infra_empty_stream():
    assert detect_infra_failure("   ") is not None


def test_infra_auth_401():
    raw = _INIT_OK + '\n{"type":"system","subtype":"api_retry","error_status":401,"error":"authentication_failed"}'
    assert "401" in detect_infra_failure(raw)


def test_infra_no_result_event():
    # connector present, but the run never produced a result event (aborted)
    raw = _INIT_OK
    assert "no result" in detect_infra_failure(raw).lower()


def test_infra_connector_missing():
    raw = '{"type":"system","subtype":"init","mcp_servers":[]}\n' + _RESULT
    assert "connector" in detect_infra_failure(raw).lower()


def test_infra_none_on_healthy_run():
    raw = _INIT_OK + "\n" + _RESULT
    assert detect_infra_failure(raw) is None


# --- extract_readings ------------------------------------------------------

_PROSE = """## TL;DR
- Assumption Strength: 🔴 Weak — keystone contradicted.

## Coverage Notice
Partial coverage — an FX regime read, not the instrument.

## Pass 1 — Load-Bearing Vulnerabilities
macro-1 and macro-2 carry the thesis; implicit-1 also fails.

## Bias & Conviction Check
🟡 Elevated — confirmation bias; it is not 🔴 High because the claims stay falsifiable.
"""


def test_extract_strength_light():
    assert extract_readings(_PROSE)["strength"] == "🔴 Weak"


def test_extract_hype_ignores_negated_sibling():
    # "not 🔴 High" must not flip the reading away from the bound 🟡 Elevated
    assert extract_readings(_PROSE)["hype"] == "🟡 Elevated"


def test_extract_coverage():
    assert extract_readings(_PROSE)["coverage"] == "partial"


def test_extract_load_bearing_ids():
    assert extract_readings(_PROSE)["load_bearing"] == ["macro-1", "macro-2", "implicit-1"]


# --- id_from_filename ------------------------------------------------------

def test_id_from_filename_roundtrip():
    name = "stress-test-thesis_live-macro_led_long-2_I_like_long_824_20260710T000000Z.stream.json"
    assert id_from_filename(name, "stress-test-thesis", "live") == "macro_led_long"


def test_id_from_filename_rejects_foreign():
    assert id_from_filename("other_prefix_x.stream.json", "stress-test-thesis", "live") is None


# --- stability -------------------------------------------------------------

def test_stability_stable():
    s = stability(["🔴 Weak", "🔴 Weak", "🔴 Weak"])
    assert s["stable"] is True and s["n"] == 3 and s["unique"] == ["🔴 Weak"]


def test_stability_unstable():
    s = stability(["🔴 Weak", "🟡 Mixed"])
    assert s["stable"] is False and len(s["unique"]) == 2


def test_stability_handles_list_values():
    # load_bearing readings are lists — must be hashable-normalized, not crash
    s = stability([["macro-1", "macro-2"], ["macro-1", "macro-2"]])
    assert s["stable"] is True
