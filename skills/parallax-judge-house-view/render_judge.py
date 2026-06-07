"""Markdown + JSON renderers for /parallax-judge-house-view reports.

The judge skill writes a bundle to
``~/.parallax/judge-reports/<judged_view_version_id>-<judged_at>/`` per
v2 plan §3.1 Phase 6:

    report.md          (client-facing markdown)
    report.json        (structured form for cron / automation consumption)
    mcp_responses.jsonl  (one line per MCP call: tool, args, response,
                          latency_ms — written by the orchestrator)
    reasoning_chain.yaml (written by chain_emit, not this module)
    audit_entry.json   (the row appended to audit.jsonl, written by the
                        orchestrator after audit_chain.append_entry)

This module owns ``report.md`` and ``report.json``. The other artifacts
are written by the orchestrator directly to avoid double-formatting.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

# Header banner is intentionally a constant — renderers in other skills
# (house-view-diff, stress) reuse the same visual structure and the
# Phase F consumer integrations match against this prefix when deciding
# whether to suppress duplicate banners.
_REPORT_HEADER = "# House View Judge Report"

# Severity → emoji + label. Surface-visible severity is the orchestrator's
# call (drift_classify.classify_severity); the renderer only maps the
# label to its banner glyph.
_SEVERITY_BANNERS = {
    "drift_minor": ("OK", "Minor drift detected"),
    "drift_moderate": ("WARN", "Moderate drift detected"),
    "drift_material": ("ALERT", "Material drift detected"),
    "drift_breaking": ("CRITICAL", "Breaking drift detected"),
}


def _isoformat(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _format_recommendation_row(rec: dict[str, Any]) -> str:
    """Render one Recommendations table row.

    Honest declines (citation_check failed) render with the decline
    marker visible so the CIO can see the system caught a hallucination
    rather than silently dropping it.
    """
    path = rec.get("path", "")
    declined = rec.get("declined", False)
    if declined:
        return (
            f"| `{path}` | (declined) | n/a | "
            f"{rec.get('rationale', '')} |"
        )
    rec_value = rec.get("recommended_value")
    rec_str = "null" if rec_value is None else f"{rec_value:+d}" if isinstance(rec_value, int) else str(rec_value)
    conf = rec.get("confidence", 0.0)
    rationale = (rec.get("rationale") or "").replace("|", "\\|")[:200]
    return f"| `{path}` | {rec_str} | {conf:.2f} | {rationale} |"


def render_markdown_report(
    *,
    view_meta: dict[str, Any],
    judged_view_id: str,
    judged_version_id: str,
    view_age_days: int,
    parallax_age_days: int,
    severity: str,
    severity_details: dict[str, Any],
    drift_summary: dict[str, int],
    resolutions: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    pillars_only: bool = False,
    trigger: str = "on_demand",
    judged_at: datetime.datetime | None = None,
) -> str:
    """Render the human-readable judge report.

    Args mirror the orchestrator's per-phase outputs. ``pillars_only=True``
    suppresses the per-cell table (used by the ``--pillars-only`` CLI flag).
    """
    judged_at = judged_at or datetime.datetime.now(datetime.timezone.utc)
    glyph, label = _SEVERITY_BANNERS.get(severity, ("?", severity))

    lines: list[str] = [
        _REPORT_HEADER,
        "",
        f"**View ID:** `{judged_view_id}`  ",
        f"**Version ID:** `{judged_version_id}`  ",
        f"**View Name:** {view_meta.get('view_name', '<unset>')}  ",
        f"**Judged At:** {_isoformat(judged_at)}  ",
        f"**Trigger:** `{trigger}`  ",
        f"**View Age:** {view_age_days} day(s)  ",
        f"**Parallax Age:** {parallax_age_days} day(s)  ",
        "",
        "---",
        "",
        f"## Verdict: {glyph} — {label} (`{severity}`)",
        "",
    ]

    # Severity explanation block.
    lines.append(
        f"- Divergent cells: **{severity_details.get('divergent_count', 0)}** "
        f"of **{severity_details.get('denominator', 0)}** non-zero tilts "
        f"({severity_details.get('divergent_pct', 0):.1%})"
    )
    if severity_details.get("pillar_divergence"):
        cells = severity_details.get("pillar_cells", [])
        lines.append(
            f"- Pillar divergence on: {', '.join(f'`{c}`' for c in cells)} "
            "(any pillar divergence forces `drift_material`)"
        )
    if severity_details.get("macro_sign_flip"):
        cells = severity_details.get("macro_sign_flip_cells", [])
        lines.append(
            f"- Macro-regime sign-flip on: {', '.join(f'`{c}`' for c in cells)}"
        )
    if severity_details.get("magnitude_escalated"):
        lines.append(
            f"- Magnitude escalation: max delta "
            f"`{severity_details.get('max_magnitude')}` >= 3 → tier bumped"
        )

    lines.extend(["", "## Drift summary", ""])
    lines.append("| State | Count |")
    lines.append("|---|---|")
    for key in (
        "aligned_count",
        "drift_minor_count",
        "drift_material_count",
        "drift_breaking_count",
        "parallax_silent_count",
        "uncovered_count",
        "cio_silent_count",
    ):
        if key in drift_summary:
            lines.append(f"| `{key}` | {drift_summary[key]} |")

    # Per-cell table (skipped under --pillars-only).
    if not pillars_only and resolutions:
        lines.extend(["", "## Per-cell resolution", ""])
        lines.append("| Path | Market | State | CIO | Parallax |")
        lines.append("|---|---|---|---|---|")
        for r in resolutions:
            mkt = r.get("market") or "(global)"
            cio = r.get("cio_tilt")
            plx = r.get("parallax_view")
            lines.append(
                f"| `{r.get('dim', '')}` | {mkt} | {r.get('state', '?')} | "
                f"{cio!r} | {plx!r} |"
            )

    # Recommendations.
    lines.extend(["", "## Recommendations", ""])
    if not recommendations:
        lines.append(
            "_No per-cell recommendations were emitted. View is materially "
            "aligned with current Parallax signals, or severity tier is "
            "below the recommendation threshold._"
        )
    else:
        kept = sum(1 for r in recommendations if not r.get("declined"))
        declined = sum(1 for r in recommendations if r.get("declined"))
        lines.append(f"_{kept} recommendation(s); {declined} declined for citation failure._")
        lines.append("")
        lines.append("| Path | Recommended | Confidence | Rationale |")
        lines.append("|---|---|---|---|")
        for rec in recommendations:
            lines.append(_format_recommendation_row(rec))

    lines.extend([
        "",
        "---",
        "",
        "## Operational notes",
        "",
        "- This report is **read-only**. The judge never modifies the active view.",
        "- To accept any recommendation: `/parallax-load-house-view --edit`, then "
        "cite this run in the `basis_statement` (`judge:<audit_hash_short>`).",
        "- A future `/parallax-load-house-view --apply-judge <audit-hash>` will "
        "pre-populate the draft from the audit row's `recommendations` field.",
        "",
        "*Calibration: `heuristic_phase0` — intended for directional research only; "
        "see loader.md §5.1a.*",
    ])

    return "\n".join(lines) + "\n"


def render_json_sidecar(
    *,
    view_meta: dict[str, Any],
    judged_view_id: str,
    judged_version_id: str,
    view_age_days: int,
    parallax_age_days: int,
    severity: str,
    severity_details: dict[str, Any],
    drift_summary: dict[str, int],
    resolutions: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    trigger: str = "on_demand",
    judged_at: datetime.datetime | None = None,
) -> str:
    """Render the structured JSON sidecar (for cron / automation).

    Schema is stable: any addition is additive only. The
    ``--json`` CLI mode prints this verbatim to stdout in addition to
    writing it to the report bundle.
    """
    judged_at = judged_at or datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "report_version": 1,
        "view_id": judged_view_id,
        "version_id": judged_version_id,
        "view_name": view_meta.get("view_name"),
        "judged_at": _isoformat(judged_at),
        "trigger": trigger,
        "view_age_days": view_age_days,
        "parallax_age_days": parallax_age_days,
        "severity": severity,
        "severity_details": severity_details,
        "drift_summary": drift_summary,
        "resolutions": resolutions,
        "recommendations": recommendations,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def write_report_bundle(
    *,
    output_dir: Path,
    markdown: str,
    json_sidecar: str,
) -> dict[str, Path]:
    """Write report.md + report.json into ``output_dir``.

    The orchestrator owns mcp_responses.jsonl, reasoning_chain.yaml, and
    audit_entry.json — this function only handles the two renderable
    artifacts. Directory creation mirrors stress/render_helpers (0700).
    """
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    report_md = output_dir / "report.md"
    report_json = output_dir / "report.json"
    report_md.write_text(markdown, encoding="utf-8")
    report_json.write_text(json_sidecar, encoding="utf-8")
    report_md.chmod(0o600)
    report_json.chmod(0o600)
    return {"report.md": report_md, "report.json": report_json}
