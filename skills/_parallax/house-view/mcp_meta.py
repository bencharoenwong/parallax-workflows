"""Shape rules for deciding whether a Parallax MCP response carries data.

``stress.classify_mcp_meta_state`` owns the full meta-state vocabulary
(UNCOVERED / UNREACHABLE / PARALLAX_SILENT / ok). Only one piece of it is
needed by more than one caller: the fail-closed judgement about whether a
response is structurally unusable, as opposed to a well-formed response that
merely reports no data.

That distinction is load-bearing and easy to get wrong in the obvious way. A
``{"success": false, "error": ...}`` response is **not** unreachable — the
server answered, it just has nothing for that component, which the house-view
skills treat as silent-for-that-component rather than a dead market. What *is*
unreachable is a response whose shape we cannot interpret at all: absent, not a
mapping, or carrying neither a ``success`` nor an ``error`` key. Those fail
closed, because a response we cannot classify must never be counted as
successfully fetched data.

Lives here rather than in either skill so the maker's reachability test and the
stress classifier cannot drift apart — they previously disagreed, with
``maker`` counting any non-``None`` object as reachable.
"""
from __future__ import annotations

from typing import Any


def shape_unreachable_reason(response: Any) -> str | None:
    """Why ``response`` is structurally unusable, or ``None`` if it is usable.

    "Usable" means only that the shape can be interpreted — a healthy response
    and an explicit ``success: false`` both return ``None`` here, and the
    caller decides what the difference means for its own vocabulary.
    """
    if response is None:
        return "no response from MCP"
    if not isinstance(response, dict):
        return f"unexpected response type: {type(response).__name__}"
    if "success" not in response and "error" not in response:
        # Neither healthy nor error-flagged: we cannot tell what this is.
        return "malformed response shape (no `success`/`error`)"
    if response.get("success") is False:
        return None  # answered, reporting failure -- silent, not unreachable
    if response.get("error") is not None:
        return None  # answered, flagging an error -- silent, not unreachable
    if response.get("success") is True:
        return None  # healthy
    # Has a success/error key but neither a usable boolean nor an error value.
    return "unrecognized response shape"


def carries_data(response: Any) -> bool:
    """True when the response is structurally interpretable. Fails closed."""
    return shape_unreachable_reason(response) is None
