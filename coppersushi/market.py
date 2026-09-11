"""Pure transformations for published zonal market outcomes."""

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.market import DayAheadPrices
from coppersushi.market_day import MarketDay

CORE_ZONES = ("AT", "BE", "CZ", "DE", "FR", "HR", "HU", "NL", "PL", "RO", "SI", "SK")
ZONE_NAMES = {
    "AT": "Austria",
    "BE": "Belgium",
    "CZ": "Czechia",
    "DE": "Germany",
    "FR": "France",
    "HR": "Croatia",
    "HU": "Hungary",
    "NL": "Netherlands",
    "PL": "Poland",
    "RO": "Romania",
    "SI": "Slovenia",
    "SK": "Slovakia",
}


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
    return frame[columns].sort_values(["interval", "zone"], ignore_index=True).pipe(DayAheadPrices.validate)


def check_complete(prices: DataFrame[DayAheadPrices], day: MarketDay, zones: tuple[str, ...]) -> None:
    """Raise unless ``prices`` holds every zone at every market time unit of ``day``, and nothing else.

    The market time unit is the grain prices are read at, by exact match. A table at a coarser
    grain is not a table with gaps but a table of wrong answers — an hourly mean of four
    quarter-hourly cleared prices is a price the market never cleared at — so it is refused whole.
    Duplicate keys are the schema's to refuse; the index difference below would not see them.
    """
    expected = pd.MultiIndex.from_product([day.market_time_units(), zones], names=["interval", "zone"])
    actual = pd.MultiIndex.from_frame(prices[["interval", "zone"]])
    missing = expected.difference(actual)
    extra = actual.difference(expected)
    if len(missing) or len(extra):
        raise ValueError(
            f"prices for {day.date}: {len(missing)} zone market time units missing, "
            f"{len(extra)} outside the day or its zones"
        )
