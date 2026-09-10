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
# A delivery-day label, not an instant. ``MarketDay`` applies ``MARKET_TZ`` at both midnights.
FIFTEEN_MINUTE_DELIVERY_DAY = date(2025, 10, 1)


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
        """Every interval start of the day at ``frequency``, tz-aware UTC."""
        return pd.date_range(
            self.start_time_utc,
            self.end_time_utc,
            freq=frequency,
            inclusive="left",
            tz="UTC",
        )

    @property
    def market_time_unit(self) -> str:
        """The Single Day-Ahead Coupling market time unit, as a pandas frequency.

        Hourly historically and quarter-hourly from delivery day 2025-10-01, the go-live the
        Market Coupling Steering Committee published. That date denotes the local market day;
        ``start_time_local`` and ``end_time_local`` turn its two midnights into instants.
        """
        return "15min" if self.date >= FIFTEEN_MINUTE_DELIVERY_DAY else "h"

    def market_time_units(self) -> pd.DatetimeIndex:
        """Every market time unit of the day: the grain everything the market publishes is read at.

        This calendar rule also supplies intervals with no binding active flow-based row,
        which the sparse JAO response cannot do by itself.
        """
        return self.intervals(self.market_time_unit)
