"""Pure logic for /parallax-desk-call-list.

No MCP imports or calls live here. The skill layer gathers price/enrichment data;
this module validates desk books and ranks clients from plain Python data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

SCAN_CONCURRENCY = 24


@dataclass(frozen=True)
class Holding:
    symbol: str
    weight: float
    asset_class: str | None = None


@dataclass(frozen=True)
class ClientBook:
    client_name: str
    client_ref: str | None
    holdings: tuple[Holding, ...]
    original_weight_sum: float


@dataclass(frozen=True)
class DeskBook:
    desk_name: str | None
    updated_at: str | None
    default_threshold_pct: float | None
    default_min_impact_pp: float | None
    clients: tuple[ClientBook, ...]
    source: str = "saved"
    unmatched_subset: tuple[str, ...] = ()


@dataclass(frozen=True)
class BookWarning:
    code: str
    message: str
    client_name: str | None = None
    symbol: str | None = None


@dataclass(frozen=True)
class SymbolMove:
    symbol: str
    move_pct: float | None
    priced: bool = True
    close_dates: tuple[str, str] | None = None


@dataclass(frozen=True)
class ClientImpact:
    client_name: str
    triggered_exposure: float
    net_impact_pp: float
    severity_pp: float
    top_driver: str | None
    top_driver_move_pct: float | None
    top_driver_contribution_pp: float
    coverage: float
    unpriced_symbols: tuple[str, ...] = ()


def load_desk_book(path: str | Path) -> dict[str, Any]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError("desk book must be a YAML mapping")
    return raw


def validate_book(raw: dict[str, Any]) -> tuple[DeskBook, list[BookWarning]]:
    if raw.get("schema_version") != 1:
        raise ValueError("schema_version must be present and equal to 1")

    clients_raw = raw.get("clients")
    if not isinstance(clients_raw, list) or not clients_raw:
        raise ValueError("desk book requires at least one client")

    warnings: list[BookWarning] = []
    seen_names: dict[str, int] = {}
    clients: list[ClientBook] = []
    for row in clients_raw:
        if not isinstance(row, dict):
            raise ValueError("each client must be a mapping")
        base_name = str(row.get("client_name", "")).strip()
        if not base_name:
            raise ValueError("each client requires client_name")
        seen_names[base_name] = seen_names.get(base_name, 0) + 1
        name = base_name if seen_names[base_name] == 1 else f"{base_name} #{seen_names[base_name]}"
        if name != base_name:
            warnings.append(BookWarning("duplicate_client_name", f"duplicate client name suffixed to {name}", name))

        holdings_raw = row.get("holdings", row.get("portfolio"))
        if not isinstance(holdings_raw, list) or not holdings_raw:
            raise ValueError(f"{name} requires at least one holding")

        by_symbol: dict[str, Holding] = {}
        for holding in holdings_raw:
            if not isinstance(holding, dict):
                raise ValueError(f"{name} holding must be a mapping")
            symbol = _normalise_symbol(holding.get("symbol"))
            weight = _numeric_weight(holding.get("weight"), name, symbol)
            asset_class = holding.get("asset_class")
            if asset_class is not None:
                asset_class = str(asset_class).strip().lower()
            if symbol in by_symbol:
                prev = by_symbol[symbol]
                by_symbol[symbol] = replace(prev, weight=prev.weight + weight)
                warnings.append(BookWarning("duplicate_symbol", f"{name}: duplicate {symbol} summed", name, symbol))
            else:
                by_symbol[symbol] = Holding(symbol, weight, asset_class)

        total = sum(h.weight for h in by_symbol.values())
        if total <= 0:
            raise ValueError(f"{name} has no positive holding weights")
        if not 0.95 <= total <= 1.05:
            warnings.append(BookWarning("weights_off", f"{name}: weights summed to {total:.3f}, renormalised - verify book", name))
        holdings = tuple(
            Holding(h.symbol, h.weight / total, h.asset_class)
            for h in by_symbol.values()
        )
        clients.append(ClientBook(name, _optional_str(row.get("client_ref")), holdings, total))

    return (
        DeskBook(
            desk_name=_optional_str(raw.get("desk_name")),
            updated_at=_optional_str(raw.get("updated_at")),
            default_threshold_pct=_optional_float(raw.get("default_threshold_pct")),
            default_min_impact_pp=_optional_float(raw.get("default_min_impact_pp")),
            clients=tuple(clients),
        ),
        warnings,
    )


def book_age_days(updated_at: str | None, now: datetime) -> int | None:
    if not updated_at:
        return None
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0, (now.astimezone(timezone.utc) - dt.astimezone(timezone.utc)).days)


def staleness_tier(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age <= 30:
        return "fresh"
    if age <= 90:
        return "warn"
    return "stale"


def resolve_input(inline: list[dict[str, Any]] | None, book: DeskBook, subset: Iterable[str] | None = None) -> DeskBook:
    if inline is not None:
        inline_raw = {"schema_version": 1, "clients": [_inline_client(c) for c in inline]}
        resolved, _warnings = validate_book(inline_raw)
        return replace(resolved, source="inline")

    if not subset:
        return book

    wanted = tuple(str(s).strip() for s in subset if str(s).strip())
    wanted_fold = {s.casefold() for s in wanted}
    clients = tuple(
        c for c in book.clients
        if c.client_name.casefold() in wanted_fold or (c.client_ref or "").casefold() in wanted_fold
    )
    matched = {c.client_name.casefold() for c in clients} | {(c.client_ref or "").casefold() for c in clients}
    unmatched = tuple(s for s in wanted if s.casefold() not in matched)
    return replace(book, clients=clients, unmatched_subset=unmatched)


def union_symbols(book: DeskBook) -> tuple[str, ...]:
    return tuple(sorted({h.symbol for c in book.clients for h in c.holdings}))


def overnight_move(closes: list[float] | tuple[float, ...]) -> float:
    if len(closes) < 2:
        raise ValueError("at least two closes are required")
    previous, latest = float(closes[-2]), float(closes[-1])
    if previous == 0:
        raise ValueError("previous close must be non-zero")
    return (latest / previous - 1.0) * 100.0


def triggered_symbols(moves: dict[str, float | SymbolMove], threshold: float) -> tuple[str, ...]:
    return tuple(sorted(
        symbol for symbol, move in moves.items()
        if (value := _move_value(move)) is not None and abs(value) > threshold
    ))


def auto_raise_threshold(moves: dict[str, float | SymbolMove], cap: int = 40) -> float | None:
    magnitudes = sorted((abs(v) for m in moves.values() if (v := _move_value(m)) is not None), reverse=True)
    if len(magnitudes) <= cap:
        return None
    raw = magnitudes[cap - 1]
    return math.ceil(raw * 2.0) / 2.0


def scan_integrity(moves: dict[str, float | SymbolMove], union: Iterable[str]) -> dict[str, Any]:
    symbols = tuple(union)
    priced = tuple(s for s in symbols if _is_priced(moves.get(s)))
    unpriced = tuple(s for s in symbols if s not in priced)
    coverage = len(priced) / len(symbols) if symbols else 1.0
    return {
        "status": "ok" if coverage >= 0.80 else "SCAN DEGRADED",
        "coverage": coverage,
        "priced_count": len(priced),
        "total_count": len(symbols),
        "unpriced_symbols": unpriced,
    }


def client_metrics(client: ClientBook, moves: dict[str, float | SymbolMove], triggered: Iterable[str]) -> ClientImpact:
    triggered_set = set(triggered)
    exposure = net = severity = top_contribution = 0.0
    top_symbol: str | None = None
    top_move: float | None = None
    priced_weight = 0.0
    unpriced: list[str] = []

    for holding in client.holdings:
        move = _move_value(moves.get(holding.symbol))
        if move is None:
            unpriced.append(holding.symbol)
        else:
            priced_weight += holding.weight
        if holding.symbol not in triggered_set or move is None:
            continue
        contribution = holding.weight * abs(move)
        exposure += holding.weight
        net += holding.weight * move
        severity += contribution
        if contribution > top_contribution:
            top_contribution = contribution
            top_symbol = holding.symbol
            top_move = move

    return ClientImpact(client.client_name, exposure, net, severity, top_symbol, top_move, top_contribution, priced_weight, tuple(unpriced))


def rank_clients(impacts: Iterable[ClientImpact], min_impact: float) -> tuple[ClientImpact, ...]:
    eligible = [i for i in impacts if i.severity_pp >= min_impact]
    return tuple(sorted(
        eligible,
        key=lambda i: (-i.severity_pp, -abs(i.net_impact_pp), -i.top_driver_contribution_pp, i.client_name),
    ))


def bound_sections(ranked: list[ClientImpact] | tuple[ClientImpact, ...], detail_cap: int = 8, group_cap: int = 25) -> dict[str, Any]:
    detail = tuple(ranked[:detail_cap])
    summary = tuple(ranked[detail_cap:])
    grouped: dict[str, list[str]] | None = None
    if len(ranked) > group_cap:
        grouped = {}
        for impact in summary:
            grouped.setdefault(impact.top_driver or "UNKNOWN", []).append(impact.client_name)
    return {"detail": detail, "summary": summary, "grouped_by_symbol": grouped}


def verdict_sensitivity(
    moves: dict[str, float | SymbolMove],
    threshold: float,
    impacts: Iterable[ClientImpact],
    min_impact: float,
) -> tuple[str, ...]:
    lines: list[str] = []
    below = [
        (threshold - abs(v), symbol, v)
        for symbol, move in moves.items()
        if (v := _move_value(move)) is not None and abs(v) <= threshold
    ]
    if below:
        dist, symbol, value = min(below, key=lambda x: (x[0], x[1]))
        lines.append(
            f"Symbol nearest the move threshold: {symbol} at {value:+.2f}%, "
            f"{dist:.2f} percentage points below the {threshold:.2f}% trigger."
        )
    under = [
        (min_impact - i.severity_pp, i.client_name, i.severity_pp)
        for i in impacts
        if i.severity_pp < min_impact
    ]
    if under:
        dist, name, severity = min(under, key=lambda x: (x[0], x[1]))
        lines.append(
            f"Client nearest the impact floor: {name} at {severity:.2f} pp, "
            f"{dist:.2f} pp below the {min_impact:.2f} pp floor."
        )
    return tuple(lines)


def redact_names(book: DeskBook) -> tuple[DeskBook, dict[str, str]]:
    mapping = {client.client_name: f"Client {idx}" for idx, client in enumerate(book.clients, start=1)}
    clients = tuple(replace(c, client_name=mapping[c.client_name]) for c in book.clients)
    return replace(book, clients=clients), mapping


def render_no_calls_or_degraded(
    book: DeskBook,
    moves: dict[str, float | SymbolMove],
    threshold: float,
    min_impact: float,
) -> str:
    symbols = union_symbols(book)
    integrity = scan_integrity(moves, symbols)
    if integrity["status"] == "SCAN DEGRADED":
        unpriced = ", ".join(integrity["unpriced_symbols"][:10])
        return (
            f"**Scan degraded — results not reliable.** Priced {integrity['priced_count']} "
            f"of {integrity['total_count']} unique symbols ({integrity['coverage']:.0%}). "
            f"Unpriced: {unpriced}. A call list is not rendered because absence of a trigger "
            "cannot be distinguished from absence of data."
        )
    triggered = triggered_symbols(moves, threshold)
    impacts = [client_metrics(c, moves, triggered) for c in book.clients]
    ranked = rank_clients(impacts, min_impact)
    if not triggered or not ranked:
        largest_symbol, largest_move = _largest_move(moves)
        return (
            f"**No calls indicated.** {len(symbols)} unique symbols scanned across "
            f"{len(book.clients)} client books. Largest move: {largest_symbol} {largest_move:+.1f}% "
            f"(threshold {threshold:.1f}%). No book impact reached the {min_impact:.2f} pp floor."
        )
    return "CALL LIST"


def _normalise_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not symbol:
        raise ValueError("holding requires symbol")
    return symbol


def _numeric_weight(value: Any, client_name: str, symbol: str) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{client_name} {symbol} weight must be numeric") from exc
    if not 0 < weight <= 1:
        raise ValueError(f"{client_name} {symbol} weight must be > 0 and <= 1")
    return weight


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _inline_client(client: dict[str, Any]) -> dict[str, Any]:
    return {
        "client_name": client.get("client_name"),
        "client_ref": client.get("client_ref"),
        "holdings": client.get("portfolio", client.get("holdings")),
    }


def _move_value(move: float | SymbolMove | None) -> float | None:
    if move is None:
        return None
    if isinstance(move, SymbolMove):
        return move.move_pct if move.priced else None
    return float(move)


def _is_priced(move: float | SymbolMove | None) -> bool:
    return _move_value(move) is not None


def _largest_move(moves: dict[str, float | SymbolMove]) -> tuple[str, float]:
    priced = [(symbol, value) for symbol, move in moves.items() if (value := _move_value(move)) is not None]
    if not priced:
        return ("n/a", 0.0)
    return max(priced, key=lambda x: abs(x[1]))
