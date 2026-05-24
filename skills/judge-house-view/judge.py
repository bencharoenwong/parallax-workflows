"""Orchestrator for /parallax-judge-house-view.

Implements Phases 0-8 from notes/2026-05-24-house-view-v2-plan.md §3.1.
The skill is read-only against the active house view: it appends a
single ``action="judge"`` row to ``audit.jsonl`` (always
``applied=false``) and writes a self-contained report bundle to
``~/.parallax/judge-reports/<judged_version_id>-<judged_at>/``. The
active ``view.yaml`` and ``provenance.yaml`` are never touched.

Server-side ``house_view_judge`` MCP tool: DEFERRED (v2 plan §3.2 /
BUG-007). The skill-only path here is the canonical surface until the
Supabase managed backend ships.

External-dependency policy
--------------------------

The judge re-uses the maker's shared modules (``cross_country``,
``pillar_compose``, ``pillar_formulas``) to compute "what would the
maker say today" — the imputed view we diff against the saved view.
Those modules live in the Phase B1 maker skill. We import them
lazily so the judge can:

- run against ``--dry`` fixtures without B1 installed (tests pass)
- fall back to a clear "imputed view unavailable" diagnostic when
  the maker hasn't shipped yet (live deploys, until B1 lands).

If B1 chooses a different module path (``_parallax/house-view/`` vs
``make-house-view/``), the import probe walks both candidates.
"""
from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Local module path setup — same pattern as stress.py.
_THIS_DIR = Path(__file__).resolve().parent
_HOUSE_VIEW_DIR = _THIS_DIR.parent / "_parallax" / "house-view"
_STRESS_DIR = _THIS_DIR.parent / "stress-house-view"
for _p in (_THIS_DIR, _HOUSE_VIEW_DIR, _STRESS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import rfc8785  # noqa: E402
import yaml  # noqa: E402

import audit_chain  # noqa: E402  (from _parallax/house-view/)
import chain_emit  # noqa: E402
import stress  # noqa: E402  (from stress-house-view/)

import cadence  # noqa: E402  (local)
import drift_classify  # noqa: E402  (local)
import recommendation as rec_mod  # noqa: E402  (local)
import render_judge  # noqa: E402  (local)

logger = logging.getLogger(__name__)

SKILL_NAME = "parallax-judge-house-view"
SKILL_VERSION = "parallax-judge-house-view@1.0.0"

# Where the judge writes its report bundles. The user-facing default
# mirrors ~/.parallax/stress-tests/ + ~/.parallax/reasoning-chains/.
DEFAULT_REPORT_DIR = Path(
    os.environ.get("PARALLAX_JUDGE_REPORTS_DIR")
    or os.path.expanduser("~/.parallax/judge-reports")
)


# ---------------------------------------------------------------------------
# Shared-module probe (cross_country / pillar_compose / pillar_formulas)
# ---------------------------------------------------------------------------

# Maker modules live in skills/make-house-view/ (hyphenated, not a Python
# package). Follow the same sys.path injection pattern stress.py uses to
# import shared infra (see stress.py: _HOUSE_VIEW_DIR + sys.path.insert).
_MAKER_DIR = Path(__file__).resolve().parent.parent / "make-house-view"


@dataclass
class MakerModules:
    """Bundle of maker modules used during the imputed-view computation.

    Populated by ``probe_maker_modules``; carries the actual module
    references when the maker is available, or ``None`` slots + the
    diagnostic string when it isn't.
    """

    available: bool
    diagnostic: str
    cross_country: Any = None
    pillar_compose: Any = None
    pillar_formulas: Any = None


def probe_maker_modules() -> MakerModules:
    """Load the maker's shared modules via sys.path injection.

    The maker lives at ``skills/make-house-view/`` (hyphenated, not a Python
    package). Same pattern stress.py uses for shared infra: inject the
    directory into sys.path and bare-import the modules.

    Returns a populated ``MakerModules`` on success, or one with
    ``available=False`` and a human-readable diagnostic when the maker
    is not installed at the expected path.
    """
    if not _MAKER_DIR.is_dir():
        return MakerModules(
            available=False,
            diagnostic=(
                f"maker modules unavailable — directory not found: {_MAKER_DIR}. "
                "Imputed view will be NULL; cell resolutions still computed "
                "from raw MCP responses where possible."
            ),
        )
    if str(_MAKER_DIR) not in sys.path:
        sys.path.insert(0, str(_MAKER_DIR))
    try:
        import cross_country as cc  # noqa: E402
        import pillar_compose as pc  # noqa: E402
        import pillar_formulas as pf  # noqa: E402
    except ImportError as exc:
        return MakerModules(
            available=False,
            diagnostic=(
                f"maker modules unavailable — import failed: {exc}. "
                f"Searched: {_MAKER_DIR}. "
                "Imputed view will be NULL; cell resolutions still computed "
                "from raw MCP responses where possible."
            ),
        )
    return MakerModules(
        available=True,
        diagnostic=f"maker modules resolved from {_MAKER_DIR}",
        cross_country=cc,
        pillar_compose=pc,
        pillar_formulas=pf,
    )


# ---------------------------------------------------------------------------
# JudgeConfig / JudgeResult
# ---------------------------------------------------------------------------


@dataclass
class JudgeConfig:
    """Knobs for one judge run.

    Attributes:
        pillars_only: --pillars-only CLI flag. Suppresses the per-cell
            table in the report; the orchestrator still computes
            resolutions for the drift_summary counts.
        json_output: --json CLI flag. Returns JSON to stdout in addition
            to writing the report bundle.
        dry: --dry CLI flag. Uses mocked MCP responses (caller supplies
            them via ``mock_mcp_responses``).
        explicit: Whether the caller invoked the CLI directly (used by
            ``cadence.resolve_trigger``).
        scheduled: Whether this is a cron-style scheduled run.
        report_dir: Override the default report bundle location.
        view_dir: Override the active-view location (mirrors
            ``stress.HOUSE_VIEW_DIR``).
        mock_mcp_responses: When ``dry=True``, the per-market MCP
            response dict the orchestrator uses in place of live calls.
    """

    pillars_only: bool = False
    json_output: bool = False
    dry: bool = False
    explicit: bool = True
    scheduled: bool = False
    report_dir: Path | None = None
    view_dir: Path | None = None
    mock_mcp_responses: dict[str, Any] | None = None


@dataclass
class JudgeResult:
    """Final outcome of one judge run. Returned by ``run_judge``."""

    severity: str
    severity_details: dict[str, Any]
    drift_summary: dict[str, int]
    resolutions: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    report_dir: Path | None = None
    audit_entry: dict[str, Any] | None = None
    chain_path: Path | None = None
    chain_emit_failed: bool = False
    """True iff phase_8_emit_chain raised. Surfaces programmatically what
    was previously only visible by parsing the diagnostics string. SKILL.md
    lists the reasoning chain as a required output, so callers (and tests)
    should treat True as a hard failure even when severity/recommendations
    look fine."""
    diagnostics: list[str] = field(default_factory=list)
    json_payload: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _isoformat(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _view_age_days(view_data: dict[str, Any], now: datetime.datetime) -> int:
    upload_iso = view_data.get("metadata", {}).get("upload_timestamp")
    if not upload_iso:
        return 0
    try:
        ts = datetime.datetime.fromisoformat(upload_iso.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    delta = now - ts
    return max(0, delta.days)


def _parallax_age_days(mcp_responses: dict[str, Any], now: datetime.datetime) -> int:
    """Max staleness across MCP responses. Mirrors stress's semantics.

    Each response may carry a ``report_date`` (YYYY-MM-DD) per the
    inventory; we compute (now.date() - report_date).days. Missing
    dates count as 0 (we cannot prove staleness if the response omits
    the field).
    """
    best = 0
    for _, resp in mcp_responses.items():
        if not isinstance(resp, dict):
            continue
        report_date = resp.get("report_date") or resp.get("data_as_of")
        if not report_date:
            continue
        try:
            d = datetime.date.fromisoformat(report_date[:10])
        except (TypeError, ValueError):
            continue
        age = (now.date() - d).days
        if age > best:
            best = age
    return best


def _response_hash(mcp_responses: dict[str, Any]) -> str:
    """sha256(JCS(sorted concat of all (tool, args, response) tuples)).

    Mirrors the v2 plan §6.4 spec for chain_emit's response_hash.
    """
    parts = []
    for key in sorted(mcp_responses.keys()):
        # The key is the canonical ``tool:args`` summary string; the
        # value is the response dict. We canonicalize each separately so
        # ordering inside the response doesn't change the hash.
        try:
            canonical = rfc8785.dumps({"t": key, "r": mcp_responses[key]})
        except (TypeError, ValueError):
            canonical = json.dumps(
                {"t": key, "r": mcp_responses[key]},
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        parts.append(canonical)
    return hashlib.sha256(b"\n".join(parts)).hexdigest()


# ---------------------------------------------------------------------------
# Phase 0: load active view
# ---------------------------------------------------------------------------


def phase_0_load_view(view_dir: Path | None) -> stress.View:
    """Load + verify the active view. Halt on missing / broken chain."""
    target = view_dir or stress.HOUSE_VIEW_DIR
    return stress.load_active_view(target)


# ---------------------------------------------------------------------------
# Phase 1: MCP fan-out
# ---------------------------------------------------------------------------


def phase_1_fan_out(
    config: JudgeConfig,
    mcp_call_fn: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    """Fan out MCP calls per the maker's recipe.

    In ``dry`` mode we use ``config.mock_mcp_responses`` verbatim. In
    live mode the caller supplies an ``mcp_call_fn`` that the
    orchestrator delegates to (tests inject a fake). Live MCP dispatch
    is the responsibility of the Claude skill runtime — this module
    only orchestrates the shape.

    Returns a dict keyed by ``tool:arg1:arg2:...`` summary strings.
    """
    if config.dry:
        if config.mock_mcp_responses is None:
            raise ValueError("dry=True requires mock_mcp_responses")
        return dict(config.mock_mcp_responses)
    if mcp_call_fn is None:
        # Live mode without an injected callable means the orchestrator
        # is being driven from a non-runtime test path. We return an
        # empty dict and surface the gap in diagnostics — better than
        # crashing the whole pipeline.
        return {}
    # The actual fan-out shape (14 markets × 5 components + telemetry)
    # is implemented by the maker's orchestrator. The judge reuses
    # cross_country.aggregate + pillar_compose.compute_pillars on the
    # same payload shape — so live wiring goes through mcp_call_fn
    # with the maker's call recipe. Until B1 lands, this code path
    # gracefully degrades to "no MCP responses" rather than guessing.
    return mcp_call_fn() or {}


# ---------------------------------------------------------------------------
# Phase 2: per-cell resolution
# ---------------------------------------------------------------------------


def _imputed_view_from_maker(
    maker: MakerModules,
    mcp_responses: dict[str, Any],
    weights: dict[str, Any] | None,
    inventory: dict[str, Any] | None,
) -> dict[str, Any]:
    """Run the maker's pure-compute path to derive 'what the maker would
    say today'. Returns a view-shaped dict (just the ``tilts`` subtree).
    """
    if not maker.available:
        return {}
    try:
        # cross_country.aggregate(per_market_responses, telemetry, weights)
        # returns top-level keys: regions, sectors, macro_regime, phi, xi,
        # psi_news_blobs, fan_out_summary, field_coverage. NOT wrapped in
        # a `tilts` subtree (verified in cross_country.py docstring).
        aggregated = maker.cross_country.aggregate(
            mcp_responses.get("per_market", mcp_responses),
            mcp_responses.get("telemetry", {}),
            weights,
        )
        pillars = maker.pillar_compose.compute_pillars(
            aggregated,
            mcp_responses.get("telemetry", {}),
            inventory or {},
        )
        # Lift aggregated top-level tilt categories into the view-shaped
        # tilts dict that phase_2_resolve_cells consumes.
        tilts: dict[str, Any] = {
            "regions": dict(aggregated.get("regions", {})) if isinstance(aggregated, dict) else {},
            "sectors": dict(aggregated.get("sectors", {})) if isinstance(aggregated, dict) else {},
            "macro_regime": dict(aggregated.get("macro_regime", {})) if isinstance(aggregated, dict) else {},
        }
        if pillars:
            # Prefer the maker's view-helper if exposed; else extract .value.
            if hasattr(maker.pillar_compose, "pillar_values_for_view"):
                tilts["pillars"] = maker.pillar_compose.pillar_values_for_view(pillars)
            else:
                tilts["pillars"] = {
                    name: getattr(pr, "value", pr) for name, pr in pillars.items()
                }
        return {"tilts": tilts}
    except Exception as exc:  # pragma: no cover  (maker may raise anything)
        logger.warning("imputed view computation failed: %s", exc)
        return {}


def phase_2_resolve_cells(
    view: stress.View,
    imputed_view: dict[str, Any],
    age_delta: str,
    covered_markets: set[str] | None,
) -> list[dict[str, Any]]:
    """Diff active vs imputed per-cell via stress.resolve_cell_state.

    Returns one resolution dict per non-zero cell in the active view
    (the denominator stress.enumerate_dimensions tracks). Resolutions
    not yet covered by the imputed view get state=PARALLAX_SILENT.
    """
    dims, market_info = stress.enumerate_dimensions(view)
    resolutions: list[dict[str, Any]] = []
    imputed_tilts = (imputed_view or {}).get("tilts", {}) or {}

    for path in dims:
        # path is "tilts.<category>.<dim>" or "tilts.<category>.<dim>.<sub>".
        segments = path.split(".")
        cio_tilt = stress._get_nested(view.data, path)
        parallax_view = stress._get_nested({"tilts": imputed_tilts}, path)
        # Region tilts pick up a market key; everything else is global.
        market = segments[2] if len(segments) >= 3 and segments[1] == "regions" else None
        state = stress.resolve_cell_state(
            cio_tilt,
            parallax_view,
            age_delta,
            market=market,
            covered_markets=covered_markets,
        )
        resolutions.append({
            "dim": path,
            "state": state,
            "cio_tilt": cio_tilt,
            "parallax_view": parallax_view,
            "market": market,
            "parallax_summary": _summarize_parallax(parallax_view),
        })
    return resolutions


def _summarize_parallax(value: Any) -> str:
    if value is None:
        return "(imputed view silent)"
    if isinstance(value, (int, float)):
        return f"imputed={value:+}" if isinstance(value, int) else f"imputed={value}"
    return str(value)[:120]


# ---------------------------------------------------------------------------
# Phase 4: build recommended deltas
# ---------------------------------------------------------------------------


def phase_4_build_deltas(
    resolutions: list[dict[str, Any]],
    cio_age_days: int,
    parallax_age_days: int,
) -> list[dict[str, Any]]:
    """Reuse stress.build_recommended_deltas with include_fresh=True.

    Judge-specific: every DIVERGENT_FRESH delta carries
    kind="informational_fresh" (per A1 work; validator allowlist already
    extended).
    """
    return stress.build_recommended_deltas(
        resolutions,
        cio_age_days=cio_age_days,
        parallax_age_days=parallax_age_days,
        include_fresh=True,
    )


# ---------------------------------------------------------------------------
# Phase 5: LLM-as-judge recommendations
# ---------------------------------------------------------------------------


def phase_5_recommendations(
    resolutions: list[dict[str, Any]],
    severity: str,
    *,
    view: stress.View,
    mcp_responses: dict[str, Any],
    llm_call_fn: Callable[[dict[str, Any]], dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Generate per-cell recommendations for material-drift cells.

    For each cell at ``drift_material`` (or stricter) severity, call the
    injected LLM via ``llm_call_fn`` and then citation-validate the
    result. Cells that fail the check get the decline placeholder.

    The LLM call shape:
        llm_call_fn(prompt_dict) -> response_dict
    where ``prompt_dict`` is the output of build_recommendation_prompt
    and ``response_dict`` is the LLM's structured-output reply.

    When ``llm_call_fn`` is None, no recommendations are emitted. This
    is the test default (recommendations are exercised end-to-end via
    explicit injection).
    """
    if llm_call_fn is None or severity not in ("drift_material", "drift_breaking"):
        return []

    recommendations: list[dict[str, Any]] = []
    metadata = view.data.get("metadata", {}) or {}
    effective_date = metadata.get("effective_date")

    for r in resolutions:
        if r.get("state") not in ("DIVERGENT_FRESH", "DIVERGENT_STALE"):
            continue
        path = r.get("dim", "")
        snippet = _extract_snippet_for_path(path, r, mcp_responses)
        if not snippet:
            # No snippet → cannot ask LLM (would have nothing to cite).
            recommendations.append(
                rec_mod.make_decline_placeholder(
                    path=path,
                    state=r.get("state", ""),
                    severity=severity,
                    reason="no source snippet available for this cell",
                )
            )
            continue
        prompt = rec_mod.build_recommendation_prompt(
            path=path,
            cio_value=r.get("cio_tilt"),
            parallax_value=r.get("parallax_view"),
            effective_date=effective_date,
            tool=r.get("source_tool", "macro_analyst"),
            args=r.get("source_args"),
            parallax_date=r.get("parallax_date"),
            source_snippet=snippet,
            state=r.get("state", ""),
            severity=severity,
        )
        try:
            raw = llm_call_fn(prompt)
        except Exception as exc:
            recommendations.append(
                rec_mod.make_decline_placeholder(
                    path=path,
                    state=r.get("state", ""),
                    severity=severity,
                    reason=f"LLM call raised {exc.__class__.__name__}: {exc}",
                )
            )
            continue
        record, _ok = rec_mod.apply_recommendation_or_decline(
            snippet=prompt["snippet_for_validation"],
            recommendation=raw,
            path=path,
            state=r.get("state", ""),
            severity=severity,
        )
        recommendations.append(record)
    return recommendations


def _extract_snippet_for_path(
    path: str,
    resolution: dict[str, Any],
    mcp_responses: dict[str, Any],
) -> str:
    """Best-effort snippet pull for one cell.

    Region cells pull from the matching market's macro_analyst content;
    sector cells use the sectors component when available; everything
    else falls back to telemetry commentary. The resolution itself can
    pre-fill ``source_snippet`` when the orchestrator already extracted
    it from the maker pipeline — we honor that field first.
    """
    if resolution.get("source_snippet"):
        return resolution["source_snippet"]

    segments = path.split(".")
    market = resolution.get("market")
    # Look up candidate response keys.
    candidates = []
    if market:
        candidates.extend([
            f"macro_analyst:{market}:macro_indicators",
            f"macro_analyst:{market}:tactical",
        ])
    if len(segments) >= 3 and segments[1] == "sectors":
        candidates.extend([
            "macro_analyst:United_States:sectors",
            "macro_analyst:United_States:sector_positioning",
        ])
    candidates.append("get_telemetry:commentary")

    for key in candidates:
        resp = mcp_responses.get(key)
        if isinstance(resp, dict):
            content = resp.get("content") or resp.get("commentary")
            if isinstance(content, dict):
                content = content.get("headline", "")
            if isinstance(content, str) and content.strip():
                return content
    return ""


# ---------------------------------------------------------------------------
# Phase 6+7: render + audit
# ---------------------------------------------------------------------------


def phase_6_render_and_phase_7_audit(
    *,
    view: stress.View,
    config: JudgeConfig,
    trigger: str,
    severity: str,
    severity_details: dict[str, Any],
    drift_summary: dict[str, int],
    resolutions: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
    view_age_days: int,
    parallax_age_days: int,
    mcp_responses: dict[str, Any],
    judged_at: datetime.datetime,
) -> tuple[Path, dict[str, Any], str]:
    """Write the report bundle and append the audit row.

    Returns (report_dir, audit_entry, json_payload).
    """
    judged_view_id = view.data.get("metadata", {}).get("view_id", "<unknown>")
    judged_version_id = view.data.get("metadata", {}).get("version_id", "<unknown>")

    # Report bundle directory. The 6-char hex nonce disambiguates two judge
    # runs against the same view within one wall-clock second (e.g.,
    # cron-fired auto-on-load drift check overlapping an operator-triggered
    # /parallax-judge-house-view). 6 hex chars = 16.7M possibilities;
    # collision probability for two same-second runs ≈ 6e-8 (operationally
    # negligible). Without the nonce, the second run's report.md/json/
    # mcp_responses.jsonl/audit_entry.json would silently overwrite the
    # first's via render_judge.py's `mkdir(exist_ok=True)` — audit.jsonl
    # is fine (flock-protected) but the user-facing bundles collide.
    # See test_e2e_concurrency.py Test 1.
    base = config.report_dir or DEFAULT_REPORT_DIR
    nonce = uuid.uuid4().hex[:6]
    bundle_name = (
        f"{judged_version_id}-"
        f"{_isoformat(judged_at).replace(':', '').replace('-', '')}-{nonce}"
    )
    out_dir = Path(base) / bundle_name

    md = render_judge.render_markdown_report(
        view_meta=view.data.get("metadata", {}),
        judged_view_id=judged_view_id,
        judged_version_id=judged_version_id,
        view_age_days=view_age_days,
        parallax_age_days=parallax_age_days,
        severity=severity,
        severity_details=severity_details,
        drift_summary=drift_summary,
        resolutions=resolutions,
        recommendations=recommendations,
        pillars_only=config.pillars_only,
        trigger=trigger,
        judged_at=judged_at,
    )
    json_payload = render_judge.render_json_sidecar(
        view_meta=view.data.get("metadata", {}),
        judged_view_id=judged_view_id,
        judged_version_id=judged_version_id,
        view_age_days=view_age_days,
        parallax_age_days=parallax_age_days,
        severity=severity,
        severity_details=severity_details,
        drift_summary=drift_summary,
        resolutions=resolutions,
        recommendations=recommendations,
        trigger=trigger,
        judged_at=judged_at,
    )
    render_judge.write_report_bundle(
        output_dir=out_dir, markdown=md, json_sidecar=json_payload
    )

    # mcp_responses.jsonl
    mcp_log_path = out_dir / "mcp_responses.jsonl"
    with mcp_log_path.open("w", encoding="utf-8") as f:
        for key, resp in mcp_responses.items():
            f.write(json.dumps({"call": key, "response": resp}, default=str) + "\n")
    mcp_log_path.chmod(0o600)

    # Phase 7: single audit row, applied=false (always).
    entry_data = {
        "ts": _isoformat(judged_at),
        "view_id": judged_view_id,
        "version_id": judged_version_id,
        "view_hash": view.view_hash,
        "skill": SKILL_NAME,
        "action": "judge",
        "applied": False,
        "judged_view_id": judged_view_id,
        "judged_version_id": judged_version_id,
        "view_age_days": view_age_days,
        "parallax_age_days": parallax_age_days,
        "drift_summary": drift_summary,
        "recommendations": deltas,
    }
    audit_entry = audit_chain.append_entry(view.audit_path, entry_data)

    # Persist a copy alongside the report bundle for offline auditors.
    audit_copy_path = out_dir / "audit_entry.json"
    audit_copy_path.write_text(json.dumps(audit_entry, indent=2, default=str))
    audit_copy_path.chmod(0o600)

    return out_dir, audit_entry, json_payload


# ---------------------------------------------------------------------------
# Phase 8: reasoning chain
# ---------------------------------------------------------------------------


def _serialize_mcp_for_chain(mcp_responses: dict[str, Any]) -> dict[str, Any]:
    """Convert mcp_responses to a YAML-serializable plain-dict form.

    The orchestrator carries `per_market` as a list of dataclass
    ``MarketResponse`` objects (from the maker module). chain_emit
    writes YAML via PyYAML's default Dumper, which can't represent
    arbitrary dataclasses. ALSO used as the input to ``_response_hash``
    so the hash is computed over canonical JSON-able structures rather
    than dataclass ``__repr__`` strings (would silently change if
    MarketResponse fields reorder).

    Mirrors maker.MCPResponses.as_chain_payload's intent but stays
    dict-shaped (chain spec accepts dict for response_inline).
    """
    out: dict[str, Any] = {}
    for k, v in mcp_responses.items():
        if isinstance(v, list):
            out[k] = [
                dataclasses.asdict(item)
                if dataclasses.is_dataclass(item) and not isinstance(item, type)
                else item
                for item in v
            ]
        elif dataclasses.is_dataclass(v) and not isinstance(v, type):
            out[k] = dataclasses.asdict(v)
        else:
            out[k] = v
    return out


def phase_8_emit_chain(
    *,
    view: stress.View,
    mcp_responses: dict[str, Any],
    audit_entry: dict[str, Any],
    judged_at: datetime.datetime,
) -> Path:
    """Emit a reasoning chain via chain_emit.emit_phase_0_chain.

    The judge does not produce a portfolio (it's a model-validation
    tool), so ``final_portfolio.weights`` is empty per spec §3.5
    (empty-portfolio allowance documented in chain_emit normalizer).

    ``base_scores.response_inline`` carries the aggregated MCP response
    payload; ``base_scores.response_hash`` is the deterministic anchor.
    """
    run_id = str(uuid.uuid4())
    # Serialize dataclass MarketResponse instances to plain dicts before
    # handing to chain_emit (PyYAML can't represent arbitrary dataclasses).
    # Pass the SAME serialized form to _response_hash so the hash is
    # canonical JCS over plain dicts rather than dataclass __repr__
    # strings (which would silently change if MarketResponse fields
    # reorder, violating §6.4 stability).
    serializable_mcp = _serialize_mcp_for_chain(mcp_responses)
    return chain_emit.emit_phase_0_chain(
        view=view.data,
        base_scores={
            "response_inline": serializable_mcp,
            "response_hash": _response_hash(serializable_mcp),
        },
        final_portfolio={"weights": {}},
        run_id=run_id,
        skill_version=SKILL_VERSION,
        skill=SKILL_NAME,
        notes=(
            f"judge run for view_id={audit_entry.get('view_id', '?')[:8]} "
            f"at {_isoformat(judged_at)}"
        ),
    )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def run_judge(
    *,
    config: JudgeConfig | None = None,
    mcp_call_fn: Callable[..., dict[str, Any]] | None = None,
    llm_call_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    covered_markets: set[str] | None = None,
) -> JudgeResult:
    """Top-level orchestrator. Implements Phases 0-8 from v2 plan §3.1.

    Args:
        config: Knobs / CLI flags.
        mcp_call_fn: Caller-supplied MCP dispatcher. In live mode the
            Claude skill runtime wires this. In tests, an inject-able fake.
        llm_call_fn: Caller-supplied LLM dispatcher for Phase 5. Same
            inversion as mcp_call_fn. Tests pass a stub.
        covered_markets: Set of markets in Parallax coverage (from
            list_macro_countries). Passed through to
            stress.resolve_cell_state.

    Returns:
        Populated ``JudgeResult``.
    """
    config = config or JudgeConfig()
    now = _utcnow()
    diagnostics: list[str] = []

    # Phase 0
    view = phase_0_load_view(config.view_dir)
    view_age_days = _view_age_days(view.data, now)

    # Trigger resolution (informational — affects banner only).
    trigger, should_run = cadence.resolve_trigger(
        explicit=config.explicit,
        scheduled=config.scheduled,
        view_age_days=view_age_days,
    )
    if not should_run:
        # Auto-on-load below the age threshold: surface a no-op result.
        diagnostics.append(
            f"auto-on-load suppressed: view_age_days={view_age_days} < "
            f"{cadence.AUTO_ON_LOAD_MIN_AGE_DAYS}"
        )
        return JudgeResult(
            severity="drift_minor",
            severity_details={"reason": "auto-on-load below threshold"},
            drift_summary={},
            diagnostics=diagnostics,
        )

    # Phase 1
    mcp_responses = phase_1_fan_out(config, mcp_call_fn)
    if not mcp_responses:
        diagnostics.append("MCP fan-out returned no responses")

    # Imputed view via maker modules (if available).
    maker = probe_maker_modules()
    diagnostics.append(maker.diagnostic)
    # Load aggregator weights from the shared yaml — mirrors maker.aggregate
    # at maker.py:402. Empty weights silently zero out the 60% coverage gate
    # and nullify every cross-country field, so on load failure we pass None
    # (which makes cross_country.aggregate self-load via its internal
    # `if weights is None: weights = load_weights()` guard) rather than {}.
    weights: dict[str, Any] | None = None
    if maker.available:
        try:
            weights = maker.cross_country.load_weights()
        except Exception as exc:
            diagnostics.append(
                f"weights load failed: {exc}; passing None so aggregate() self-loads"
            )
            weights = None
    imputed_view = _imputed_view_from_maker(
        maker, mcp_responses, weights=weights, inventory=None
    )

    # Phase 2
    parallax_age_days = _parallax_age_days(mcp_responses, now)
    cio_age_days = view_age_days
    age_delta = stress.compute_age_delta(cio_age_days, parallax_age_days)
    resolutions = phase_2_resolve_cells(
        view=view,
        imputed_view=imputed_view,
        age_delta=age_delta,
        covered_markets=covered_markets,
    )

    # Phase 3
    dims, _markets = stress.enumerate_dimensions(view)
    denominator = len(dims)
    severity, severity_details = drift_classify.classify_severity(
        resolutions=resolutions,
        view_age_days=view_age_days,
        denominator=denominator,
    )
    drift_summary = drift_classify.summarize_states(resolutions)

    # Phase 4
    deltas = phase_4_build_deltas(
        resolutions=resolutions,
        cio_age_days=cio_age_days,
        parallax_age_days=parallax_age_days,
    )

    # Phase 5 — only at material+ severity. The LLM call shape is
    # injected; tests run with llm_call_fn=None and assert zero recs.
    recommendations = phase_5_recommendations(
        resolutions=resolutions,
        severity=severity,
        view=view,
        mcp_responses=mcp_responses,
        llm_call_fn=llm_call_fn,
    )

    # Phase 6 + 7
    report_dir, audit_entry, json_payload = phase_6_render_and_phase_7_audit(
        view=view,
        config=config,
        trigger=trigger,
        severity=severity,
        severity_details=severity_details,
        drift_summary=drift_summary,
        resolutions=resolutions,
        recommendations=recommendations,
        deltas=deltas,
        view_age_days=view_age_days,
        parallax_age_days=parallax_age_days,
        mcp_responses=mcp_responses,
        judged_at=now,
    )

    # Phase 8
    chain_emit_failed = False
    try:
        chain_path = phase_8_emit_chain(
            view=view,
            mcp_responses=mcp_responses,
            audit_entry=audit_entry,
            judged_at=now,
        )
    except Exception as exc:
        diagnostics.append(f"chain_emit raised {exc.__class__.__name__}: {exc}")
        chain_path = None
        chain_emit_failed = True

    return JudgeResult(
        severity=severity,
        severity_details=severity_details,
        drift_summary=drift_summary,
        resolutions=resolutions,
        recommendations=recommendations,
        report_dir=report_dir,
        audit_entry=audit_entry,
        chain_path=chain_path,
        chain_emit_failed=chain_emit_failed,
        diagnostics=diagnostics,
        json_payload=json_payload,
    )


# ---------------------------------------------------------------------------
# CLI entry point — kept thin; main UX is via the Claude skill SKILL.md
# ---------------------------------------------------------------------------


def _build_argparser():
    import argparse

    p = argparse.ArgumentParser(
        prog="parallax-judge-house-view",
        description="Read-only LLM-as-judge for an active Parallax house view.",
    )
    p.add_argument("--pillars-only", action="store_true",
                   help="Suppress per-cell table; pillar drift only.")
    p.add_argument("--json", action="store_true",
                   help="Print JSON sidecar to stdout in addition to the bundle.")
    p.add_argument("--dry", action="store_true",
                   help="Use mocked MCP responses (requires --mock-mcp).")
    p.add_argument("--mock-mcp", type=str, default=None,
                   help="Path to JSON file with mock MCP responses (with --dry).")
    p.add_argument("--scheduled", action="store_true",
                   help="Mark this as a scheduled / cron run for audit.")
    p.add_argument("--view-dir", type=str, default=None,
                   help="Override active-view directory.")
    p.add_argument("--report-dir", type=str, default=None,
                   help="Override judge-reports directory.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    mock_responses = None
    if args.dry:
        if not args.mock_mcp:
            print("--dry requires --mock-mcp <path>", file=sys.stderr)
            return 2
        mock_responses = json.loads(Path(args.mock_mcp).read_text())
    config = JudgeConfig(
        pillars_only=args.pillars_only,
        json_output=args.json,
        dry=args.dry,
        explicit=not args.scheduled,
        scheduled=args.scheduled,
        view_dir=Path(args.view_dir) if args.view_dir else None,
        report_dir=Path(args.report_dir) if args.report_dir else None,
        mock_mcp_responses=mock_responses,
    )
    result = run_judge(config=config)
    if args.json:
        print(result.json_payload or "")
    else:
        print(f"verdict: {result.severity}")
        if result.report_dir:
            print(f"report:  {result.report_dir}")
        if result.chain_path:
            print(f"chain:   {result.chain_path}")
        for d in result.diagnostics:
            print(f"note:    {d}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
