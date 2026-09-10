"""Typed tables for market outcomes published outside the network model."""

from pandera.typing import Series
import pandera.pandas as pa

from coppersushi.data_model.jao import UtcTimestamp


class DayAheadPrices(pa.DataFrameModel):
    """Published zonal day-ahead prices at their source resolution."""

    interval: Series[UtcTimestamp]
    zone: Series[str]
    price: Series[float]
    unit: Series[str] = pa.Field(eq="EUR/MWh")
    source: Series[str]
    updated_at: Series[UtcTimestamp]

    class Config:
        strict = False
        coerce = True
