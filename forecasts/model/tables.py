"""Validated model features with typed clocks and coverage flags."""
from functools import cache

import pandera.polars as pa
import polars as pl

from forecasts.inputs.prices import UTC
from forecasts.config import PRICE_FEATURES, PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE
from forecasts.model.price_features import PriceFeatures

class Features(PriceFeatures):
    """Price and calendar inputs with typed clocks and explicit missing flags."""
    delivery_date: pl.Date
    issue_cutoff_utc: UTC
    utc_offset_minutes: int
    clock_fold: int = pa.Field(isin=[0, 1])
    quarter_of_day: int = pa.Field(ge=0, le=95)
    day_of_week: int = pa.Field(ge=0, le=6)
    month: int = pa.Field(ge=1, le=12)
    public_holiday: int = pa.Field(isin=[0, 1])
    price_timing_assumed: int = pa.Field(eq=1)

    @classmethod
    @cache
    def to_schema(cls) -> pa.DataFrameSchema:
        """Declare all price availability flags."""
        flags = [*PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE]
        return super().to_schema().add_columns({name: pa.Column(int, checks=pa.Check.isin([0, 1]))
                                                for name in flags})

    @pa.dataframe_check
    @classmethod
    def valid_inputs(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Reject contradictory clocks, non-finite prices and inconsistent flags."""
        return data.lazyframe.select(
            (pl.col("delivery_date") == pl.col("delivery_utc").dt.convert_time_zone("Europe/Berlin").dt.date())
            & pl.all_horizontal([
                (pl.col(f).is_null() | pl.col(f).is_finite())
                & (pl.col(f + "_missing") == pl.col(f).is_null().cast(pl.Int64))
                for f in PRICE_FEATURES]))
