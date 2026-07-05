"""Cron schedule helpers: compute and describe the next run time."""
from datetime import datetime, timezone

from croniter import croniter


def next_run_at(schedule: str | None, base: datetime | None = None) -> datetime | None:
    """Return the next datetime a cron expression fires after `base` (UTC now).

    Returns None when there is no schedule or it can't be parsed.
    """
    if not schedule:
        return None
    base = base or datetime.now(timezone.utc)
    try:
        return croniter(schedule, base).get_next(datetime)
    except Exception:
        return None


def humanize_until(target: datetime | None, now: datetime | None = None) -> str | None:
    """Human-friendly "in 5 minutes" style string until `target`."""
    if target is None:
        return None
    now = now or datetime.now(timezone.utc)
    seconds = int((target - now).total_seconds())
    if seconds <= 0:
        return "due now"

    minutes, hours, days = seconds // 60, seconds // 3600, seconds // 86400

    def plural(n: int, unit: str) -> str:
        return f"in {n} {unit}{'' if n == 1 else 's'}"

    if seconds < 60:
        return "in less than a minute"
    if minutes < 60:
        return plural(minutes, "minute")
    if hours < 24:
        return plural(hours, "hour")
    return plural(days, "day")
