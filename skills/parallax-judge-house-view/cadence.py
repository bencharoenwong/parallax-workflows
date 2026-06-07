"""Cadence triggers for /parallax-judge-house-view.

The judge runs in three modes:

- **on-demand**: explicit `/parallax-judge-house-view` invocation. No
  gating — always runs the full pipeline.
- **auto-on-load**: consumer skills (`portfolio-builder`, `rebalance`,
  `thematic-screen` per v2 plan §7) auto-invoke the judge when the
  active view is older than ``AUTO_ON_LOAD_MIN_AGE_DAYS`` days. The
  judge runs in cached / dry-run mode (no fresh MCP fan-out if the
  cache is within ``AUTO_ON_LOAD_CACHE_TTL_SECONDS``).
- **scheduled**: bank-side cron invokes
  ``/parallax-judge-house-view --json`` against a locally-mounted
  view. No special gating beyond the on-demand path; the trigger only
  records that this was a scheduled run for the audit row.

The actual cache lookup / invocation routing is the orchestrator's
responsibility (``judge.py``). This module provides the predicates so
all three trigger surfaces apply the same thresholds.

Server-side `house_view_judge` MCP tool: DEFERRED until Supabase
managed backend ships (v2 plan §3.2 / BUG-007). When that lands, the
server-side path will reuse the same `should_run_auto_on_load`
predicate against the org's managed view age + a server-cached
recommendation TTL.
"""
from __future__ import annotations

import datetime
from typing import Literal

# Auto-on-load only fires for views older than this many days. Below this
# threshold, the consumer skill skips the judge call entirely (no banner,
# no audit row) — the view is fresh enough that drift is unlikely and the
# 45-60s fan-out latency would dominate the consumer skill's own work.
AUTO_ON_LOAD_MIN_AGE_DAYS = 30

# When auto-on-load fires, the judge prefers a cached recommendation if
# one exists from the last hour. This keeps consumer-skill latency in the
# ~few-second range for repeated invocations (e.g., a fund manager
# reloading the portfolio builder several times in a row).
AUTO_ON_LOAD_CACHE_TTL_SECONDS = 3600

TriggerSource = Literal["on_demand", "auto_on_load", "scheduled"]


def should_run_auto_on_load(view_age_days: int) -> bool:
    """True iff a consumer skill should auto-trigger the judge.

    Args:
        view_age_days: ``floor((now - upload_timestamp) / 86400)``.

    Returns:
        True when the view is at or past the threshold. Consumer skills
        that get True call the judge in ``--cached`` mode and surface a
        banner only when the returned severity == ``drift_material``.
    """
    if view_age_days is None or view_age_days < 0:
        return False
    return view_age_days >= AUTO_ON_LOAD_MIN_AGE_DAYS


def is_cache_fresh(
    cached_at: datetime.datetime | None,
    now: datetime.datetime | None = None,
) -> bool:
    """True iff a previously-cached judge result is still usable.

    Args:
        cached_at: When the cached result was written, or None if no
            cache entry exists.
        now: Override for tests; defaults to ``datetime.now(UTC)``.
    """
    if cached_at is None:
        return False
    now = now or datetime.datetime.now(datetime.timezone.utc)
    age = (now - cached_at).total_seconds()
    return 0 <= age <= AUTO_ON_LOAD_CACHE_TTL_SECONDS


def resolve_trigger(
    *,
    explicit: bool,
    scheduled: bool,
    view_age_days: int | None,
) -> tuple[TriggerSource, bool]:
    """Return ``(trigger, should_run)`` for the orchestrator.

    Order of precedence: explicit > scheduled > auto-on-load.

    Args:
        explicit: True when the caller invoked /parallax-judge-house-view
            directly (CLI surface).
        scheduled: True when the caller is a cron / scheduled runner
            (e.g., bank-side cron with `--json`). Distinct from explicit
            because scheduled runs default to JSON output and never
            interact with AskUserQuestion.
        view_age_days: Used only for auto-on-load gating.

    Returns:
        ``(trigger, should_run)``. ``should_run`` is False only when
        trigger == ``auto_on_load`` and the age threshold is not yet met.
    """
    if explicit:
        return "on_demand", True
    if scheduled:
        return "scheduled", True
    # Auto-on-load via consumer skill.
    return "auto_on_load", should_run_auto_on_load(view_age_days or 0)
