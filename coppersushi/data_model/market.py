"""Typed tables for market outcomes published outside the network model."""

from pandera.typing import Series
import pandera.pandas as pa

from coppersushi.data_model.jao import UtcTimestamp


class DayAheadPrices(pa.DataFrameModel):
    """Published zonal day-ahead prices, one per zone and market time unit.

    The grain is the market day's, hourly or quarter-hourly, and `market.check_complete` pins
    a table to its day wherever one is known. Timestamps alone cannot say which grain a table
    is on once a row may be missing, so a range spanning delivery day 2025-10-01 is two tables,
    never one frame whose rows change length partway down.
    """

    interval: Series[UtcTimestamp]
    zone: Series[str]
    price: Series[float]
    unit: Series[str] = pa.Field(eq="EUR/MWh")
    source: Series[str]
    updated_at: Series[UtcTimestamp]

    class Config:
        strict = False
        coerce = True
        unique = ["interval", "zone"]
