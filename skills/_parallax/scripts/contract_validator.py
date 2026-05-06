"""
Shared MCP contract-test validator for parallax-* skills.

The Parallax MCP family is consumed by multiple skills (cio-letter-prep,
morning-brief, client-review, rebalance, explain-portfolio, ...). Each skill
reads a specific subset of fields from each endpoint's response. If an upstream
endpoint changes its response shape (drops a field, renames, changes type),
every consuming skill silently degrades until a customer hits it.

This module provides the shared validator + helpers that per-skill contract
tests use to assert "the mock JSON conforms to the schema we documented."
Schemas (the canonical contract per endpoint) live in ``contract_schemas.py``.
Mock fixtures live in ``mcp_mocks/*.json``.

Per-skill usage
---------------

A consuming skill creates ``skills/<skill>/scripts/test_mcp_contracts.py``::

    from __future__ import annotations
    import pathlib, sys

    # Add the shared `_parallax/scripts/` to sys.path
    _HERE = pathlib.Path(__file__).resolve().parent
    _PARALLAX = _HERE.parent.parent / "_parallax" / "scripts"
    sys.path.insert(0, str(_PARALLAX))

    from contract_validator import (
        load_mock, validate, OPTIONAL, NUM, is_iso_date, is_iso_datetime,
    )
    from contract_schemas import (
        GET_TELEMETRY_SCHEMA, ANALYZE_PORTFOLIO_SCHEMA,  # ...
    )

    def test_get_telemetry_mock_conforms_to_schema():
        validate(load_mock("get_telemetry"), GET_TELEMETRY_SCHEMA, "get_telemetry")

    def test_get_telemetry_mock_has_realistic_values():
        data = load_mock("get_telemetry")
        assert data["regime_tag"] in {"risk-on", "risk-off", "neutral", "mixed", "selective rotation"}
        # ...

The skill MAY also add its own per-skill mocks if it consumes endpoint shapes
not covered by the shared mocks (see ``mcp_mocks/README.md``).

Schema DSL (Python-dict)
------------------------

::

    SCHEMA = {
        "field_name": <type spec>,
        ...
    }

    <type spec> ::= type                       # required, single type
                  | (type, ...)                # required, any of these types
                  | (type, "optional")         # optional, single type
                  | dict (nested schema)       # required nested object
                  | (dict, "optional")         # optional nested object
                  | [<type spec>]              # required list; element schema
                  | ([<type spec>], "optional") # optional list

For list elements that are dicts, use ``[nested_schema]`` (a one-element list
whose only element is a dict).

Validator limitation — empty lists
----------------------------------

When a schema specifies a list with element-shape ``[elt_schema]``, an empty
list passes the validator unconditionally — element-shape validation only
fires per-element. If empty lists are not legitimate output for an endpoint,
add a ``len(data[field]) > 0`` guard in that endpoint's realistic-values test.

OPTIONAL semantics — absent vs null
-----------------------------------

``OPTIONAL`` means **the field may be absent** from the response dict. It does
NOT cover JSON null: if an endpoint returns ``{"currency": null}`` (field
present but null), the validator will reject because ``None`` does not match
the inner type spec (e.g., ``str``). This is a deliberate semantic — null and
absent are distinct in JSON, and silently accepting both would mask real
contract drift.

If a future endpoint legitimately uses null for a field, introduce a
``NULLABLE`` sentinel (alongside ``OPTIONAL``) rather than loosening
``OPTIONAL`` itself. Don't add this until a real schema needs it.

Coupling with skill SKILL.md files
----------------------------------

When a skill begins reading a new field from any endpoint, the corresponding
schema in ``contract_schemas.py`` MUST be updated in the same PR. The README
in ``mcp_mocks/`` describes the refresh workflow; the coupling is flagged here
because a SKILL.md author updating field reads is unlikely to check the
README first.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Any


# Number is "int or float"; Parallax may return either depending on the value.
NUM = (int, float)


OPTIONAL = "optional"


# --------------------------------------------------------------------------
# Mock loading
# --------------------------------------------------------------------------

# Shared mocks live next to this validator module.
MOCKS_DIR = pathlib.Path(__file__).parent / "mcp_mocks"


def load_mock(name: str, mocks_dir: pathlib.Path | None = None) -> Any:
    """Load mock JSON file ``mcp_mocks/<name>.json`` and return parsed value.

    Args:
        name: mock file basename without extension.
        mocks_dir: optional override for skill-specific mock fixtures. Defaults
            to the shared ``_parallax/scripts/mcp_mocks/`` directory.
    """
    base = mocks_dir if mocks_dir is not None else MOCKS_DIR
    path = base / f"{name}.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Hand-rolled schema validator
# --------------------------------------------------------------------------


def _is_optional_spec(spec: Any) -> bool:
    """True iff ``spec`` is a ``(inner, "optional")`` tuple marker."""
    return (
        isinstance(spec, tuple)
        and len(spec) == 2
        and spec[1] == OPTIONAL
    )


def validate(value: Any, spec: Any, path: str) -> None:
    """Validate ``value`` against ``spec``. Raise AssertionError on mismatch.

    See module docstring for the spec DSL. ``path`` is a dotted JSON path
    used in error messages.
    """
    # Optional wrapper: unwrap and validate inner
    if _is_optional_spec(spec):
        validate(value, spec[0], path)
        return

    # Nested dict schema
    if isinstance(spec, dict):
        assert isinstance(value, dict), (
            f"{path}: expected dict, got {type(value).__name__}"
        )
        for field, field_spec in spec.items():
            child_path = f"{path}.{field}" if path else field
            optional = _is_optional_spec(field_spec)
            if field not in value:
                assert optional, f"{child_path}: missing required field"
                continue
            validate(value[field], field_spec, child_path)
        return

    # List schema: spec is a one-element list whose element is the elt spec
    if isinstance(spec, list):
        assert isinstance(value, list), (
            f"{path}: expected list, got {type(value).__name__}"
        )
        assert len(spec) == 1, (
            f"{path}: list spec must have exactly one element schema"
        )
        elt_spec = spec[0]
        for i, item in enumerate(value):
            validate(item, elt_spec, f"{path}[{i}]")
        return

    # Tuple-of-types: any of these types
    if isinstance(spec, tuple):
        assert all(isinstance(t, type) for t in spec), (
            f"{path}: malformed tuple spec {spec!r}"
        )
        assert isinstance(value, spec), (
            f"{path}: expected one of {[t.__name__ for t in spec]}, "
            f"got {type(value).__name__}"
        )
        return

    # Single type
    if isinstance(spec, type):
        # bool is subclass of int in Python — disallow accidental bool-for-int
        if spec is int and isinstance(value, bool):
            raise AssertionError(f"{path}: expected int, got bool")
        assert isinstance(value, spec), (
            f"{path}: expected {spec.__name__}, got {type(value).__name__}"
        )
        return

    raise AssertionError(f"{path}: malformed schema spec {spec!r}")


# --------------------------------------------------------------------------
# Realistic-values helpers (used by per-skill realistic-values tests)
# --------------------------------------------------------------------------


def is_iso_date(s: str) -> bool:
    """True iff ``s`` parses as an ISO 'YYYY-MM-DD' date."""
    try:
        _dt.date.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


def is_iso_datetime(s: str) -> bool:
    """True iff ``s`` parses as an ISO datetime, with or without trailing Z."""
    try:
        normalised = s.replace("Z", "+00:00") if s.endswith("Z") else s
        _dt.datetime.fromisoformat(normalised)
        return True
    except (ValueError, TypeError):
        return False
