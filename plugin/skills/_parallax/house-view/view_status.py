"""House view status — operator-agnostic, deterministic helper.

Computes the current state of the active house view (active / warning /
critical / expired / not_yet_effective / malformed / none) and a banner
string that consumer skills surface to the user.

Why this exists separately from `loader.md`:
the date arithmetic and threshold logic must be deterministic across
operator LLMs (Claude / GPT / Gemini). Markdown instructions can drift
or get skipped under context pressure; a one-line shell call to this
module returns the same banner every time.

CLI:
    python -m view_status                       # prints banner
    python -m view_status --json                # prints JSON status
    python -m view_status --exit-code-by-state  # nonzero on expired/malformed
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

DEFAULT_DIR = Path("~/.parallax/active-house-view").expanduser()
CRITICAL_DAYS = 10
WARNING_DAYS = 14


@dataclass(frozen=True)
class ViewStatus:
    state: str
    view_name: str | None
    effective_date: str | None
    valid_through: str | None
    days_remaining: int | None
    banner: str
    suggestion: str | None
    tilts_apply: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("PARALLAX_HOUSE_VIEW_DIR")
    return Path(env).expanduser() if env else DEFAULT_DIR


def _parse_date(s: Any) -> date | None:
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def compute_status(
    view_dir: Path | None = None,
    today: date | None = None,
) -> ViewStatus:
    today = today or date.today()
    view_dir = _resolve_dir(view_dir)
    view_path = view_dir / "view.yaml"

    if not view_path.exists():
        return ViewStatus(
            state="none",
            view_name=None,
            effective_date=None,
            valid_through=None,
            days_remaining=None,
            banner="No active house view. Run `/parallax-load-house-view` to set one.",
            suggestion=None,
            tilts_apply=False,
        )

    try:
        with view_path.open() as f:
            view = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        return ViewStatus(
            state="malformed",
            view_name=None,
            effective_date=None,
            valid_through=None,
            days_remaining=None,
            banner=(
                f"! House view at {view_path} is unreadable ({type(e).__name__}). "
                "Run `/parallax-load-house-view --edit` to repair."
            ),
            suggestion="Repair or re-load.",
            tilts_apply=False,
        )

    meta = view.get("metadata") or {}
    view_name = meta.get("view_name")
    effective = _parse_date(meta.get("effective_date"))
    valid_through = _parse_date(meta.get("valid_through"))
    auto_expire_days = meta.get("auto_expire_days")
    name_disp = view_name or "unnamed"

    if effective is None and valid_through is None:
        return ViewStatus(
            state="malformed",
            view_name=view_name,
            effective_date=None,
            valid_through=None,
            days_remaining=None,
            banner=(
                f"! House view '{name_disp}' is missing both effective_date and valid_through. "
                "Tilts NOT applied. Run `/parallax-load-house-view --edit`."
            ),
            suggestion="Repair window before tilts can apply.",
            tilts_apply=False,
        )

    if valid_through is not None:
        expiry = valid_through
    elif effective is not None and isinstance(auto_expire_days, int) and auto_expire_days > 0:
        expiry = effective + timedelta(days=auto_expire_days)
    else:
        return ViewStatus(
            state="malformed",
            view_name=view_name,
            effective_date=meta.get("effective_date"),
            valid_through=None,
            days_remaining=None,
            banner=(
                f"! House view '{name_disp}' lacks `valid_through` and a positive `auto_expire_days`. "
                "Tilts NOT applied. Run `/parallax-load-house-view --edit`."
            ),
            suggestion="Set valid_through.",
            tilts_apply=False,
        )

    if effective is not None and today < effective:
        return ViewStatus(
            state="not_yet_effective",
            view_name=view_name,
            effective_date=meta.get("effective_date"),
            valid_through=expiry.isoformat(),
            days_remaining=(expiry - today).days,
            banner=(
                f"House view '{name_disp}' becomes effective on {effective.isoformat()}. "
                "Running without tilts until then."
            ),
            suggestion=None,
            tilts_apply=False,
        )

    days_remaining = (expiry - today).days

    if days_remaining < 0:
        return ViewStatus(
            state="expired",
            view_name=view_name,
            effective_date=meta.get("effective_date"),
            valid_through=expiry.isoformat(),
            days_remaining=days_remaining,
            banner=(
                f"! House view '{name_disp}' expired {-days_remaining} day(s) ago "
                f"({expiry.isoformat()}). Tilts NOT applied. "
                "Run `/parallax-load-house-view --extend` or load a fresh view."
            ),
            suggestion="Refresh required.",
            tilts_apply=False,
        )

    if days_remaining < CRITICAL_DAYS:
        plural = "" if days_remaining == 1 else "s"
        return ViewStatus(
            state="critical",
            view_name=view_name,
            effective_date=meta.get("effective_date"),
            valid_through=expiry.isoformat(),
            days_remaining=days_remaining,
            banner=(
                f"⚠ Active view '{name_disp}' expires in {days_remaining} day{plural} "
                f"({expiry.isoformat()}). Have you received an updated CIO view? "
                "Run `/parallax-load-house-view` to refresh."
            ),
            suggestion="Ask CIO/IC for an updated view.",
            tilts_apply=True,
        )

    if days_remaining < WARNING_DAYS:
        return ViewStatus(
            state="warning",
            view_name=view_name,
            effective_date=meta.get("effective_date"),
            valid_through=expiry.isoformat(),
            days_remaining=days_remaining,
            banner=(
                f"Active view '{name_disp}' expires in {days_remaining} days "
                f"({expiry.isoformat()}); consider refreshing soon."
            ),
            suggestion=None,
            tilts_apply=True,
        )

    return ViewStatus(
        state="active",
        view_name=view_name,
        effective_date=meta.get("effective_date"),
        valid_through=expiry.isoformat(),
        days_remaining=days_remaining,
        banner=(
            f"Active house view: '{name_disp}' — effective {meta.get('effective_date')} "
            f"through {expiry.isoformat()} ({days_remaining} days remaining)."
        ),
        suggestion=None,
        tilts_apply=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="House view status (operator-agnostic helper).",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Override active-house-view dir (default: $PARALLAX_HOUSE_VIEW_DIR or ~/.parallax/active-house-view/).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of banner text.",
    )
    parser.add_argument(
        "--exit-code-by-state",
        action="store_true",
        help="Exit nonzero on expired/malformed (for shell gates).",
    )
    args = parser.parse_args(argv)

    status = compute_status(view_dir=args.dir)

    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
    else:
        print(status.banner)

    if args.exit_code_by_state:
        if status.state in {"expired", "malformed"}:
            return 2
        if status.state in {"not_yet_effective"}:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
