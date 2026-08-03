"""Fail-closed shape rules shared by the maker and the stress classifier."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mcp_meta  # noqa: E402


def test_real_macro_analyst_envelope_carries_data():
    """Shape verified against the live tool 2026-08-03."""
    assert mcp_meta.carries_data(
        {"success": True, "component": "macro_indicators", "content": "..."}
    )


def test_explicit_failure_is_silent_not_unreachable():
    """The server answered. That is silent-for-this-component, not a dead
    market -- conflating them would abort a run the data supports."""
    assert mcp_meta.carries_data({"success": False, "error": "no data"})
    assert mcp_meta.carries_data({"error": "permission_denied"})


def test_uninterpretable_shapes_fail_closed():
    for bad in (None, [], "text", 42, {}, {"content": "no envelope"}):
        assert not mcp_meta.carries_data(bad), f"{bad!r} must fail closed"
        assert mcp_meta.shape_unreachable_reason(bad)


def test_reason_is_none_exactly_when_usable():
    for resp in ({"success": True}, {"success": False}, {"error": "x"}):
        assert mcp_meta.shape_unreachable_reason(resp) is None
