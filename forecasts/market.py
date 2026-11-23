"""Delivery quarters and issue times for the DE–LU day-ahead market."""
from collections.abc import Iterable, Iterator
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
UTC = timezone.utc


def cutoff(day: date) -> datetime:
    """Return the preceding-day 11:00 Berlin issue deadline in UTC."""
    return datetime.combine(day - timedelta(days=1), time(11), BERLIN).astimezone(UTC)


def quarters(start: date, end: date) -> Iterator[datetime]:
    """Yield actual UTC delivery quarters in the local-date interval [start, end)."""
    current = datetime.combine(start, time(), BERLIN).astimezone(UTC)
    stop = datetime.combine(end, time(), BERLIN).astimezone(UTC)
    while current < stop:
        yield current
        current += timedelta(minutes=15)


def issue_deadline(day: date, live: bool, issue_time: datetime | None) -> datetime:
    """Resolve the historical deadline or validate the actual live issue time."""
    deadline = cutoff(day)
    if live:
        if issue_time is None or issue_time.utcoffset() is None:
            raise ValueError("Live selection requires an actual timezone-aware issue timestamp")
        if issue_time > deadline:
            raise ValueError("Actual issue time is after the delivery day's deadline")
        deadline = issue_time
    return deadline


def require_quarters(actual: Iterable[datetime], start: date, end: date, evidence: str) -> None:
    """Require exactly the physical Berlin delivery quarters in the period."""
    observed = list(actual)
    expected = set(quarters(start, end))
    actual_set = set(observed)
    missing = expected - actual_set
    unexpected = actual_set - expected
    duplicates = len(observed) - len(actual_set)
    if missing or unexpected or duplicates or not expected:
        raise ValueError(
            f"{evidence} for {start} through {end - timedelta(days=1)}: "
            f"{len(missing)} missing quarters{_example(missing)}, "
            f"{len(unexpected)} unexpected quarters{_example(unexpected)}, {duplicates} duplicates"
        )


def _example(timestamps: set[datetime]) -> str:
    return f" (first {min(timestamps).isoformat()} UTC)" if timestamps else ""
