from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

_SKILL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_SKILL_DIR))

from desk_call_list_logic import (  # noqa: E402
    SCAN_CONCURRENCY,
    ClientBook,
    ClientImpact,
    DeskBook,
    Holding,
    SymbolMove,
    auto_raise_threshold,
    book_age_days,
    bound_sections,
    client_metrics,
    load_desk_book,
    overnight_move,
    rank_clients,
    redact_names,
    render_no_calls_or_degraded,
    resolve_input,
    scan_integrity,
    staleness_tier,
    triggered_symbols,
    union_symbols,
    validate_book,
    verdict_sensitivity,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _client(name: str, holdings: list[tuple[str, float]]) -> ClientBook:
    return ClientBook(name, None, tuple(Holding(s, w) for s, w in holdings), sum(w for _, w in holdings))


def _book(clients: list[ClientBook]) -> DeskBook:
    return DeskBook("Desk", "2026-07-19T00:00:00Z", None, None, tuple(clients))


def test_overnight_move_two_closes():
    assert overnight_move([100.0, 93.0]) == pytest.approx(-7.0)


def test_overnight_move_insufficient_data_raises():
    with pytest.raises(ValueError):
        overnight_move([100.0])


def test_threshold_boundary_is_strictly_greater():
    assert triggered_symbols({"AAPL.O": 5.00, "MSFT.O": 5.01}, 5.0) == ("MSFT.O",)


def test_severity_is_direction_agnostic():
    impact = client_metrics(_client("Offset", [("UP.O", 0.5), ("DOWN.O", 0.5)]), {"UP.O": 6.0, "DOWN.O": -6.0}, ("UP.O", "DOWN.O"))
    assert impact.severity_pp > 0
    assert impact.net_impact_pp == pytest.approx(0.0)


def test_net_impact_signed_arithmetic():
    impact = client_metrics(_client("Worked", [("NVDA.O", 0.12), ("ABC.N", 0.05)]), {"NVDA.O": -7.2, "ABC.N": 6.1}, ("NVDA.O", "ABC.N"))
    assert impact.triggered_exposure == pytest.approx(0.17)
    assert impact.net_impact_pp == pytest.approx(-0.559, abs=0.001)
    assert impact.severity_pp == pytest.approx(1.169, abs=0.001)


def test_rank_order_severity_then_abs_net_then_max_single_then_name():
    impacts = [
        ClientImpact("Delta", 0, 1.0, 2.0, "A", 6, 1.0, 1.0),
        ClientImpact("Bravo", 0, 2.0, 2.0, "B", 6, 0.9, 1.0),
        ClientImpact("Alpha", 0, 1.0, 2.0, "C", 6, 1.0, 1.0),
        ClientImpact("Echo", 0, 1.0, 3.0, "D", 6, 1.0, 1.0),
    ]
    assert [i.client_name for i in rank_clients(impacts, 0.5)] == ["Echo", "Bravo", "Alpha", "Delta"]


def test_min_impact_filters_small_positions():
    impact = client_metrics(_client("Tiny", [("AAPL.O", 0.01), ("CASH", 0.99)]), {"AAPL.O": 6.0, "CASH": 0.0}, ("AAPL.O",))
    assert impact.severity_pp == pytest.approx(0.06)
    assert rank_clients([impact], 0.5) == ()


def test_bounding_caps_detail_sections_at_default_eight():
    ranked = [ClientImpact(f"C{i:02d}", 0, 1, 1, "A", 6, 1, 1) for i in range(10)]
    bounded = bound_sections(ranked)
    assert len(bounded["detail"]) == 8
    assert len(bounded["summary"]) == 2


def test_bounding_groups_by_symbol_above_twenty_five_clients():
    ranked = [ClientImpact(f"C{i:02d}", 0, 1, 1, "AAPL.O" if i % 2 else "MSFT.O", 6, 1, 1) for i in range(26)]
    grouped = bound_sections(ranked)["grouped_by_symbol"]
    assert grouped is not None
    assert set(grouped) == {"AAPL.O", "MSFT.O"}


def test_no_calls_when_no_symbol_crosses_threshold():
    book = _book([_client("A", [("AAPL.O", 1.0)])])
    out = render_no_calls_or_degraded(book, {"AAPL.O": 4.9}, 5.0, 0.5)
    assert "No calls indicated" in out


def test_no_calls_when_movers_exist_but_no_client_clears_min_impact():
    book = _book([_client("A", [("AAPL.O", 0.01), ("MSFT.O", 0.99)])])
    out = render_no_calls_or_degraded(book, {"AAPL.O": 6.0, "MSFT.O": 0.0}, 5.0, 0.5)
    assert "No calls indicated" in out


def test_book_weights_renormalised_and_flagged():
    raw = load_desk_book(FIXTURES / "book_weights_off.yaml")
    book, warnings = validate_book(raw)
    assert sum(h.weight for h in book.clients[0].holdings) == pytest.approx(1.0)
    assert any(w.code == "weights_off" for w in warnings)


def test_duplicate_symbol_within_client_summed_and_flagged():
    raw = {"schema_version": 1, "clients": [{"client_name": "A", "holdings": [{"symbol": "aapl.o", "weight": 0.2}, {"symbol": "AAPL.O", "weight": 0.3}, {"symbol": "MSFT.O", "weight": 0.5}]}]}
    book, warnings = validate_book(raw)
    assert len(book.clients[0].holdings) == 2
    assert any(h.symbol == "AAPL.O" and h.weight == pytest.approx(0.5) for h in book.clients[0].holdings)
    assert any(w.code == "duplicate_symbol" for w in warnings)


def test_duplicate_client_name_suffixed_and_flagged():
    raw = {"schema_version": 1, "clients": [{"client_name": "A", "holdings": [{"symbol": "AAPL.O", "weight": 1}]}, {"client_name": "A", "holdings": [{"symbol": "MSFT.O", "weight": 1}]}]}
    book, warnings = validate_book(raw)
    assert [c.client_name for c in book.clients] == ["A", "A #2"]
    assert any(w.code == "duplicate_client_name" for w in warnings)


def test_inline_input_fully_overrides_saved_book():
    saved, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    resolved = resolve_input([{"client_name": "Inline", "portfolio": [{"symbol": "TSLA.O", "weight": 1.0}]}], saved)
    assert [c.client_name for c in resolved.clients] == ["Inline"]
    assert "Northgate" not in [c.client_name for c in resolved.clients]


def test_subset_flag_filters_saved_book_without_merging():
    raw = {"schema_version": 1, "clients": [{"client_name": "A", "client_ref": "A1", "holdings": [{"symbol": "AAPL.O", "weight": 1}]}, {"client_name": "B", "client_ref": "B1", "holdings": [{"symbol": "MSFT.O", "weight": 1}]}]}
    book, _ = validate_book(raw)
    resolved = resolve_input(None, book, ["B1"])
    assert [c.client_name for c in resolved.clients] == ["B"]


def test_subset_unmatched_name_is_reported_not_silently_dropped():
    book, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    resolved = resolve_input(None, book, ["Missing"])
    assert resolved.unmatched_subset == ("Missing",)


def test_staleness_tiers_at_30_31_90_91_and_missing():
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    assert staleness_tier(book_age_days("2026-06-20T00:00:00Z", now)) == "fresh"
    assert staleness_tier(book_age_days("2026-06-19T00:00:00Z", now)) == "warn"
    assert staleness_tier(book_age_days("2026-04-21T00:00:00Z", now)) == "warn"
    assert staleness_tier(book_age_days("2026-04-20T00:00:00Z", now)) == "stale"
    assert staleness_tier(book_age_days(None, now)) == "unknown"


def test_union_symbols_deduped_across_overlapping_books():
    book, _ = validate_book(load_desk_book(FIXTURES / "book_fresh_overlapping.yaml"))
    assert len(union_symbols(book)) == 36


def test_auto_raise_threshold_caps_movers_at_forty():
    moves = {f"S{i:03d}.O": 100.0 - i for i in range(60)}
    threshold = auto_raise_threshold(moves, cap=40)
    assert threshold == 61.0
    assert len(triggered_symbols(moves, threshold)) <= 40


def test_missing_price_reduces_coverage_and_flags_but_does_not_drop_client():
    impact = client_metrics(_client("A", [("AAPL.O", 0.5), ("MSFT.O", 0.5)]), {"AAPL.O": 6.0, "MSFT.O": SymbolMove("MSFT.O", None, False)}, ("AAPL.O",))
    assert impact.coverage == pytest.approx(0.5)
    assert impact.unpriced_symbols == ("MSFT.O",)
    assert impact.client_name == "A"


def test_schema_version_mismatch_refuses_to_run():
    with pytest.raises(ValueError, match="schema_version"):
        validate_book(load_desk_book(FIXTURES / "book_malformed.yaml"))


def test_verdict_sensitivity_uses_no_forbidden_verbs():
    impacts = [ClientImpact("A", 0, 0.1, 0.49, "AAPL.O", 4.9, 0.49, 1)]
    text = " ".join(verdict_sensitivity({"AAPL.O": 4.9}, 5.0, impacts, 0.5)).lower()
    for forbidden in ["buy", "sell", "trim", "should", "recommend", "consider adding"]:
        assert forbidden not in text


def test_redact_names_is_stable_across_runs():
    book, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    redacted1, mapping1 = redact_names(book)
    redacted2, mapping2 = redact_names(book)
    assert mapping1 == mapping2
    assert redacted1.clients[0].client_name == redacted2.clients[0].client_name == "Client 1"


def test_scan_integrity_below_threshold_blocks_no_calls_path():
    integrity = scan_integrity({"AAPL.O": 1.0, "MSFT.O": SymbolMove("MSFT.O", None, False)}, ["AAPL.O", "MSFT.O"])
    assert integrity["status"] == "SCAN DEGRADED"


def test_scan_integrity_at_threshold_allows_render():
    integrity = scan_integrity({"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": SymbolMove("E", None, False)}, ["A", "B", "C", "D", "E"])
    assert integrity["coverage"] == pytest.approx(0.80)
    assert integrity["status"] == "ok"


def test_scan_integrity_precedes_empty_mover_branch():
    book = _book([_client("A", [("AAPL.O", 0.5), ("MSFT.O", 0.5)])])
    out = render_no_calls_or_degraded(book, {"AAPL.O": 1.0, "MSFT.O": SymbolMove("MSFT.O", None, False)}, 5.0, 0.5)
    assert "Scan degraded" in out
    assert "No calls indicated" not in out


def test_symbol_with_one_close_is_named_not_silently_dropped():
    integrity = scan_integrity({"AAPL.O": SymbolMove("AAPL.O", None, False)}, ["AAPL.O"])
    assert integrity["unpriced_symbols"] == ("AAPL.O",)


def test_scan_concurrency_is_a_named_constant():
    assert isinstance(SCAN_CONCURRENCY, int)
    assert SCAN_CONCURRENCY in {8, 24}
