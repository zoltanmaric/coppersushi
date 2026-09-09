"""The Core market day: local midnight to local midnight in CET/CEST, so 23, 24 or 25 hours.

Arithmetic stays in local time — ``pd.DateOffset(days=1)`` shifts wall time — so the zone
resolves the clock change rather than us adding 24 hours to a day that has 23.

Domain: wiki/flow-based-market-coupling.md. Timezones: coppersushi/AGENTS.md.
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
    """The market day an instant falls in; the inverse of ``config_window``'s start.

    Naive input is read as UTC, PyPSA's convention; an aware timestamp is converted.
    """
    return str(pd.to_datetime(moment, utc=True).tz_convert(MARKET_TZ).date())


def config_window(day: str) -> tuple[str, str]:
    """The market day's window as naive-UTC strings, the form PyPSA-Eur's ``snapshots`` takes."""
    start, end = window(day)
    return tuple(moment.tz_localize(None).strftime("%Y-%m-%d %H:%M") for moment in (start, end))
