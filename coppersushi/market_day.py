"""The Core market day, which is not the UTC day.

JAO publishes per market day in CET/CEST, so 2024-08-29 runs from 2024-08-28T22:00Z to
2024-08-29T22:00Z, and a day is 23, 24 or 25 hours long depending on daylight saving. Our
snapshots follow it, so a JAO hour maps to a snapshot by identity and nothing has to be
dropped, duplicated or averaged.

Arithmetic happens in local time — ``pd.DateOffset(days=1)`` shifts wall time, so the zone
handles the clock change and we never add 24 hours to a day that has 23.

Design: wiki/specs/jao-grid.md. Timezone rules: coppersushi/AGENTS.md, wiki/timezone-handling.md.
"""

import pandas as pd

MARKET_TZ = "Europe/Brussels"  # CET/CEST, the zone Core's day-ahead market runs on


def window(day: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The market day's ``[start, end)`` as tz-aware UTC timestamps."""
    start = pd.Timestamp(day, tz=MARKET_TZ)
    end = start + pd.DateOffset(days=1)
    return start.tz_convert("UTC"), end.tz_convert("UTC")


def hours(day: str) -> pd.DatetimeIndex:
    """Every hour of the market day, tz-aware UTC: 23, 24 or 25 of them."""
    start, end = window(day)
    return pd.date_range(start, end, freq="h", inclusive="left", tz="UTC")


def snapshots(day: str) -> pd.DatetimeIndex:
    """The market day's hours as PyPSA snapshots.

    The single conversion point where an aware timestamp becomes naive: PyPSA snapshots are
    naive, meaning UTC (coppersushi/AGENTS.md, explicit-timezones).
    """
    return hours(day).tz_localize(None)


def containing(moment: str | pd.Timestamp) -> str:
    """The market day an instant falls in — the inverse of ``config_window``'s start.

    The runner names candidates after the day they cover, but the config carries a window
    *start* (``2024-08-28 22:00``), which is the previous calendar date. Naive input is read as
    UTC, PyPSA's convention; an aware timestamp is converted.
    """
    return str(pd.to_datetime(moment, utc=True).tz_convert(MARKET_TZ).date())


def config_window(day: str) -> tuple[str, str]:
    """The ``snapshots.start`` and ``snapshots.end`` for ``config/coppersushi.yaml``.

    PyPSA-Eur reads them as naive UTC, so they are the market day's UTC window written without
    a zone — derived here rather than hand-copied into the config.
    """
    start, end = window(day)
    return tuple(moment.tz_localize(None).strftime("%Y-%m-%d %H:%M") for moment in (start, end))
