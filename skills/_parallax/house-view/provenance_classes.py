"""Provenance class field specs.

Read by load-house-view --why and audit_export.create_bundle.
Single source of truth for which fields each provenance class carries.
"""

GENERATOR_SYNTHESIS_FIELDS = {
    "required": [
        "confidence", "rationale", "source_tools",
        "composition_formula", "aggregator_weights_ref",
        "data_as_of",
    ],
    "optional": [
        "source_call_args", "source_snippets",
        "missing_inputs", "fan_out_summary",
    ],
}

JUDGE_RECOMMENDATION_FIELDS = {
    "required": [
        "confidence", "rationale", "judge_run_id",
        "drift_severity", "stress_state",
        "parallax_signal", "age_delta_days",
    ],
    "optional": ["notes"],
}

# Existing classes kept here for completeness (read-only consumers
# already know them; this is the authoritative spec).
PROSE_EXTRACTION_FIELDS = {
    "required": ["confidence", "rationale", "source_span"],
    "optional": [],
}

MACRO_REGIME_RULE_FIELDS = {
    "required": ["confidence", "rationale", "rule_ref", "trigger"],
    "optional": [],
}

MANUAL_EDIT_FIELDS = {
    "required": ["confidence", "rationale", "prior_value", "edit_notes"],
    "optional": [],
}

# Legacy — back-compat read only; never produced at new save time.
PARALLAX_DATA_FILL_FIELDS = {
    "required": ["confidence", "rationale", "source_tools"],
    "optional": ["data_as_of"],
}

CLASS_REGISTRY = {
    "generator_synthesis":  GENERATOR_SYNTHESIS_FIELDS,
    "judge_recommendation": JUDGE_RECOMMENDATION_FIELDS,
    "prose_extraction":     PROSE_EXTRACTION_FIELDS,
    "macro_regime_rule":    MACRO_REGIME_RULE_FIELDS,
    "manual_edit":          MANUAL_EDIT_FIELDS,
    "parallax_data_fill":   PARALLAX_DATA_FILL_FIELDS,
}

# Classes that are valid for READING (back-compat) but should NOT be
# produced by new code at save time. Writers calling validate_provenance_entry
# with mode="write" get an error for deprecated classes; readers (default)
# get a warning printed to stderr but the entry still validates.
DEPRECATED_CLASSES = frozenset({"parallax_data_fill"})


def validate_provenance_entry(entry: dict, mode: str = "read") -> list[str]:
    """Returns list of validation errors; empty if valid.

    Args:
        entry: provenance entry dict with a 'class' key.
        mode: 'read' (default) accepts deprecated classes with a stderr
              warning. 'write' rejects deprecated classes as errors.
    """
    errors = []
    cls = entry.get("class")
    if cls not in CLASS_REGISTRY:
        errors.append(f"unknown provenance class: {cls!r}")
        return errors
    if cls in DEPRECATED_CLASSES:
        if mode == "write":
            errors.append(
                f"deprecated provenance class {cls!r} is read-only; "
                f"new entries must use a current class "
                f"(see schema.yaml § classification_taxonomy)"
            )
            return errors
        # mode == "read": surface a warning but continue validation.
        import sys as _sys
        print(
            f"WARN: provenance class {cls!r} is deprecated and read-only; "
            f"this entry should be migrated.",
            file=_sys.stderr,
        )
    spec = CLASS_REGISTRY[cls]
    for field in spec["required"]:
        if field not in entry:
            errors.append(f"{cls}: missing required field {field!r}")
    return errors
