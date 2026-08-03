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

    # --- meter 2: Parallax (the client's bill), DERIVED not metered ---
    parallax_tokens: int = 0
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
    # Counted over KNOWN_ENDPOINTS, not just the priced tables: a KNOWN_UNPRICED
    # call under a Parallax namespace is definitively Parallax work performed,
    # and ``unpriced_endpoints`` records only its name. Filtering it out here
    # would leave a pair-finder run -- five etf_holdings, three etf_search --
    # reporting zero Parallax calls, with nothing in the record stating how much
    # work it actually did. Cost stays derived from the priced tables alone.
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

    # An ambiguous call is a known endpoint name under an unrecognised MCP
    # namespace: it may be a Parallax connector mounted off-brand, or another
    # server's colliding tool. Either way ``parallax_tokens`` is now of unknown
    # accuracy, so the run must not be pooled into an aggregate that reads as a
    # measured client bill. Unlike KNOWN_UNPRICED this IS resolvable -- naming
    # the namespace in PARALLAX_MCP_ALIASES clears it permanently.
    if rec.ambiguous_endpoints and rec.status == STATUS_OK:
        rec.status = STATUS_DEGRADED
        rec.degraded_paths.append(
            "ambiguous_endpoint:" + ",".join(rec.ambiguous_endpoints)
        )

    # A KNOWN_UNPRICED endpoint is deliberately absent from the table, not a
    # sign the table is stale -- no table edit can clear it, so degrading here
    # would permanently exclude every run of a workflow that calls one
    # (pair-finder) from AGGREGATABLE. It stays STATUS_OK; ``unpriced_endpoints``
    # on the record states what the derived total omits.

    return rec


def from_path(path: str | Path, **kwargs) -> RunRecord:
    p = Path(path)
    kwargs.setdefault("run_id", p.stem)
    return from_stream_json(p.read_text(encoding="utf-8", errors="replace"), **kwargs)
