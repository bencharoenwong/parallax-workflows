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


AS_OF = "2026-10-19"


def _dated(moves):
    """Give legacy arithmetic fixtures an explicit, fixed recent session."""
    return {s: SymbolMove(s, m, True, ("2026-10-15", "2026-10-16"))
            if isinstance(m, (int, float)) else m for s, m in moves.items()}


def _scan(moves, symbols):
    return scan_integrity(_dated(moves), symbols, as_of=AS_OF)


def _render(book, moves, threshold, min_impact):
    return render_no_calls_or_degraded(book, _dated(moves), threshold, min_impact, as_of=AS_OF)


def test_overnight_move_two_closes():
    assert overnight_move([100.0, 93.0]) == pytest.approx(-7.0)


def test_overnight_move_insufficient_data_raises():
    with pytest.raises(ValueError):
        overnight_move([100.0])


@pytest.mark.parametrize("closes", [[float("nan"), 100.0], [100.0, float("inf")]])
def test_overnight_move_rejects_nonfinite_closes(closes):
    with pytest.raises(ValueError, match="finite"):
        overnight_move(closes)


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
    out = _render(book, {"AAPL.O": 4.9}, 5.0, 0.5)
    assert "No calls indicated" in out


def test_no_calls_when_movers_exist_but_no_client_clears_min_impact():
    book = _book([_client("A", [("AAPL.O", 0.01), ("MSFT.O", 0.99)])])
    out = _render(book, {"AAPL.O": 6.0, "MSFT.O": 0.0}, 5.0, 0.5)
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


def test_invalid_asset_class_is_rejected():
    raw = {"schema_version": 1, "clients": [{"client_name": "A", "holdings": [{"symbol": "AAPL.O", "weight": 1, "asset_class": "stock"}]}]}
    with pytest.raises(ValueError, match="asset_class must be exactly"):
        validate_book(raw)


def test_cross_client_asset_class_conflict_is_rejected():
    raw = {"schema_version": 1, "clients": [{"client_name": "A", "holdings": [{"symbol": "SPY", "weight": 1, "asset_class": "etf"}]}, {"client_name": "B", "holdings": [{"symbol": "SPY", "weight": 1, "asset_class": "equity"}]}]}
    with pytest.raises(ValueError, match="conflicting asset_class values"):
        validate_book(raw)


def test_invalid_book_thresholds_warn_and_use_built_in_defaults():
    raw = {
        "schema_version": 1,
        "default_threshold_pct": float("nan"),
        "default_min_impact_pp": -0.1,
        "clients": [
            {
                "client_name": "A",
                "holdings": [{"symbol": "AAPL.O", "weight": 1}],
            }
        ],
    }
    book, warnings = validate_book(raw)
    assert book.default_threshold_pct == 5.0
    assert book.default_min_impact_pp == 0.5
    assert {warning.code for warning in warnings} == {
        "invalid_default_threshold_pct",
        "invalid_default_min_impact_pp",
    }


def test_inline_input_fully_overrides_saved_book():
    saved, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    resolved = resolve_input([{"client_name": "Inline", "portfolio": [{"symbol": "TSLA.O", "weight": 1.0}]}], saved)
    assert [c.client_name for c in resolved.clients] == ["Inline"]
    assert "Northgate" not in [c.client_name for c in resolved.clients]


def test_inline_warnings_are_surfaced():
    saved, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    resolved = resolve_input(
        [{"client_name": "Inline", "portfolio": [{"symbol": "TSLA.O", "weight": 0.12}]}],
        saved,
    )
    assert any(warning.code == "weights_off" for warning in resolved.validation_warnings)
    out = _render(resolved, {"TSLA.O": 1.0}, 5.0, 0.5)
    assert "Validation Warnings" in out
    assert "renormalised" in out


def test_subset_flag_filters_saved_book_without_merging():
    raw = {"schema_version": 1, "clients": [{"client_name": "A", "client_ref": "A1", "holdings": [{"symbol": "AAPL.O", "weight": 1}]}, {"client_name": "B", "client_ref": "B1", "holdings": [{"symbol": "MSFT.O", "weight": 1}]}]}
    book, _ = validate_book(raw)
    resolved = resolve_input(None, book, ["B1"])
    assert [c.client_name for c in resolved.clients] == ["B"]


def test_subset_unmatched_name_is_reported_not_silently_dropped():
    book, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    resolved = resolve_input(None, book, ["Northgate", "Missing"])
    assert resolved.unmatched_subset == ("Missing",)


def test_subset_all_unmatched_refuses_and_names_selectors():
    book, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    with pytest.raises(ValueError, match="subset matched no clients: Missing, Unknown"):
        resolve_input(None, book, ["Missing", "Unknown"])


def test_subset_drops_excluded_client_warnings():
    raw = {
        "schema_version": 1,
        "default_threshold_pct": -1,
        "clients": [
            {
                "client_name": "Client A",
                "client_ref": "A1",
                "holdings": [{"symbol": "AAPL.O", "weight": 0.5}],
            },
            {
                "client_name": "Client B",
                "client_ref": "B1",
                "holdings": [{"symbol": "MSFT.O", "weight": 0.5}],
            },
        ],
    }
    book, _ = validate_book(raw)
    resolved = resolve_input(None, book, ["A1"])
    assert any(warning.client_name is None for warning in resolved.validation_warnings)
    assert any(
        warning.client_name == "Client A"
        for warning in resolved.validation_warnings
    )
    assert all(
        warning.client_name in {None, "Client A"}
        for warning in resolved.validation_warnings
    )
    assert all("Client B" not in warning.message for warning in resolved.validation_warnings)


def test_redacted_refusal_emits_no_selector_names():
    book, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    selectors = ["Private Client", "PRIVATE-REF"]
    with pytest.raises(ValueError) as exc_info:
        resolve_input(None, book, selectors, redact_names=True)
    output = str(exc_info.value)
    assert output == "**Scan refused — 2 selector(s) matched no client.**"
    assert all(selector not in output for selector in selectors)


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
    threshold = auto_raise_threshold(moves, threshold=5.0, cap=40)
    assert threshold == 61.0
    assert len(triggered_symbols(moves, threshold)) <= 40


def test_auto_raise_does_not_fire_on_quiet_scan():
    moves = {f"S{i:03d}.O": 1.0 for i in range(60)}
    moves.update({"S000.O": 6.0, "S001.O": -7.0})
    assert auto_raise_threshold(moves, threshold=5.0, cap=40) is None


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


def test_redact_names_removes_client_refs_and_unmatched_selectors():
    book, _ = validate_book(load_desk_book(FIXTURES / "book_single_client.yaml"))
    resolved = resolve_input(
        None,
        book,
        ["Northgate", "Private Selector"],
        redact_names=True,
    )
    assert resolved.unmatched_subset == ()
    assert resolved.unmatched_subset_count == 1
    redacted, _ = redact_names(resolved)
    assert redacted.clients[0].client_ref is None
    assert redacted.unmatched_subset == ()
    assert redacted.unmatched_subset_count == 1


def test_redact_names_also_redacts_validation_warnings():
    raw = {
        "schema_version": 1,
        "clients": [
            {
                "client_name": "Example Client",
                "holdings": [{"symbol": "AAPL.O", "weight": 0.2}],
            }
        ],
    }
    book, _ = validate_book(raw)
    redacted, _ = redact_names(book)
    warning = redacted.validation_warnings[0]
    assert warning.client_name == "Client 1"
    assert "Example Client" not in warning.message


def test_scan_integrity_below_threshold_blocks_no_calls_path():
    integrity = _scan({"AAPL.O": 1.0, "MSFT.O": SymbolMove("MSFT.O", None, False)}, ["AAPL.O", "MSFT.O"])
    assert integrity["status"] == "SCAN DEGRADED"


def test_all_nan_scan_is_degraded_not_ok():
    for move in [float("nan"), SymbolMove("AAPL.O", float("nan"))]:
        integrity = _scan({"AAPL.O": move}, ["AAPL.O"])
        assert integrity["status"] == "SCAN DEGRADED"
        assert integrity["coverage"] == 0.0


def test_scan_integrity_at_threshold_allows_render():
    integrity = _scan({"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": SymbolMove("E", None, False)}, ["A", "B", "C", "D", "E"])
    assert integrity["coverage"] == pytest.approx(0.80)
    assert integrity["status"] == "ok"


def test_empty_union_is_not_no_calls():
    out = _render(_book([]), {}, 5.0, 0.5)
    assert "Scan refused" in out
    assert "No calls indicated" not in out


def test_scan_integrity_precedes_empty_mover_branch():
    book = _book([_client("A", [("AAPL.O", 0.5), ("MSFT.O", 0.5)])])
    out = _render(book, {"AAPL.O": 1.0, "MSFT.O": SymbolMove("MSFT.O", None, False)}, 5.0, 0.5)
    assert "Scan degraded" in out
    assert "No calls indicated" not in out


def test_symbol_with_one_close_is_named_not_silently_dropped():
    integrity = _scan({"AAPL.O": SymbolMove("AAPL.O", None, False)}, ["AAPL.O"])
    assert integrity["unpriced_symbols"] == ("AAPL.O",)


def test_scan_concurrency_is_a_named_constant():
    assert isinstance(SCAN_CONCURRENCY, int)
    assert SCAN_CONCURRENCY in {8, 24}


@pytest.mark.parametrize("closes", [[0, 100], [100, 0], [-100, -110], [100, -10]])
def test_nonpositive_equity_etf_closes_are_invalid(closes):
    with pytest.raises(ValueError, match="positive"):
        overnight_move(closes)


@pytest.mark.parametrize("dates", [None, ("2020-01-01", "2020-01-02"),
    ("2026-10-16", "2026-10-15"), ("2026-10-16", "2026-10-16"),
    ("2026-10-01", "2026-10-16"), ("2026-10-19", "2026-10-20"),
    ("invalid", "2026-10-16")])
def test_unusable_sessions_cannot_count_as_priced_or_trigger_calls(dates):
    moves = {"AAA.X": SymbolMove("AAA.X", 20.0, True, dates)}
    result = scan_integrity(moves, ["AAA.X"], as_of=AS_OF)
    assert result["coverage"] == 0
    assert result["status"] == "SCAN DEGRADED"
    out = render_no_calls_or_degraded(_book([_client("A", [("AAA.X", 1)])]), moves, 5, .5, as_of=AS_OF)
    assert "Scan degraded" in out
    assert "No calls indicated" not in out


def test_undated_numeric_moves_are_not_current_scan_evidence():
    assert scan_integrity({"AAA.X": 8}, ["AAA.X"], as_of=AS_OF)["coverage"] == 0


def test_recent_mixed_market_sessions_are_disclosed_separately():
    moves = {"AAA.X": SymbolMove("AAA.X", 8, True, ("2026-10-15", "2026-10-16")),
             "BBB.X": SymbolMove("BBB.X", 6, True, ("2026-10-14", "2026-10-15"))}
    result = scan_integrity(moves, moves, as_of=AS_OF)
    assert result["status"] == "ok"
    assert result["session_basis"] == "mixed_latest_sessions"
    assert result["session_intervals"]["BBB.X"] == ("2026-10-14", "2026-10-15")


def test_timezone_aware_as_of_uses_utc_and_default_is_current_utc():
    from desk_call_list_logic import validate_price_moves
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    dates = ((now.date()-timedelta(days=1)).isoformat(), now.date().isoformat())
    moves = {"AAA.X": SymbolMove("AAA.X", 1, True, dates)}
    assert validate_price_moves(moves)[0] == moves
    assert validate_price_moves(moves, as_of=now)[0] == moves
    with pytest.raises(ValueError, match="timezone"):
        validate_price_moves(moves, as_of=datetime(2026, 10, 19))


def test_unmatched_price_identity_is_not_current_evidence():
    moves = {"AAA.X": SymbolMove("BBB.X", 9, True, ("2026-10-15", "2026-10-16"))}
    assert scan_integrity(moves, moves, as_of=AS_OF)["coverage"] == 0


def test_impossible_equity_price_move_cannot_count_as_priced():
    moves = {"AAA.X": SymbolMove("AAA.X", -100.1, True, ("2026-10-15", "2026-10-16"))}
    assert scan_integrity(moves, moves, as_of=AS_OF)["coverage"] == 0


def test_quiet_mixed_sessions_do_not_hide_date_basis():
    moves = {"AAA.X": SymbolMove("AAA.X", 1, True, ("2026-10-15", "2026-10-16")),
             "BBB.X": SymbolMove("BBB.X", 1, True, ("2026-10-14", "2026-10-15"))}
    out = render_no_calls_or_degraded(_book([_client("A", [("AAA.X", .5), ("BBB.X", .5)])]), moves, 5, .5, as_of=AS_OF)
    assert "No calls indicated" in out
    assert "mixed_latest_sessions" in out
    assert "2026-10-14 to 2026-10-15" in out


@pytest.mark.parametrize("value", ["bad response", {}, True])
def test_malformed_move_degrades_instead_of_crashing(value):
    moves = {"AAA.X": SymbolMove("AAA.X", value, True, ("2026-10-15", "2026-10-16"))}
    assert scan_integrity(moves, moves, as_of=AS_OF)["coverage"] == 0


@pytest.mark.parametrize("closes", [[True, 100], [100, False], ["100", 110], [100, "110"], [{}, 100]])
def test_overnight_prices_reject_boolean_and_coerced_text_before_conversion(closes):
    with pytest.raises(ValueError, match="numeric"):
        overnight_move(closes)
