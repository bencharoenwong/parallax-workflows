"""Maker orchestrator for `/parallax-make-house-view` (Phase B1).

Implements the 8-step orchestration from v2 plan §2.1:

  1. list_macro_countries()                     [Batch 0; 1 call]
  2. Fan-out macro_analyst(market, component)   [Batch 1; ≤14×5=70 calls]
  3. get_telemetry(fields=[...])                [Batch 2; parallel with Batch 1]
  4. cross_country.aggregate(...)               [pure compute]
  5. pillar_compose.compute_pillars(...)        [pure compute]
  6. (OPTIONAL) gap_suggest.fold_responses(...) [residual silent fields]
  7. GateContext → gate_present.run_gate_loop   [shared confirmation]
  8. Reuse load-house-view Step 4 path          [save + audit + chain]

This module is the orchestrator code. The skill operator (Claude) is
responsible for actually issuing parallel MCP calls — the orchestrator
exposes `MakerOrchestrator.execute_synthesis(mcp_runner)` where
`mcp_runner` is a callable abstraction over MCP fan-out the skill
provides at invoke time.

Design notes:
- Does NOT modify shared infra (audit_chain, manifest_cache, chain_emit,
  view_status, gate_present, provenance_classes). Reuses only.
- Save path is `_save_via_load_house_view_path` which mirrors
  skills/load-house-view/SKILL.md Step 4 verbatim, with action="generate"
  and provenance class generator_synthesis.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

# ----- Path resolution: maker imports cross_country / pillar_compose -----
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_SHARED_DIR = (_HERE / ".." / "_parallax" / "house-view").resolve()
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

import audit_chain  # noqa: E402
import chain_emit  # noqa: E402
import gate_present  # noqa: E402
import provenance_classes  # noqa: E402
import view_status  # noqa: E402

import cross_country  # noqa: E402
import pillar_compose  # noqa: E402
import prose_synth  # noqa: E402
from cross_country import MarketResponse  # noqa: E402
from pillar_formulas import PillarResult  # noqa: E402

logger = logging.getLogger(__name__)

SKILL_VERSION = "parallax-make-house-view@1.0.0"
SKILL_NAME = "parallax-make-house-view"

DEFAULT_VIEW_DIR = Path("~/.parallax/active-house-view").expanduser()

# Default components fanned out per market (MCP_FIELD_INVENTORY.md §5.3).
DEFAULT_COMPONENTS = (
    "macro_indicators",
    "tactical",
    "sectors",
    "fixed_income",
    "news",
)

# Concurrency cap (v2 plan §2.1).
DEFAULT_CONCURRENCY = 8

# Per-market timeout (v2 plan §2.1).
DEFAULT_MARKET_TIMEOUT_S = 45

# Schema-side region key for each Parallax market name. Includes all
# markets observed via list_macro_countries (MCP_FIELD_INVENTORY.md §1).
MARKET_TO_SCHEMA_KEY: dict[str, str] = {
    "United States": "us",
    "Canada": "canada",
    "France": "france",
    "Germany": "germany",
    "Japan": "japan",
    "Singapore": "singapore",
    "United Kingdom": "uk",
    "China": "china",
    "India": "india",
    "Indonesia": "indonesia",
    "Malaysia": "malaysia",
    "South Korea": "south_korea",
    "Taiwan": "taiwan",
    "Thailand": "thailand",
}

# Hardcoded fallback if list_macro_countries fails. Per parallax-conventions
# §6 "Macro fallback from RIC suffixes" — we use the 14 known-covered markets.
HARDCODED_COVERAGE = tuple(MARKET_TO_SCHEMA_KEY.keys())

# Threshold above which we hard-abort the run because the fan-out coverage
# is so degraded that aggregation can't produce reliable pillars (v2 plan §2.2).
UNREACHABLE_ABORT_SHARE = 0.30


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------


@dataclass
class MakerOptions:
    """CLI-derived options surface."""

    shadow_diff: bool = False
    basis_hint: str | None = None
    market_filter: list[str] | None = None  # e.g. ["us", "japan"]
    status_only: bool = False
    view_dir: Path = DEFAULT_VIEW_DIR
    components: tuple[str, ...] = DEFAULT_COMPONENTS
    concurrency: int = DEFAULT_CONCURRENCY
    market_timeout_s: int = DEFAULT_MARKET_TIMEOUT_S
    weights_path: Path | None = None


@dataclass
class MCPResponses:
    """Aggregate of all MCP responses captured during fan-out.

    Carried into chain_emit's base_scores.response_inline + response_hash.
    """

    list_macro_countries: dict[str, Any] | None = None
    per_market: list[MarketResponse] = field(default_factory=list)
    telemetry: dict[str, Any] | None = None

    def as_chain_payload(self) -> tuple[dict[str, Any], str]:
        """Build response_inline + response_hash for chain_emit.

        Ordered, sorted, JSON-canonicalized for hash stability.
        """
        ordered: list[tuple[str, str, Any]] = []
        if self.list_macro_countries is not None:
            ordered.append(("list_macro_countries", "{}", self.list_macro_countries))
        if self.telemetry is not None:
            ordered.append(("get_telemetry", "{}", self.telemetry))
        for m in self.per_market:
            for comp, resp in sorted((m.components or {}).items()):
                if resp is None:
                    continue
                arg_str = json.dumps(
                    {"market": m.market_name, "component": comp}, sort_keys=True
                )
                ordered.append((f"macro_analyst:{m.market_name}:{comp}", arg_str, resp))
        ordered.sort(key=lambda x: (x[0], x[1]))

        concat_parts: list[bytes] = []
        for tool, args, resp in ordered:
            try:
                payload = json.dumps(
                    {"t": tool, "a": args, "r": resp},
                    sort_keys=True,
                    default=str,
                ).encode("utf-8")
            except (TypeError, ValueError):
                payload = json.dumps(
                    {"t": tool, "a": args, "r": repr(resp)},
                    sort_keys=True,
                ).encode("utf-8")
            concat_parts.append(payload)
        concat = b"\n".join(concat_parts) if concat_parts else b""
        response_hash = hashlib.sha256(concat).hexdigest()

        inline = {
            "list_macro_countries": self.list_macro_countries,
            "telemetry": self.telemetry,
            "per_market_summary": [
                {
                    "market": m.market_name,
                    "schema_key": m.schema_key,
                    "reachable": m.reachable,
                    "components_received": sorted(
                        [c for c, r in (m.components or {}).items() if r is not None]
                    ),
                }
                for m in self.per_market
            ],
        }
        return inline, response_hash


@dataclass
class MakerResult:
    """Final result of `execute_synthesis`."""

    disposition: (
        str  # "confirm" | "edited" | "regenerated" | "abandoned" | "shadow_diff"
    )
    draft_view: dict[str, Any] | None
    view_id: str | None = None
    version_id: str | None = None
    saved_paths: dict[str, Path] | None = None
    chain_path: Path | None = None
    audit_entry: dict[str, Any] | None = None
    shadow_diff_report: str | None = None
    pillars: dict[str, PillarResult] | None = None
    aggregated: dict[str, Any] | None = None
    mcp_responses: MCPResponses | None = None


# ---------------------------------------------------------------------------
# MCP runner abstraction
# ---------------------------------------------------------------------------


class MCPRunner:
    """Caller-supplied abstraction for issuing parallel MCP calls.

    The Claude operator implements this by closing over its
    `mcp__claude_ai_Parallax__*` tool surface. Tests pass a synthetic
    runner that returns fixture responses.

    Methods are documented as "as if parallel" — implementations should
    actually batch via the concurrency cap; the orchestrator does NOT
    serialize calls inside this contract.
    """

    def list_macro_countries(self) -> dict[str, Any] | None:
        raise NotImplementedError

    def get_telemetry(self, fields: list[str]) -> dict[str, Any] | None:
        raise NotImplementedError

    def macro_analyst_batch(
        self,
        requests: list[tuple[str, str]],  # (market_name, component_name)
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        per_call_timeout_s: int = DEFAULT_MARKET_TIMEOUT_S,
    ) -> dict[tuple[str, str], dict[str, Any] | None]:
        """Fire all (market, component) requests with concurrency cap.

        Returns {(market, component): response_dict_or_None}. None entries
        indicate UNREACHABLE for that request — caller distinguishes
        market-level vs component-level reachability.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class MakerOrchestrator:
    options: MakerOptions

    # ---- Step 1: list_macro_countries (+ Step 1.5: filter) ----

    def resolve_covered_markets(
        self, mcp: MCPRunner
    ) -> tuple[list[str], dict[str, Any] | None]:
        """Step 1. Returns (market_names, raw_response).

        Excludes "Global" from per-country fan-out (MCP_FIELD_INVENTORY.md §1).
        Applies CLI market filter when present.
        """
        raw = None
        try:
            raw = mcp.list_macro_countries()
        except Exception as exc:  # pragma: no cover — exercised in tests
            logger.warning(
                "maker.list_macro_countries.failed (falling back to hardcoded): %s",
                exc,
            )
            raw = None

        if raw is None or not raw.get("success", True):
            logger.warning(
                "maker.list_macro_countries.unavailable — using hardcoded coverage"
            )
            markets = list(HARDCODED_COVERAGE)
        else:
            entries = raw.get("countries") or raw.get("markets") or []
            markets = [m for m in entries if isinstance(m, str)]
            # Defensive: if Parallax returns a list of dicts instead of strs.
            if not markets:
                for row in entries:
                    if isinstance(row, dict):
                        name = row.get("name") or row.get("market")
                        if isinstance(name, str):
                            markets.append(name)
            markets = [m for m in markets if m and m.lower() != "global"]
            if not markets:
                markets = list(HARDCODED_COVERAGE)

        # CLI filter: e.g. options.market_filter = ["us", "japan"] → keep
        # only those Parallax market names.
        if self.options.market_filter:
            schema_filter = {k.strip().lower() for k in self.options.market_filter}
            keep = []
            for m in markets:
                schema_key = MARKET_TO_SCHEMA_KEY.get(m)
                if schema_key and schema_key in schema_filter:
                    keep.append(m)
            markets = keep

        return markets, raw

    # ---- Step 2+3: parallel fan-out + telemetry ----

    def fan_out(
        self, mcp: MCPRunner, covered_markets: list[str]
    ) -> tuple[list[MarketResponse], dict[str, Any] | None]:
        """Steps 2 + 3 fired in parallel by the caller's runner.

        Returns (per_market_responses, telemetry_response).
        """
        requests = [
            (market, comp)
            for market in covered_markets
            for comp in self.options.components
        ]

        # The runner is responsible for parallel dispatch. The orchestrator
        # does NOT serialize. We do measure wall-clock for telemetry.
        t0 = time.monotonic()

        telemetry: dict[str, Any] | None = None
        results: dict[tuple[str, str], dict[str, Any] | None] = {}

        try:
            results = mcp.macro_analyst_batch(
                requests,
                concurrency=self.options.concurrency,
                per_call_timeout_s=self.options.market_timeout_s,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("maker.fan_out.batch.failed: %s", exc)
            results = {(m, c): None for (m, c) in requests}

        try:
            telemetry = mcp.get_telemetry(
                fields=[
                    "regime_tag",
                    "divergences",
                    "factor_view.factors",
                    "factor_view.commentary",
                    "signals",
                    "commentary",
                ]
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("maker.get_telemetry.failed: %s", exc)
            telemetry = None

        elapsed = time.monotonic() - t0
        logger.info(
            "maker.fan_out.complete: %d requests in %.2fs (markets=%d, components=%d)",
            len(requests),
            elapsed,
            len(covered_markets),
            len(self.options.components),
        )

        per_market: list[MarketResponse] = []
        for market in covered_markets:
            comp_responses: dict[str, dict[str, Any] | None] = {}
            partial: list[str] = []
            any_reachable = False
            for comp in self.options.components:
                resp = results.get((market, comp))
                comp_responses[comp] = resp
                if resp is not None:
                    any_reachable = True
                    # PARTIAL detection done downstream by cross_country.
                else:
                    partial.append(comp)
            per_market.append(
                MarketResponse(
                    market_name=market,
                    schema_key=MARKET_TO_SCHEMA_KEY.get(
                        market, market.lower().replace(" ", "_")
                    ),
                    components=comp_responses,
                    reachable=any_reachable,
                    partial_components=tuple(partial),
                )
            )

        return per_market, telemetry

    # ---- Step 4: aggregate ----

    def aggregate(
        self,
        per_market: list[MarketResponse],
        telemetry: dict[str, Any] | None,
    ) -> dict[str, Any]:
        weights = cross_country.load_weights(self.options.weights_path)
        return cross_country.aggregate(per_market, telemetry, weights=weights)

    # ---- Step 5: pillars ----

    def compose_pillars(
        self,
        aggregated: dict[str, Any],
        telemetry: dict[str, Any] | None,
        *,
        psychological_judge_fn: Callable | None = None,
    ) -> dict[str, PillarResult]:
        return pillar_compose.compute_pillars(
            aggregated,
            telemetry,
            inventory=None,
            psychological_judge_fn=psychological_judge_fn,
        )

    # ---- Step 6: package the draft view ----

    def build_draft_view(
        self,
        aggregated: dict[str, Any],
        pillars: dict[str, PillarResult],
        covered_markets: list[str],
        *,
        view_id: str,
        version_id: str,
        parent_version_id: str | None,
    ) -> dict[str, Any]:
        """Construct the draft view dict matching schema.yaml shape."""
        pillar_values = pillar_compose.pillar_values_for_view(pillars)

        # Build tilts.regions from aggregated.regions (per-market, bypass coverage).
        regions = {k: int(v) for k, v in (aggregated.get("regions") or {}).items()}
        # Build tilts.sectors from coverage-gated aggregated.sectors (rounded).
        sectors = {
            k: int(round(float(v)))
            for k, v in (aggregated.get("sectors") or {}).items()
        }

        macro_regime = aggregated.get("macro_regime") or {}

        now_iso = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )

        basis = (
            f"Synthesized by /parallax-make-house-view@{SKILL_VERSION} from "
            f"Parallax macro_analyst + telemetry on {now_iso}. "
            f"Markets queried: {len(covered_markets)}."
        )
        if self.options.basis_hint:
            basis = f"{basis} Basis hint: {self.options.basis_hint}"

        # Avg pillar confidence for extraction_confidence.pillars; per-category
        # confidence reduced from synthesis fan-out summary.
        pillar_conf = pillar_compose.pillar_confidence_average(pillars)
        fan_out = aggregated.get("fan_out_summary") or {}
        n_total = fan_out.get("markets_total") or 1
        n_succ = fan_out.get("markets_succeeded") or 0
        succeed_ratio = n_succ / n_total if n_total else 0.0

        # Per-category extraction confidence approximated from fan-out success.
        category_conf = max(0.0, min(0.9, 0.4 + 0.5 * succeed_ratio))

        # Compute valuation_state/market_entropy specific confidence from pillar-level confidence.
        view = {
            "metadata": {
                "schema_version": 1,
                "calibration_status": "heuristic_phase0",
                "view_id": view_id,
                "view_name": f"Parallax synthesis {now_iso[:10]}",
                "uploaded_by": "parallax-make-house-view@system",
                "uploader_role": "Strategist",  # placeholder — gate may edit
                "upload_timestamp": now_iso,
                "effective_date": now_iso[:10],
                "valid_through": None,
                "auto_expire_days": 30,  # synthesized views expire faster
                "basis_statement": basis,
                "source_documents": [],
                "version_id": version_id,
                "parent_version_id": parent_version_id,
                "view_hash": "<computed_at_save>",
            },
            "tilts": {
                "pillars": pillar_values,
                "sectors": sectors,
                "regions": regions,
                "factors": {},
                "styles": {},
                "themes": {},
                "excludes": [],
                "exclude_reasons": [],
                "tilt_conviction": {},
                "macro_regime": macro_regime,
            },
            "extraction": {
                "source_type": "url",  # synthesized via MCP; closest match in enum
                "extraction_method": SKILL_VERSION,
                "extracted_at": now_iso,
                "extraction_confidence": {
                    "pillars": pillar_conf,
                    "sectors": category_conf,
                    "regions": category_conf,
                    "factors": 0.0,  # maker doesn't populate factors in v0
                    "styles": 0.0,
                    "themes": 0.0,
                    "excludes": 1.0,  # empty list — trivially confident
                    "macro_regime": (
                        max(0.3, category_conf) if macro_regime.get("growth") else 0.0
                    ),
                },
                "extraction_notes": (
                    f"Synthesized from {n_succ}/{n_total} markets. "
                    f"Fan-out summary: {json.dumps(fan_out, default=str)[:400]}"
                ),
                "uploader_confirmed": False,  # set True at confirmation gate
            },
        }
        return view

    # ---- Step 7: gate (delegated to caller) ----

    def build_gate_context(
        self, pillars: dict[str, PillarResult], view: dict[str, Any]
    ) -> gate_present.GateContext:
        pillar_conf = pillar_compose.pillar_confidence_average(pillars)
        extraction_conf = view["extraction"]["extraction_confidence"]
        now_iso = (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        return gate_present.GateContext(
            source_label=f"Parallax synthesis {now_iso}",
            uploader_present=False,
            confidence_map={
                "pillars": pillar_conf,
                "sectors": extraction_conf.get("sectors", 0.0),
                "regions": extraction_conf.get("regions", 0.0),
                "factors": extraction_conf.get("factors", 0.0),
                "macro_regime": extraction_conf.get("macro_regime", 0.0),
            },
            extraction_attempt_action=True,
            disposition_options=["confirm", "edit", "regenerate", "abandon"],
        )

    # ---- Step 8: save (reuses load-house-view Step 4 path) ----

    def save_view(
        self,
        view: dict[str, Any],
        pillars: dict[str, PillarResult],
        aggregated: dict[str, Any],
        mcp_responses: MCPResponses,
        covered_markets: list[str],
    ) -> tuple[dict[str, Path], str, str, dict[str, Any], Path | None]:
        """Compute hashes, write files, append audit, emit chain.

        Returns (saved_paths, view_id, version_id, audit_entry, chain_path).
        """
        view_dir = Path(self.options.view_dir)
        view_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(view_dir, 0o700)
        except OSError:
            pass

        # 1. view_hash per schema.yaml.
        view_hash = _compute_view_hash(view)
        view["metadata"]["view_hash"] = view_hash

        # 1b/1c. Provenance + provenance_hash.
        provenance_data = _build_provenance(view, pillars, aggregated, covered_markets)
        provenance_canonical = _jcs_dumps(provenance_data)
        provenance_hash = hashlib.sha256(provenance_canonical).hexdigest()
        view["metadata"]["provenance_hash"] = provenance_hash

        # Ensure uploader_confirmed=True at save time.
        view["extraction"]["uploader_confirmed"] = True

        # 7-9. Build prose body + prose_body_hash.
        prose_body = prose_synth.render_prose(
            view,
            fan_out_summary=aggregated.get("fan_out_summary"),
            pillar_missing_inputs={
                "econometrics_phase": pillars["omega"].missing_inputs,
                "valuation_state": pillars["phi"].missing_inputs,
                "market_entropy": pillars["xi"].missing_inputs,
                "psychological_wavelength": pillars["psi"].missing_inputs,
            },
        )
        prose_body_hash = hashlib.sha256(prose_body.encode("utf-8")).hexdigest()

        # 9. Write files (synchronous, simplified vs load-house-view's
        # multi-stage async/atomic flow — same end state, single write step).
        version_id = view["metadata"]["version_id"]

        view_path = view_dir / "view.yaml"
        prose_path = view_dir / "prose.md"
        provenance_path = view_dir / "provenance.yaml"
        audit_path = view_dir / "audit.jsonl"

        # YAML dumps with sorted keys for stability.
        view_yaml = yaml.safe_dump(
            view, sort_keys=True, default_flow_style=False, allow_unicode=True
        )
        view_path.write_text(view_yaml, encoding="utf-8")
        try:
            os.chmod(view_path, 0o600)
        except OSError:
            pass

        prose_frontmatter = (
            "---\n"
            f"paired_yaml_hash: {view_hash}\n"
            f"prose_body_hash: {prose_body_hash}\n"
            f"view_id: {view['metadata']['view_id']}\n"
            f"version_id: {version_id}\n"
            "---\n"
        )
        prose_path.write_text(prose_frontmatter + prose_body, encoding="utf-8")
        try:
            os.chmod(prose_path, 0o600)
        except OSError:
            pass

        provenance_yaml = yaml.safe_dump(
            provenance_data,
            sort_keys=True,
            default_flow_style=False,
            allow_unicode=True,
        )
        provenance_path.write_text(provenance_yaml, encoding="utf-8")
        try:
            os.chmod(provenance_path, 0o600)
        except OSError:
            pass

        # 11. Append audit entry (loader.md §6.1/§6.2 — generate row).
        source_tools = _build_source_tools_list(mcp_responses, covered_markets)
        audit_entry_payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "view_id": view["metadata"]["view_id"],
            "version_id": version_id,
            "view_hash": view_hash,
            "skill": SKILL_NAME,
            "action": "generate",
            "applied": True,
            "parent_version_id": view["metadata"].get("parent_version_id"),
            "provenance_hash": provenance_hash,
            "source_tools": source_tools,
            "calibration_status": "heuristic_phase0",
        }
        # FORBIDDEN per loader.md §6.2: composition_formula,
        # aggregator_weights_ref, source_snippets, pillar_missing_inputs
        # MUST NOT appear on the audit row. Defensive assert below.
        for forbidden in (
            "composition_formula",
            "aggregator_weights_ref",
            "source_snippets",
            "pillar_missing_inputs",
        ):
            if forbidden in audit_entry_payload:
                raise ValueError(
                    f"audit entry contains forbidden key {forbidden!r} per "
                    "loader.md §6.2 generate-row constraint"
                )

        final_audit_entry = audit_chain.append_entry(
            audit_path, audit_entry_payload, ensure_chained=True
        )
        try:
            os.chmod(audit_path, 0o600)
        except OSError:
            pass

        # 11a. Emit reasoning chain (Phase-0 / no manifest, see chain_emit).
        chain_path: Path | None = None
        try:
            inline, response_hash = mcp_responses.as_chain_payload()
            base_scores = {
                "response_inline": inline,
                "response_hash": response_hash,
            }
            chain_path = chain_emit.emit_phase_0_chain(
                view=view,
                base_scores=base_scores,
                final_portfolio={"weights": {}},  # maker produces no portfolio
                run_id=str(uuid.uuid4()),
                skill_version=SKILL_VERSION,
                skill=SKILL_NAME,
                sections_touched=[],
                notes=(
                    f"parallax-make-house-view synthesis; markets="
                    f"{len(covered_markets)}; pillars="
                    f"avg_conf={pillar_compose.pillar_confidence_average(pillars):.2f}"
                ),
            )
        except Exception as exc:  # pragma: no cover — non-blocking per SKILL.md
            logger.warning("maker.chain_emit.failed: %s", exc)

        saved_paths = {
            "view": view_path,
            "prose": prose_path,
            "provenance": provenance_path,
            "audit": audit_path,
        }
        return (
            saved_paths,
            view["metadata"]["view_id"],
            version_id,
            final_audit_entry,
            chain_path,
        )

    # ---- Top-level driver ----

    def execute_synthesis(
        self,
        mcp: MCPRunner,
        *,
        dispose_fn: Callable[[gate_present.GatePrompt], str] | None = None,
        edit_fn: (
            Callable[[dict, gate_present.GateContext], tuple[dict, str | None]] | None
        ) = None,
        psychological_judge_fn: (
            Callable[[list[str], str | None], tuple[int, str, float]] | None
        ) = None,
    ) -> MakerResult:
        """End-to-end Steps 1-8 driver.

        Args:
            mcp: caller-supplied MCPRunner (real MCP in production, mocked
                in tests).
            dispose_fn, edit_fn: gate callbacks. When None and
                shadow_diff=True, the gate is skipped (no save).
                When None and shadow_diff=False, raise — the gate REQUIRES
                a disposition path.
            psychological_judge_fn: optional structured-output Claude call wrapped as
                callable. Defaults to bag-of-words heuristic.

        Returns: MakerResult with the disposition + paths + pillars.
        """
        # Step 1
        covered_markets, raw_lmc = self.resolve_covered_markets(mcp)
        if not covered_markets:
            raise RuntimeError(
                "maker: no covered markets resolved — hard abort. "
                "Check list_macro_countries and MARKET_TO_SCHEMA_KEY."
            )

        # Step 2 + 3 (in parallel via runner)
        per_market, telemetry = self.fan_out(mcp, covered_markets)

        # v2 plan §2.2 hard abort: unreachable_share > 30%
        n_total = len(per_market) or 1
        n_unreachable = sum(1 for m in per_market if not m.reachable)
        unreachable_share = n_unreachable / n_total
        if unreachable_share > UNREACHABLE_ABORT_SHARE and n_unreachable > 0:
            raise RuntimeError(
                f"maker: unreachable_share={unreachable_share:.2f} > "
                f"{UNREACHABLE_ABORT_SHARE} — hard abort per v2 plan §2.2"
            )

        # Step 4
        aggregated = self.aggregate(per_market, telemetry)

        # Step 5
        pillars = self.compose_pillars(
            aggregated, telemetry, psychological_judge_fn=psychological_judge_fn
        )

        # Step 6 is OPTIONAL — only fold gap_suggest residuals when the maker
        # leaves leaves silent. v2 plan §2.1 step 6 explicitly defers.
        # For B1 we skip; explicit hook is left for follow-up integration.

        # Bundle MCP responses for chain_emit + audit.
        mcp_responses = MCPResponses(
            list_macro_countries=raw_lmc,
            per_market=per_market,
            telemetry=telemetry,
        )

        # Step 6.5: package draft
        # parent_version_id: detect existing view.
        parent_version_id = _read_parent_version_id(self.options.view_dir)
        view_id = _resolve_or_new_view_id(self.options.view_dir)
        version_id = str(uuid.uuid4())

        draft = self.build_draft_view(
            aggregated,
            pillars,
            covered_markets,
            view_id=view_id,
            version_id=version_id,
            parent_version_id=parent_version_id,
        )

        # Shadow-diff mode: do NOT route through gate, do NOT save.
        if self.options.shadow_diff:
            bank_view = _read_active_view(self.options.view_dir)
            from shadow_diff import render_shadow_diff

            report = render_shadow_diff(bank_view, draft, pillars=pillars)
            return MakerResult(
                disposition="shadow_diff",
                draft_view=draft,
                view_id=None,
                version_id=None,
                shadow_diff_report=report,
                pillars=pillars,
                aggregated=aggregated,
                mcp_responses=mcp_responses,
            )

        # Step 7: gate
        if dispose_fn is None:
            raise ValueError(
                "execute_synthesis() requires dispose_fn (or shadow_diff=True). "
                "The maker MUST route through gate_present.run_gate_loop "
                "before saving."
            )
        context = self.build_gate_context(pillars, draft)
        gate_result = gate_present.run_gate_loop(
            draft, context, dispose_fn=dispose_fn, edit_fn=edit_fn
        )

        if gate_result.disposition in ("abandoned", "regenerated"):
            return MakerResult(
                disposition=gate_result.disposition,
                draft_view=None,
                pillars=pillars,
                aggregated=aggregated,
                mcp_responses=mcp_responses,
            )

        # confirm / edited → use final_draft for save
        final_draft = gate_result.final_draft or draft

        # Step 8: save
        saved_paths, vid, ver, audit_entry, chain_path = self.save_view(
            final_draft, pillars, aggregated, mcp_responses, covered_markets
        )
        return MakerResult(
            disposition=gate_result.disposition,
            draft_view=final_draft,
            view_id=vid,
            version_id=ver,
            saved_paths=saved_paths,
            chain_path=chain_path,
            audit_entry=audit_entry,
            pillars=pillars,
            aggregated=aggregated,
            mcp_responses=mcp_responses,
        )


# ---------------------------------------------------------------------------
# Hash / canonicalization helpers
# ---------------------------------------------------------------------------


def _is_empty(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    if v is None:
        return True
    if isinstance(v, (int, float)) and v == 0:
        return True
    return v == "" or v == [] or v == {}


def _strip_empty(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            v = _strip_empty(v)
            if _is_empty(v):
                continue
            out[k] = v
        return out
    if isinstance(obj, list):
        result = []
        for x in obj:
            y = _strip_empty(x)
            if _is_empty(y):
                continue
            result.append(y)
        return result
    return obj


def _compute_view_hash(view: dict[str, Any]) -> str:
    """Per schema.yaml §view_hash computation — Rule 1..4 pinned alg."""
    body = {
        "tilts": _strip_empty(view.get("tilts", {})),
        "excludes": _strip_empty(view.get("excludes", []) or []),
    }
    canonical = yaml.safe_dump(
        body,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        width=1_000_000,
        indent=2,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _jcs_dumps(data: Any) -> bytes:
    """JSON Canonicalization Scheme (RFC 8785) via rfc8785 lib if present."""
    try:
        import rfc8785

        return rfc8785.dumps(data)
    except ImportError:  # pragma: no cover
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------------
# Provenance assembly
# ---------------------------------------------------------------------------


def _build_provenance(
    view: dict[str, Any],
    pillars: dict[str, PillarResult],
    aggregated: dict[str, Any],
    covered_markets: list[str],
) -> dict[str, Any]:
    """One generator_synthesis entry per non-neutral leaf.

    Per schema.yaml `generator_synthesis` class spec.
    """
    now_iso = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    aggregator_weights_ref = "aggregator_weights.yaml#global_macro_weights.v0"
    out: dict[str, Any] = {}

    fan_out_summary = aggregated.get("fan_out_summary") or {}

    # Pillars
    pillar_name_map = {
        "omega": ("tilts.pillars.econometrics_phase", "macro_indicators"),
        "phi": ("tilts.pillars.valuation_state", "macro_indicators"),
        "xi": ("tilts.pillars.market_entropy", "macro_indicators"),
        "psi": ("tilts.pillars.psychological_wavelength", "news"),
    }
    _tilts_pillars = (view.get("tilts") or {}).get("pillars") or {}
    for letter, (path, primary_comp) in pillar_name_map.items():
        p = pillars[letter]
        if p.value == 0 and not p.missing_inputs:
            continue
        source_tools = [f"macro_analyst:{m}:{primary_comp}" for m in covered_markets]
        if letter in ("omega", "psi", "xi"):
            source_tools.append("get_telemetry")
        entry = {
            "class": "generator_synthesis",
            "confidence": round(p.confidence, 4),
            "rationale": (
                f"Pillar {letter.upper()}: value={p.value:+d} via "
                f"{p.composition_formula}. "
                f"Markets succeeded: {fan_out_summary.get('markets_succeeded', 0)}/"
                f"{fan_out_summary.get('markets_total', 0)}."
            )[:500],
            "source_tools": source_tools,
            "composition_formula": p.composition_formula,
            "aggregator_weights_ref": aggregator_weights_ref,
            "data_as_of": now_iso,
        }
        if p.missing_inputs:
            entry["missing_inputs"] = p.missing_inputs
        if p.source_snippets:
            entry["source_snippets"] = [s[:200] for s in p.source_snippets]
        entry["fan_out_summary"] = fan_out_summary
        errs = provenance_classes.validate_provenance_entry(entry)
        if errs:
            raise ValueError(
                f"generator_synthesis entry for {path} failed validation: {errs}"
            )
        out[path] = entry

    # Regions (per-market tilts; single source per leaf)
    for region_key, val in (view.get("tilts") or {}).get("regions", {}).items():
        if val == 0:
            continue
        # Resolve the Parallax market name for source_tools.
        market_name = next(
            (m for m in covered_markets if MARKET_TO_SCHEMA_KEY.get(m) == region_key),
            region_key,
        )
        source_tools = [
            f"macro_analyst:{market_name}:macro_indicators",
            f"macro_analyst:{market_name}:tactical",
        ]
        entry = {
            "class": "generator_synthesis",
            "confidence": 0.55,
            "rationale": (
                f"Region tilt for {region_key}: {val:+d} from "
                f"{market_name} macro_indicators + tactical prose scoring."
            )[:500],
            "source_tools": source_tools,
            "composition_formula": "gap_suggest.macro_analyst_to_region_tilt@v1",
            "aggregator_weights_ref": aggregator_weights_ref,
            "data_as_of": now_iso,
        }
        out[f"tilts.regions.{region_key}"] = entry

    # Sectors (cross-country aggregated)
    sectors_coverage = aggregated.get("sectors_coverage") or {}
    for sector_key, val in (view.get("tilts") or {}).get("sectors", {}).items():
        if val == 0:
            continue
        cov = sectors_coverage.get(sector_key) or {}
        responded = cov.get("responded_markets") or []
        source_tools = [f"macro_analyst:{m}:sectors" for m in covered_markets]
        entry = {
            "class": "generator_synthesis",
            "confidence": 0.45 if cov.get("coverage_ok") else 0.20,
            "rationale": (
                f"Sector tilt for {sector_key}: {val:+d} via weighted-median "
                f"aggregation across {len(responded)} markets with usable data."
            )[:500],
            "source_tools": source_tools,
            "composition_formula": "cross_country.aggregate@v1:weighted_median_by_market_cap",
            "aggregator_weights_ref": aggregator_weights_ref,
            "data_as_of": now_iso,
        }
        if not cov.get("coverage_ok"):
            entry["missing_inputs"] = [
                f"sector_coverage_below_threshold: responded={len(responded)}"
            ]
        out[f"tilts.sectors.{sector_key}"] = entry

    # Macro regime
    macro = (view.get("tilts") or {}).get("macro_regime") or {}
    for leaf, val in macro.items():
        if val is None:
            continue
        entry = {
            "class": "generator_synthesis",
            "confidence": 0.55,
            "rationale": (
                f"Macro regime {leaf}={val!r} from telemetry.regime_tag scan."
            )[:500],
            "source_tools": ["get_telemetry"],
            "composition_formula": "cross_country._infer_*_token@v1",
            "aggregator_weights_ref": aggregator_weights_ref,
            "data_as_of": now_iso,
        }
        out[f"tilts.macro_regime.{leaf}"] = entry

    return out


def _build_source_tools_list(
    mcp_responses: MCPResponses, covered_markets: list[str]
) -> list[str]:
    """Per-tool:arg summary for audit row's source_tools field."""
    tools: list[str] = []
    if mcp_responses.list_macro_countries is not None:
        tools.append("list_macro_countries:")
    if mcp_responses.telemetry is not None:
        tools.append("get_telemetry:regime_tag,divergences,signals,commentary")
    for m in mcp_responses.per_market:
        for comp, resp in sorted((m.components or {}).items()):
            if resp is None:
                continue
            tools.append(f"macro_analyst:{m.market_name}:{comp}")
    return tools


# ---------------------------------------------------------------------------
# View directory helpers
# ---------------------------------------------------------------------------


def _read_active_view(view_dir: Path) -> dict[str, Any] | None:
    view_path = view_dir / "view.yaml"
    if not view_path.exists():
        return None
    try:
        with open(view_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _read_parent_version_id(view_dir: Path) -> str | None:
    v = _read_active_view(view_dir)
    if v is None:
        return None
    return (v.get("metadata") or {}).get("version_id")


def _resolve_or_new_view_id(view_dir: Path) -> str:
    """Reuse existing view_id when an active synthesized view exists; else new uuid."""
    v = _read_active_view(view_dir)
    if v is None:
        return str(uuid.uuid4())
    skill = (v.get("extraction") or {}).get("extraction_method") or ""
    if skill.startswith("parallax-make-house-view"):
        return (v.get("metadata") or {}).get("view_id") or str(uuid.uuid4())
    # Existing view was ingested, not synthesized — start a new view family.
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Status mode
# ---------------------------------------------------------------------------


def render_status(view_dir: Path | None = None) -> str:
    """Render `--status` output — last-generated view metadata."""
    view_dir = view_dir or DEFAULT_VIEW_DIR
    v = _read_active_view(view_dir)
    if v is None:
        return "No active house view found at " + str(view_dir)
    metadata = v.get("metadata") or {}
    extraction = v.get("extraction") or {}
    skill = extraction.get("extraction_method") or "unknown"
    is_synth = skill.startswith("parallax-make-house-view")

    status_helper = view_status.compute_status(view_dir=view_dir)

    lines = [
        status_helper.banner,
        "",
        "Last generated view",
        "───────────────────",
        f"Name:           {metadata.get('view_name', '<unset>')}",
        f"Synthesized:    {'YES' if is_synth else 'NO (ingested via load-house-view)'}",
        f"Method:         {skill}",
        f"Effective:      {metadata.get('effective_date')} through {metadata.get('valid_through') or '(auto-expire)'}",
        f"Calibration:    {metadata.get('calibration_status')}",
        f"view_id:        {metadata.get('view_id')}",
        f"version_id:     {metadata.get('version_id')}",
    ]
    return "\n".join(lines)


__all__ = [
    "SKILL_NAME",
    "SKILL_VERSION",
    "MakerOptions",
    "MakerOrchestrator",
    "MakerResult",
    "MCPResponses",
    "MCPRunner",
    "MARKET_TO_SCHEMA_KEY",
    "HARDCODED_COVERAGE",
    "render_status",
]
