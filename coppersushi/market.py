"""Pure transformations for published zonal market outcomes."""

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.market import DayAheadPrices

CORE_ZONES = ("AT", "BE", "CZ", "DE", "FR", "HR", "HU", "NL", "PL", "RO", "SI", "SK")


def day_ahead_prices(payloads: list[dict]) -> DataFrame[DayAheadPrices]:
    """Electricity Maps price responses as one row per source interval and zone."""
    rows = [row for payload in payloads for row in payload["data"]]
    frame = pd.DataFrame(rows).rename(
        columns={"datetime": "interval", "value": "price", "updatedAt": "updated_at"}
    )
    frame = frame.assign(
        interval=pd.to_datetime(frame.interval, utc=True, format="ISO8601"),
        updated_at=pd.to_datetime(frame.updated_at, utc=True, format="ISO8601"),
    )
    columns = ["interval", "zone", "price", "unit", "source", "updated_at"]
    prices = frame[columns].sort_values(["interval", "zone"], ignore_index=True)
    repeated = prices[prices.duplicated(["interval", "zone"], keep=False)]
    if not repeated.empty:
        keys = repeated[["interval", "zone"]].astype(str).agg("/".join, axis="columns")
        raise ValueError(f"several day-ahead prices for: {', '.join(keys)}")
    return prices.pipe(DayAheadPrices.validate)


def prices_at(prices: DataFrame[DayAheadPrices], interval: pd.Timestamp) -> DataFrame[DayAheadPrices]:
    """The latest published price at or before ``interval``, independently for every zone.

    This is deliberately an as-of lookup rather than resampling. An hourly source value
    remains one hourly value used by the four quarter-hourly capacity intervals it covers.
    No intermediate prices are invented.
    """
    if interval.tzinfo is None:
        raise ValueError("interval must be timezone-aware")
    candidates = prices[prices.interval <= interval]
    if candidates.empty:
        return prices.iloc[0:0]
    latest = candidates.groupby("zone").interval.transform("max")
    return candidates[candidates.interval.eq(latest)].reset_index(drop=True).pipe(DayAheadPrices.validate)
