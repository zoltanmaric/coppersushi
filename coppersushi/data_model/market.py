"""Typed tables for market outcomes published outside the network model."""

import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictFloat, StrictStr

from pandera.typing import Series
import pandera.pandas as pa

from coppersushi.data_model.jao import ZonedTimestamp


class ElectricityMapsPrice(BaseModel):
    """One published zonal day-ahead price and its source update time."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    zone: StrictStr
    datetime: AwareDatetime
    updatedAt: AwareDatetime
    value: StrictFloat
    unit: Literal["EUR/MWh"]
    source: StrictStr


class ElectricityMapsPriceResponse(BaseModel):
    """One zone's published prices at the resolution stated by Electricity Maps."""

    model_config = ConfigDict(extra="ignore")

    zone: StrictStr
    temporalGranularity: Literal["hourly", "15_minutes"]
    data: list[ElectricityMapsPrice]


class ZonalPrices(pa.DataFrameModel):
    """Observed price per zone and interval."""

    interval: Series[ZonedTimestamp] = pa.Field(dtype_kwargs={"tz": datetime.UTC})
    zone: Series[str]
    price: Series[float]

    class Config:
        strict = False
        coerce = True
        unique = ["interval", "zone"]


class DayAheadPrices(ZonalPrices):
    """Published zonal day-ahead prices, one per zone and market time unit.

    The grain is the market day's, hourly or quarter-hourly, and `market.check_complete` pins
    a table to its day wherever one is known. Timestamps alone cannot say which grain a table
    is on once a row may be missing, so a range spanning delivery day 2025-10-01 is two tables,
    never one frame whose rows change length partway down.
    """

    unit: Series[str] = pa.Field(eq="EUR/MWh")
    source: Series[str]
    updated_at: Series[ZonedTimestamp] = pa.Field(dtype_kwargs={"tz": datetime.UTC})

    class Config:
        strict = False
        coerce = True
        unique = ["interval", "zone"]
