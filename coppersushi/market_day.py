"""The market operating day: local midnight to local midnight, so 23, 24 or 25 hours long.

``MarketDay`` rather than ``CetMarketDay`` because the zone is a constructor argument and CET
is only its default.

Calendar arithmetic runs on the naive local date, never on the aware start: adding
``timedelta(days=1)`` to an aware datetime adds exactly 24 hours and steps over a clock change.

Domain: wiki/flow-based-market-coupling.md. Timezones: coppersushi/AGENTS.md.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

MARKET_TZ = ZoneInfo("Europe/Brussels")  # CET/CEST, the zone Core's day-ahead market runs on


@dataclass(frozen=True)
class MarketDay:
    """One operating day in ``zone``, as the half-open window ``[start, end)``."""

    date: date
    zone: ZoneInfo = MARKET_TZ

    @classmethod
    def on(cls, day: str | date, zone: ZoneInfo = MARKET_TZ) -> "MarketDay":
        """The operating day of a calendar date, ``"2024-08-29"`` or a ``datetime.date``."""
        return cls(date.fromisoformat(day) if isinstance(day, str) else day, zone)

    @classmethod
    def containing(cls, moment: datetime, zone: ZoneInfo = MARKET_TZ) -> "MarketDay":
        """The operating day an instant falls in; a naive instant is read as UTC."""
        aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
        return cls(aware.astimezone(zone).date(), zone)

    @property
    def start_time_local(self) -> datetime:
        return datetime.combine(self.date, time.min, tzinfo=self.zone)

    @property
    def end_time_local(self) -> datetime:
        return datetime.combine(self.date + timedelta(days=1), time.min, tzinfo=self.zone)

    @property
    def start_time_utc(self) -> datetime:
        return self.start_time_local.astimezone(UTC)

    @property
    def end_time_utc(self) -> datetime:
        return self.end_time_local.astimezone(UTC)

    def hours(self) -> pd.DatetimeIndex:
        """Every hour of the day, tz-aware UTC: 23, 24 or 25 of them."""
        return self.intervals("h")

    def intervals(self, frequency: str = "15min") -> pd.DatetimeIndex:
        """Every market-time-unit start in the day, tz-aware UTC.

        Core day-ahead capacity data is quarter-hourly while some price sources still
        publish hourly values. Keeping the source resolution explicit avoids inventing
        four distinct prices where the source supplied one.
        """
        return pd.date_range(
            self.start_time_utc,
            self.end_time_utc,
            freq=frequency,
            inclusive="left",
            tz="UTC",
        )
