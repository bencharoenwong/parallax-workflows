"""One measured run -> one RunRecord.

Extends ``transcript.py``, which extracts prose and tool calls but discards the
stream's ``result`` event -- where every timing and cost metric lives.

Two rules this module exists to enforce:

1. **Two meters, never merged.** ``anthropic_cost_usd`` is CG's bill.
   ``parallax_tokens`` is the client's, and is DERIVED from counted calls, not
   metered. Reporting the first as "cost per artifact" understates the buyer's
   invoice by roughly an order of magnitude.

2. **Nothing is silently dropped.** A run that failed on infrastructure is
   classified, retained, and excluded from aggregation -- never averaged in and
   never deleted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from transcript import ToolCall, parse_stream_json
import token_model

# Run outcome classes. Only `ok` and `degraded` are aggregatable; `degraded`
# is reported as its own category and never pooled with `ok`.
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

    # --- meter 2: Parallax (the client's bill), DERIVED not metered ---
    parallax_tokens: int = 0
    parallax_cost_usd: float = 0.0
    unknown_endpoints: list[str] = field(default_factory=list)

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
        content = (event.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result" \
                    and block.get("is_error"):
                errors += 1
    return errors


def _detect_infra_failure(raw: str, result: dict | None) -> str | None:
    """Infrastructure failed, as distinct from the skill performing badly.

    Mirrors ``grade_corpus.detect_infra_failure``; kept here so a RunRecord can
    be built without importing the grading layer.
    """
    if not raw.strip():
        return "empty stream"
    if result is None:
        return "no result event"
    if result.get("api_error_status"):
        return f"api error {result['api_error_status']}"
    if result.get("subtype") not in (None, "success"):
        return f"result subtype {result['subtype']}"
    lowered = raw.lower()
    if "no mcp servers configured" in lowered or "mcp server" in lowered and "failed to connect" in lowered:
        return "mcp server unavailable"
    if '"status":401' in raw or "401 unauthorized" in lowered:
        return "auth failure (401)"
    return None


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

    reason = _detect_infra_failure(raw, result)
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
    counts: dict[str, int] = {}
    parallax_calls = []
    for call in calls:
        name = token_model.bare(call.name)
        if name in token_model.FLAT_COST or name in token_model.PER_HOLDING_COST:
            counts[name] = counts.get(name, 0) + 1
            parallax_calls.append(call)
    rec.tool_calls_parallax = dict(sorted(counts.items()))

    est = token_model.estimate(calls)
    rec.parallax_tokens = est.tokens
    rec.parallax_cost_usd = round(est.usd(usd_per_token), 4)
    rec.unknown_endpoints = list(est.unknown_endpoints)

    rec.tool_errors = _count_tool_errors(raw)

    if result:
        rec.elapsed_s = (result.get("duration_ms") or 0) / 1000.0
        rec.api_s = (result.get("duration_api_ms") or 0) / 1000.0
        rec.num_turns = result.get("num_turns") or 0
        rec.anthropic_cost_usd = float(result.get("total_cost_usd") or 0.0)
        usage = result.get("usage") or {}
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

    return rec


def from_path(path: str | Path, **kwargs) -> RunRecord:
    p = Path(path)
    kwargs.setdefault("run_id", p.stem)
    return from_stream_json(p.read_text(encoding="utf-8", errors="replace"), **kwargs)
