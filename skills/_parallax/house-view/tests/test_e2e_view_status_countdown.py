"""End-to-end tests for the view_status countdown state machine.

Complements ``test_e2e.py``'s Test 13
(``test_e2e_view_status_state_machine_covers_documented_states``), which
exercises the five non-countdown branches (none / malformed /
not_yet_effective / expired / active) but explicitly skips the day-boundary
assertions for ``critical`` and ``warning``.

Consumer skills (e.g., loader.md §2 step 6, auto-on-load-judge-pattern.md)
branch on these states and surface different banner prose to end users. A
silent shift in the day boundary would change what users see without any
test catching it — these tests pin both the day count and the user-facing
banner shape.

Thresholds (canonical, per ``view_status.py`` lines 33-34 and ``loader.md``
§"Soft-warning thresholds"):

  ============= ===============
   N (days)      state
  ============= ===============
   N < 0         expired
   0 ≤ N < 10    critical
   10 ≤ N < 14   warning
   N ≥ 14        active
  ============= ===============

These tests use ``date.today()`` via real-runtime ``compute_status`` (no
``today=`` injection) to validate the path consumer skills actually take.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
SHARED_DIR = REPO / "skills" / "_parallax" / "house-view"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import view_status  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_view(
    tmp_path: Path,
    *,
    view_name: str,
    effective_offset_days: int,
    valid_through_offset_days: int,
    today: date | None = None,
) -> Path:
    """Seed a view.yaml whose dates are offset from a today reference.

    ``today`` is optional. Most tests pass None (capture inside) and only
    assert on state — the midnight-window risk is one-state-shift at the
    boundary, acceptable for state-only assertions. Tests that assert on
    exact ``days_remaining`` integer equality (e.g., the parametric walk
    in Test 3) MUST capture ``today = date.today()`` first and pass it to
    BOTH ``_write_view(today=today)`` AND
    ``view_status.compute_status(view_dir, today=today)`` so a process
    that crosses midnight between the two calls doesn't shift the count.
    """
    if today is None:
        today = date.today()
    effective = today + timedelta(days=effective_offset_days)
    valid_through = today + timedelta(days=valid_through_offset_days)
    view_dir = tmp_path / "active-house-view"
    view_dir.mkdir(parents=True, exist_ok=True)
    (view_dir / "view.yaml").write_text(
        yaml.safe_dump(
            {
                "metadata": {
                    "view_name": view_name,
                    "effective_date": effective.isoformat(),
                    "valid_through": valid_through.isoformat(),
                }
            }
        )
    )
    return view_dir


# ---------------------------------------------------------------------------
# Test 1 — warning boundary (WARNING_DAYS = 14, strict <)
# ---------------------------------------------------------------------------
#
# Per view_status.py:
#   if days_remaining < CRITICAL_DAYS: critical    (CRITICAL_DAYS = 10)
#   if days_remaining < WARNING_DAYS:  warning     (WARNING_DAYS = 14)
#   else:                              active
#
# So the warning band is 10 ≤ N ≤ 13. We verify the upper boundary:
#   - N = 13 → warning  (just inside)
#   - N = 14 → active   (just outside, the first "active" day)
# AND we verify that an N comfortably inside the band is also warning.


def test_e2e_view_status_warning_state_at_documented_threshold(
    tmp_path: Path,
) -> None:
    """warning fires when 10 ≤ days_remaining < 14. Pin the upper boundary
    at day 13 (inside) vs day 14 (outside, → active) so a one-day shift in
    WARNING_DAYS breaks this test.
    """
    # Inside the band — N = 13 (last warning day before active takes over)
    view_dir_inside = _write_view(
        tmp_path / "inside",
        view_name="Warning inside",
        effective_offset_days=-30,
        valid_through_offset_days=13,
    )
    s_inside = view_status.compute_status(view_dir_inside)
    assert s_inside.state == "warning", (
        f"N=13 should be warning (WARNING_DAYS=14, strict <); got "
        f"{s_inside.state!r}"
    )
    assert s_inside.days_remaining == 13
    assert s_inside.tilts_apply is True

    # One day outside the band — N = 14 → active
    view_dir_outside = _write_view(
        tmp_path / "outside",
        view_name="Active just outside warning",
        effective_offset_days=-30,
        valid_through_offset_days=14,
    )
    s_outside = view_status.compute_status(view_dir_outside)
    assert s_outside.state == "active", (
        f"N=14 should be active (WARNING_DAYS=14, strict <); got "
        f"{s_outside.state!r}"
    )
    assert s_outside.days_remaining == 14
    assert s_outside.tilts_apply is True

    # Middle of the warning band — N = 11 (also warning)
    view_dir_mid = _write_view(
        tmp_path / "mid",
        view_name="Warning middle",
        effective_offset_days=-30,
        valid_through_offset_days=11,
    )
    s_mid = view_status.compute_status(view_dir_mid)
    assert s_mid.state == "warning"
    assert s_mid.days_remaining == 11


# ---------------------------------------------------------------------------
# Test 2 — critical boundary (CRITICAL_DAYS = 10, strict <)
# ---------------------------------------------------------------------------
#
# Critical band is 0 ≤ N ≤ 9. We verify the upper boundary:
#   - N = 9  → critical (just inside)
#   - N = 10 → warning  (just outside, first warning day)
# AND verify the lower edge:
#   - N = 0  → critical (last critical day, view expires tomorrow)


def test_e2e_view_status_critical_state_at_documented_threshold(
    tmp_path: Path,
) -> None:
    """critical fires when 0 ≤ days_remaining < 10. Pin the upper boundary
    at day 9 (inside) vs day 10 (outside, → warning) and verify N=0 is the
    last critical day (view valid through today, not yet expired).
    """
    # Inside the band — N = 9 (last critical day before warning takes over)
    view_dir_inside = _write_view(
        tmp_path / "inside",
        view_name="Critical inside",
        effective_offset_days=-30,
        valid_through_offset_days=9,
    )
    s_inside = view_status.compute_status(view_dir_inside)
    assert s_inside.state == "critical", (
        f"N=9 should be critical (CRITICAL_DAYS=10, strict <); got "
        f"{s_inside.state!r}"
    )
    assert s_inside.days_remaining == 9
    # tilts STILL apply in critical state per loader.md §"Soft-warning
    # thresholds" — only expired flips tilts_apply to False.
    assert s_inside.tilts_apply is True

    # One day outside — N = 10 → warning (still warning, not yet active)
    view_dir_outside = _write_view(
        tmp_path / "outside",
        view_name="Warning just outside critical",
        effective_offset_days=-30,
        valid_through_offset_days=10,
    )
    s_outside = view_status.compute_status(view_dir_outside)
    assert s_outside.state == "warning", (
        f"N=10 should be warning (CRITICAL_DAYS=10, strict <); got "
        f"{s_outside.state!r}"
    )
    assert s_outside.days_remaining == 10
    assert s_outside.tilts_apply is True

    # Lower edge — N = 0 (expires today; days_remaining is still 0, not -1)
    view_dir_zero = _write_view(
        tmp_path / "zero",
        view_name="Critical at zero",
        effective_offset_days=-30,
        valid_through_offset_days=0,
    )
    s_zero = view_status.compute_status(view_dir_zero)
    assert s_zero.state == "critical", (
        f"N=0 should be critical (last day before expired); got "
        f"{s_zero.state!r}"
    )
    assert s_zero.days_remaining == 0
    assert s_zero.tilts_apply is True


# ---------------------------------------------------------------------------
# Test 3 — walk the calendar across every documented boundary
# ---------------------------------------------------------------------------
#
# Parametric sweep that catches off-by-one bugs at every threshold AND
# catches the "tier swallows a neighboring day" class of regression where,
# say, warning's < accidentally becomes <=.
#
# Expected mapping (from view_status.py + loader.md):
#   N = -5  → expired
#   N =  0  → critical
#   N =  3  → critical
#   N =  7  → critical
#   N =  9  → critical
#   N = 10  → warning
#   N = 13  → warning
#   N = 14  → active
#   N = 21  → active
#   N = 60  → active
#   N = 365 → active


@pytest.mark.parametrize(
    "days_offset, expected_state",
    [
        (-5, "expired"),
        (0, "critical"),
        (3, "critical"),
        (7, "critical"),
        (9, "critical"),
        (10, "warning"),
        (13, "warning"),
        (14, "active"),
        (21, "active"),
        (60, "active"),
        (365, "active"),
    ],
)
def test_e2e_view_status_state_transitions_walk_the_calendar(
    tmp_path: Path,
    days_offset: int,
    expected_state: str,
) -> None:
    """Walk valid_through from -5 to +365 days. Each (N, state) pair is a
    separate sub-test so failures point at the exact boundary that
    regressed. Catches both off-by-one in a single threshold AND the case
    where a band silently grows/shrinks at the expense of its neighbor.
    """
    # Pin `today` to avoid a midnight-crossing flake on the strict
    # days_remaining == days_offset assertion below. Both _write_view and
    # compute_status must use the SAME today reference.
    today = date.today()
    view_dir = _write_view(
        tmp_path,
        view_name=f"Walk view N={days_offset}",
        # Use a very-old effective_date so the not_yet_effective branch
        # never fires regardless of offset sign.
        effective_offset_days=-365,
        valid_through_offset_days=days_offset,
        today=today,
    )
    status = view_status.compute_status(view_dir, today=today)
    assert status.state == expected_state, (
        f"days_offset={days_offset}: expected state={expected_state!r}, "
        f"got {status.state!r} (days_remaining={status.days_remaining})"
    )
    # days_remaining should match the offset exactly — both are derived
    # from (valid_through - today) with the same arithmetic.
    assert status.days_remaining == days_offset, (
        f"days_offset={days_offset}: expected days_remaining={days_offset}, "
        f"got {status.days_remaining}"
    )


# ---------------------------------------------------------------------------
# Test 4 — banner stays in sync with structured fields
# ---------------------------------------------------------------------------
#
# Banner is the user-facing surface. If the structured days_remaining shifts
# but the banner still hardcodes a stale number (or vice versa) consumer
# skills surface confusing prose. Pin both together.


def test_e2e_view_status_banner_and_days_remaining_consistent_with_state(
    tmp_path: Path,
) -> None:
    """For each non-trivial state (warning, critical, active, expired,
    not_yet_effective) construct a view at a known offset and assert the
    banner contains the integer day count (where applicable) and the
    structured fields match.
    """
    # warning — N = 12 (middle of warning band)
    view_dir = _write_view(
        tmp_path / "warning",
        view_name="Warning banner check",
        effective_offset_days=-30,
        valid_through_offset_days=12,
    )
    s = view_status.compute_status(view_dir)
    assert s.state == "warning"
    assert s.days_remaining == 12
    assert "12 days" in s.banner, (
        f"warning banner should contain '12 days'; got: {s.banner!r}"
    )
    assert "Warning banner check" in s.banner

    # critical — N = 5
    view_dir = _write_view(
        tmp_path / "critical",
        view_name="Critical banner check",
        effective_offset_days=-30,
        valid_through_offset_days=5,
    )
    s = view_status.compute_status(view_dir)
    assert s.state == "critical"
    assert s.days_remaining == 5
    # critical banner uses "5 days" (plural for N != 1)
    assert "5 days" in s.banner, (
        f"critical banner should contain '5 days'; got: {s.banner!r}"
    )
    assert "Critical banner check" in s.banner

    # critical — N = 1 (verify the singular "1 day" path in view_status.py)
    view_dir = _write_view(
        tmp_path / "critical_singular",
        view_name="One day left",
        effective_offset_days=-30,
        valid_through_offset_days=1,
    )
    s = view_status.compute_status(view_dir)
    assert s.state == "critical"
    assert s.days_remaining == 1
    # Banner uses "1 day" (singular) — guard the pluralization branch.
    assert "1 day" in s.banner
    # Make sure we didn't accidentally render "1 days" (plural bug).
    assert "1 days" not in s.banner, (
        f"critical banner pluralization broken for N=1: {s.banner!r}"
    )

    # active — N = 90
    view_dir = _write_view(
        tmp_path / "active",
        view_name="Active banner check",
        effective_offset_days=-30,
        valid_through_offset_days=90,
    )
    s = view_status.compute_status(view_dir)
    assert s.state == "active"
    assert s.days_remaining == 90
    assert "90 days" in s.banner, (
        f"active banner should contain '90 days'; got: {s.banner!r}"
    )
    assert "Active banner check" in s.banner

    # expired — N = -3
    view_dir = _write_view(
        tmp_path / "expired",
        view_name="Expired banner check",
        effective_offset_days=-30,
        valid_through_offset_days=-3,
    )
    s = view_status.compute_status(view_dir)
    assert s.state == "expired"
    assert s.days_remaining == -3
    assert "expired" in s.banner.lower(), (
        f"expired banner should mention 'expired'; got: {s.banner!r}"
    )
    # And the absolute day-count should appear (banner says "expired N day(s) ago")
    assert "3 day" in s.banner

    # not_yet_effective — effective in the future
    view_dir = _write_view(
        tmp_path / "future",
        view_name="Future banner check",
        effective_offset_days=30,
        valid_through_offset_days=120,
    )
    s = view_status.compute_status(view_dir)
    assert s.state == "not_yet_effective"
    assert s.tilts_apply is False
    banner_lower = s.banner.lower()
    assert "effective" in banner_lower, (
        f"not_yet_effective banner should mention 'effective'; got: {s.banner!r}"
    )
    # Future effective date (ISO) should appear so the user knows WHEN.
    future_iso = (date.today() + timedelta(days=30)).isoformat()
    assert future_iso in s.banner, (
        f"not_yet_effective banner should embed the effective date "
        f"{future_iso}; got: {s.banner!r}"
    )
