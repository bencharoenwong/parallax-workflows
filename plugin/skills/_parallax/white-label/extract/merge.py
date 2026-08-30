"""Cross-source validation and draft merging.

Used when multiple sources are supplied (URL + folder, two PPTX files, etc.).
Mismatches are flagged but never auto-resolved — operator decides at the
confirmation gate. Voice corpora are concatenated across sources with
per-source attribution.
"""

from datetime import datetime, timezone
from copy import deepcopy
from typing import Any, Dict, List, Mapping


VOICE_WORD_LIMIT = 3000


class UnresolvedMismatchError(ValueError):
    """A visual mismatch lacks an operator-selected source."""


def _sorted_drafts(drafts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        drafts,
        key=lambda draft: str(draft.get("source", {}).get("reference", "?")),
    )


def cross_validate_visual(drafts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Compare visual fields across multiple source drafts; flag mismatches.

    Returns 'mismatches' (fields that disagree across sources) and
    'agreements' (fields all sources agree on). Mismatches are NOT
    auto-resolved — surfaced at the confirmation gate for human decision.

    Color comparison is exact-hex; font comparison is exact-name (case-insensitive).
    """
    mismatches: List[Dict[str, Any]] = []
    agreements: List[Dict[str, Any]] = []

    if len(drafts) < 2:
        return {"mismatches": [], "agreements": []}
    drafts = _sorted_drafts(drafts)

    for role in ["primary", "secondary", "accent", "background", "text"]:
        values: List[Dict[str, Any]] = []
        for d in drafts:
            entry = d.get("colors", {}).get(role)
            if entry and entry.get("hex"):
                values.append({
                    "source": d.get("source", {}).get("reference", "?"),
                    "value": entry["hex"].upper(),
                })
        unique = {v["value"] for v in values}
        if len(unique) > 1:
            mismatches.append({"field": f"colors.{role}", "values": values})
        elif len(unique) == 1 and len(values) >= 2:
            agreements.append({"field": f"colors.{role}", "value": values[0]["value"]})

    for role in ["header", "body", "monospace"]:
        values = []
        for d in drafts:
            entry = d.get("fonts", {}).get(role)
            if entry and entry.get("name"):
                values.append({
                    "source": d.get("source", {}).get("reference", "?"),
                    "value": entry["name"].strip().lower(),
                })
        unique = {v["value"] for v in values}
        if len(unique) > 1:
            mismatches.append({"field": f"fonts.{role}", "values": values})
        elif len(unique) == 1 and len(values) >= 2:
            agreements.append({"field": f"fonts.{role}", "value": values[0]["value"]})

    # Typography
    for level in ["h1", "h2", "h3", "h4", "h5", "body-md", "body-sm", "code"]:
        values = []
        for d in drafts:
            entry = d.get("typography", {}).get(level)
            if entry and entry.get("fontFamily"):
                values.append({
                    "source": d.get("source", {}).get("reference", "?"),
                    "value": entry["fontFamily"].strip().lower(),
                })
        unique = {v["value"] for v in values}
        if len(unique) > 1:
            mismatches.append({"field": f"typography.{level}.fontFamily", "values": values})
        elif len(unique) == 1 and len(values) >= 2:
            agreements.append(
                {
                    "field": f"typography.{level}.fontFamily",
                    "value": values[0]["value"],
                }
            )
            
    # Rounded
    for slot in ["sm", "md", "lg", "full"]:
        values = []
        for d in drafts:
            val = d.get("rounded", {}).get(slot)
            if val:
                values.append({
                    "source": d.get("source", {}).get("reference", "?"),
                    "value": val,
                })
        unique = {v["value"] for v in values}
        if len(unique) > 1:
            mismatches.append({"field": f"rounded.{slot}", "values": values})
        elif len(unique) == 1 and len(values) >= 2:
            agreements.append({"field": f"rounded.{slot}", "value": values[0]["value"]})

    # Spacing
    for slot in ["xs", "sm", "md", "lg", "xl"]:
        values = []
        for d in drafts:
            val = d.get("spacing", {}).get(slot)
            if val:
                values.append({
                    "source": d.get("source", {}).get("reference", "?"),
                    "value": val,
                })
        unique = {v["value"] for v in values}
        if len(unique) > 1:
            mismatches.append({"field": f"spacing.{slot}", "values": values})
        elif len(unique) == 1 and len(values) >= 2:
            agreements.append({"field": f"spacing.{slot}", "value": values[0]["value"]})

    return {"mismatches": mismatches, "agreements": agreements}


def merge_drafts(drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge multiple source drafts, preferring higher-confidence values per field.

    Voice corpus is concatenated under one exact word limit. ``by_source`` keeps
    attribution without adding source labels to the bounded corpus text.
    The returned draft's source.type is 'multi' with reference listing all sources.
    """
    if not drafts:
        return {}
    if len(drafts) == 1:
        return drafts[0]

    drafts = _sorted_drafts(drafts)
    extracted_values = [d.get("extracted_at") for d in drafts if d.get("extracted_at")]

    merged: Dict[str, Any] = {
        "colors": {},
        "logos": {},
        "fonts": {},
        "source": {
            "type": "multi",
            "reference": "; ".join(d.get("source", {}).get("reference", "?") for d in drafts),
            "components": [d.get("source", {}) for d in drafts],
        },
        "extracted_at": (
            max(extracted_values)
            if extracted_values
            else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "confidence_scores": {},
        "voice_corpus": {"text": "", "word_count": 0, "truncated": False, "by_source": []},
    }

    for d in drafts:
        for role, data in d.get("colors", {}).items():
            existing = merged["colors"].get(role)
            if not existing or data.get("confidence", 0) > existing.get("confidence", 0):
                merged["colors"][role] = data
        for role, data in d.get("logos", {}).items():
            existing = merged["logos"].get(role)
            if not existing or data.get("confidence", 0) > existing.get("confidence", 0):
                merged["logos"][role] = data
        for role, data in d.get("fonts", {}).items():
            existing = merged["fonts"].get(role)
            if not existing or data.get("confidence", 0) > existing.get("confidence", 0):
                merged["fonts"][role] = data

    merged["typography"] = {}
    merged["rounded"] = {}
    merged["spacing"] = {}
    
    # Typography: atomic object replacement
    for level in ["h1", "h2", "h3", "h4", "h5", "body-md", "body-sm", "code"]:
        best_conf = -1.0
        best_data = None
        for d in drafts:
            data = d.get("typography", {}).get(level)
            if data:
                conf = d.get("confidence_scores", {}).get(f"typography.{level}", 0)
                if conf > best_conf:
                    best_conf = conf
                    best_data = data
        if best_data:
            merged["typography"][level] = best_data

    # Rounded: atomic object replacement
    best_conf = -1.0
    best_data = None
    for d in drafts:
        data = d.get("rounded", {})
        if data:
            conf = d.get("confidence_scores", {}).get("rounded", 0)
            if conf > best_conf:
                best_conf = conf
                best_data = data
    if best_data:
        merged["rounded"] = best_data

    # Spacing: atomic object replacement
    best_conf = -1.0
    best_data = None
    for d in drafts:
        data = d.get("spacing", {})
        if data:
            conf = d.get("confidence_scores", {}).get("spacing", 0)
            if conf > best_conf:
                best_conf = conf
                best_data = data
    if best_data:
        merged["spacing"] = best_data

    # Clean up empty dicts
    if not merged["typography"]: del merged["typography"]
    if not merged["rounded"]: del merged["rounded"]
    if not merged["spacing"]: del merged["spacing"]

    combined_text_parts: List[str] = []
    available_word_count = sum(
        len((d.get("voice_corpus") or {}).get("text", "").split()) for d in drafts
    )
    remaining_words = VOICE_WORD_LIMIT
    any_truncated = any(
        bool((d.get("voice_corpus") or {}).get("truncated")) for d in drafts
    )
    for d in drafts:
        vc = d.get("voice_corpus") or {}
        if vc.get("text"):
            ref = d.get("source", {}).get("reference", "?")
            source_words = vc["text"].split()
            retained = source_words[:remaining_words]
            if retained:
                combined_text_parts.append(" ".join(retained))
                merged["voice_corpus"]["by_source"].append({
                    "reference": ref,
                    "word_count": len(retained),
                })
            remaining_words -= len(retained)
            if remaining_words == 0:
                break
    merged["voice_corpus"]["text"] = "\n\n".join(combined_text_parts)
    merged["voice_corpus"]["word_count"] = len(merged["voice_corpus"]["text"].split())
    merged["voice_corpus"]["truncated"] = (
        any_truncated or available_word_count > VOICE_WORD_LIMIT
    )

    for d in drafts:
        for k, v in d.get("confidence_scores", {}).items():
            existing = merged["confidence_scores"].get(k, 0)
            if v > existing:
                merged["confidence_scores"][k] = v

    return merged


def _value_from_source(
    drafts: List[Dict[str, Any]], field: str, reference: str
) -> Any:
    matches = [
        draft
        for draft in drafts
        if draft.get("source", {}).get("reference") == reference
    ]
    if not matches:
        raise ValueError(f"Resolution for {field} names unknown source: {reference}")
    if len(matches) > 1:
        raise ValueError(f"Resolution for {field} names duplicate source: {reference}")
    value: Any = matches[0]
    for component in field.split("."):
        if not isinstance(value, dict) or component not in value:
            raise ValueError(f"Resolution source {reference} has no value for {field}")
        value = value[component]
    return deepcopy(value)


def merge_resolved_drafts(
    drafts: List[Dict[str, Any]], resolutions: Mapping[str, str]
) -> Dict[str, Any]:
    """Merge drafts after each visual mismatch has a source-attributed choice."""
    validation = cross_validate_visual(drafts)
    mismatch_fields = {mismatch["field"] for mismatch in validation["mismatches"]}
    unexpected = sorted(set(resolutions) - mismatch_fields)
    if unexpected:
        raise ValueError(
            "Resolution supplied for non-mismatch field: " + ", ".join(unexpected)
        )
    unresolved = [
        mismatch["field"]
        for mismatch in validation["mismatches"]
        if mismatch["field"] not in resolutions
    ]
    if unresolved:
        raise UnresolvedMismatchError(
            "Operator resolution required for: " + ", ".join(unresolved)
        )
    canonical_drafts = _sorted_drafts(drafts)
    # merge_drafts hands back the winning draft's own typography, rounded and
    # spacing dicts by reference, so writing a resolution through them edited
    # the caller's input. The per-source candidates the confirmation gate
    # displays were overwritten with the operator's pick, and re-validating the
    # same drafts then reported consensus where a mismatch had been.
    merged = deepcopy(merge_drafts(canonical_drafts))
    for field in sorted(resolutions):
        value = _value_from_source(canonical_drafts, field, resolutions[field])
        target = merged
        components = field.split(".")
        for component in components[:-1]:
            target = target.setdefault(component, {})
        target[components[-1]] = value
    canonical_resolutions = {
        field: resolutions[field] for field in sorted(resolutions)
    }
    merged["multi_source"] = {
        "sources": [deepcopy(draft.get("source", {})) for draft in canonical_drafts],
        "mismatches": validation["mismatches"],
        "agreements": validation["agreements"],
        "resolutions": canonical_resolutions,
    }
    return merged
