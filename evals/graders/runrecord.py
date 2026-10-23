"""One captured run -> one RunRecord, preserving model usage separately.

``parallax_tokens`` is a legacy key measured in Parallax credits: an input-only
all-success planning estimate, never an observed account deduction. Conditional
ceilings and assumptions travel with it. Existing serialized records retain their
original values; callers must explicitly parse a trace to create a new estimate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from transcript import ToolCall, parse_stream_json
from infra_failure import detect_infra_failure
import token_model

# Run outcome classes. Only `ok` is aggregatable; `degraded` is retained and
# reported as its own category, never pooled with `ok`.
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_SKILL_ERROR = "skill_error"
STATUS_INFRA_FAILURE = "infra_failure"
STATUS_TIMEOUT = "timeout"

AGGREGATABLE = {STATUS_OK}


@dataclass
class RunRecord:
    run_id: str
    workflow: str = ""
    n_holdings: int = 0
    breadth: str = ""
    replicate: int = 0

    status: str = STATUS_OK
    infra_reason: str | None = None
    degraded_paths: list[str] = field(default_factory=list)

    # --- timing ---
    elapsed_s: float = 0.0
    api_s: float = 0.0
    num_turns: int = 0

    # --- meter 1: Anthropic (CG's bill) ---
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    anthropic_cost_usd: float = 0.0

    # --- Parallax planning estimate: legacy tokens key has credit units ---
    parallax_tokens: float = 0.0
    parallax_credit_upper_bound: float | None = None
    parallax_estimate_basis: str = "unspecified (legacy record)"
    parallax_estimate_assumptions: list[str] = field(default_factory=list)
    parallax_usd_per_credit: float | None = None
    unpriced_inputs: list[str] = field(default_factory=list)
    parallax_cost_usd: float = 0.0
    unknown_endpoints: list[str] = field(default_factory=list)
    unpriced_endpoints: list[str] = field(default_factory=list)
    ambiguous_endpoints: list[str] = field(default_factory=list)

    # --- work performed ---
    tool_calls_total: int = 0
    tool_calls_parallax: dict[str, int] = field(default_factory=dict)
    tool_errors: int = 0

    # --- output ---
    sections_produced: list[str] = field(default_factory=list)
    prose_chars: int = 0

    def aggregatable(self) -> bool:
        return self.status in AGGREGATABLE

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def _find_result_event(raw: str) -> dict | None:
    found = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            found = event
    return found


def _count_tool_errors(raw: str) -> int:
    errors = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        message = event.get("message")
        content = (message if isinstance(message, dict) else {}).get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result" \
                    and block.get("is_error"):
                errors += 1
    return errors


def from_stream_json(
    raw: str,
    run_id: str,
    *,
    workflow: str = "",
    n_holdings: int = 0,
    breadth: str = "",
    replicate: int = 0,
    usd_per_token: float = token_model.USD_PER_TOKEN,
) -> RunRecord:
    result = _find_result_event(raw)
    rec = RunRecord(
        run_id=run_id,
        workflow=workflow,
        n_holdings=n_holdings,
        breadth=breadth,
        replicate=replicate,
    )

    reason = detect_infra_failure(raw, result)
    if reason:
        rec.status = STATUS_INFRA_FAILURE
        rec.infra_reason = reason

    # Tool calls are extractable even from a run with no result event.
    try:
        transcript = parse_stream_json(raw)
        calls: list[ToolCall] = list(transcript.tool_calls)
        rec.prose_chars = len(transcript.final_prose or "")
    except Exception:
        calls = []

    rec.tool_calls_total = len(calls)
    # Count known Parallax work independently of pricing-input completeness.
    counts: dict[str, int] = {}
    for call in calls:
        if not token_model.is_parallax_mcp(call.name):
            continue
        name = token_model.bare(call.name)
        if name in token_model.KNOWN_ENDPOINTS:
            counts[name] = counts.get(name, 0) + 1
    rec.tool_calls_parallax = dict(sorted(counts.items()))

    est = token_model.estimate(calls)
    rec.parallax_tokens = est.tokens
    rec.parallax_estimate_basis = token_model.PRICE_BASIS
    rec.parallax_credit_upper_bound = est.upper_bound_tokens
    rec.parallax_estimate_assumptions = list(est.assumptions)
    rec.parallax_usd_per_credit = usd_per_token
    rec.unpriced_inputs = list(est.unpriced_inputs)
    rec.parallax_cost_usd = round(est.usd(usd_per_token), 4)
    rec.unknown_endpoints = list(est.unknown_endpoints)
    rec.unpriced_endpoints = list(est.unpriced_endpoints)
    rec.ambiguous_endpoints = list(est.ambiguous_endpoints)

    rec.tool_errors = _count_tool_errors(raw)

    if result:
        rec.elapsed_s = (result.get("duration_ms") or 0) / 1000.0
        rec.api_s = (result.get("duration_api_ms") or 0) / 1000.0
        rec.num_turns = result.get("num_turns") or 0
        rec.anthropic_cost_usd = float(result.get("total_cost_usd") or 0.0)
        usage = result.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        rec.tokens_in = usage.get("input_tokens") or 0
        rec.tokens_out = usage.get("output_tokens") or 0
        rec.cache_read = usage.get("cache_read_input_tokens") or 0
        rec.cache_creation = usage.get("cache_creation_input_tokens") or 0
        if result.get("is_error") and rec.status == STATUS_OK:
            rec.status = STATUS_SKILL_ERROR

    # An unknown Parallax-looking endpoint means the price table is stale. That
    # is a hard failure, not a free call.
    if rec.unknown_endpoints and rec.status == STATUS_OK:
        rec.status = STATUS_DEGRADED
        rec.degraded_paths.append(
            "unknown_endpoint:" + ",".join(rec.unknown_endpoints)
        )

    # Unattributed calls cannot form a complete planning aggregate.
    if rec.ambiguous_endpoints and rec.status == STATUS_OK:
        rec.status = STATUS_DEGRADED
        rec.degraded_paths.append(
            "ambiguous_endpoint:" + ",".join(rec.ambiguous_endpoints)
        )

    if rec.unpriced_endpoints:
        if rec.status == STATUS_OK:
            rec.status = STATUS_DEGRADED
        rec.degraded_paths.append("unpriced_input:" + ",".join(rec.unpriced_endpoints))

    return rec


def from_path(path: str | Path, **kwargs) -> RunRecord:
    p = Path(path)
    kwargs.setdefault("run_id", p.stem)
    return from_stream_json(p.read_text(encoding="utf-8", errors="replace"), **kwargs)
