"""Validated tables at the feature, prediction and scoring stage boundaries."""
from functools import cache

import pandera.polars as pa
import polars as pl

from forecasts.config import MODEL_METHOD, QUANTILES
from forecasts.input_config import WEATHER_FIELDS
from forecasts.prices import PriceFeatures, PRICE_FEATURES, UTC

FORECAST_METHODS = (MODEL_METHOD, "reference")
PRICE_MISSING_FIELDS = [f"{field}_missing" for field in PRICE_FEATURES]
PRICE_UNAVAILABLE = "price_lags_unavailable"
WEATHER_MISSING_FIELDS = [f"{field}_missing" for field in WEATHER_FIELDS]
SOURCE_FLAGS = ("demand_source_unavailable", "weather_source_unavailable", "price_lags_unavailable")


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
        return super().to_schema().add_columns(_binary_columns([*PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE]))

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


class DiagnosticFeatures(Features):
    """Historical source coverage, including weather and demand evidence."""

    weather_timing_assumed: int = pa.Field(eq=1)
    demand_timing_conditional: int = pa.Field(eq=1)
    demand_mw: float = pa.Field(nullable=True)
    demand_available: int = pa.Field(isin=[0, 1])
    demand_missing: int = pa.Field(isin=[0, 1])
    demand_selected_update_utc: UTC = pa.Field(nullable=True)
    demand_screen: str
    demand_archive_versions: int = pa.Field(ge=0)
    demand_archived_latest_update_utc: UTC = pa.Field(nullable=True)

    @classmethod
    @cache
    def to_schema(cls) -> pa.DataFrameSchema:
        """Add the fixed weather inventory and its per-column missing flags."""
        schema = super().to_schema()
        columns = {name: pa.Column(float, nullable=True, checks=pa.Check(_finite))
                   for name in WEATHER_FIELDS}
        columns.update({name: pa.Column(int, checks=pa.Check.isin([0, 1]))
                        for name in [*WEATHER_MISSING_FIELDS, "demand_source_unavailable", "weather_source_unavailable"]})
        return schema.add_columns(columns)

    @pa.dataframe_check
    @classmethod
    def valid_demand(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Allow missing demand and reject non-finite values."""
        return data.lazyframe.select(pl.col("demand_mw").is_null() | pl.col("demand_mw").is_finite())


class Predictions(pa.DataFrameModel):
    """Five finite ordered quantiles per method, before outcomes are joined."""
    delivery_utc: UTC = pa.Field(unique=True)
    delivery_date: pl.Date
    selected_model: str = pa.Field(isin=[*FORECAST_METHODS])
    fallback_reason: str
    fold: pl.Date

    class Config:
        strict = True

    @classmethod
    def to_schema(cls) -> pa.DataFrameSchema:
        """Declare every method/quantile column from the shared fixed contract."""
        columns = _binary_columns([*PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE])
        for method in FORECAST_METHODS:
            columns.update({f"{method}_q{q}": pa.Column(float, checks=pa.Check(_finite)) for q in QUANTILES})
        columns.update({f"{MODEL_METHOD}_raw_q{q}": pa.Column(float, checks=pa.Check(_finite)) for q in QUANTILES})
        return super().to_schema().add_columns(columns)

    @pa.dataframe_check
    @classmethod
    def ordered_quantiles(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Keep raw crossings for diagnostics, but require ordered usable outputs."""
        return data.lazyframe.select(pl.all_horizontal([
            pl.col(f"{method}_q{a}") <= pl.col(f"{method}_q{b}")
            for method in FORECAST_METHODS for a, b in zip(QUANTILES, QUANTILES[1:])]))


class ScoredPredictions(Predictions):
    """Forecasts joined to nullable realised outcomes, including missing truth."""
    target: float = pa.Field(nullable=True)
    target_missing: int = pa.Field(isin=[0, 1])

    @pa.dataframe_check
    @classmethod
    def valid_truth(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Missing flags must match truth; observed outcomes must be finite."""
        return data.lazyframe.select(
            (pl.col("target_missing") == pl.col("target").is_null().cast(pl.Int64))
            & (pl.col("target").is_null() | pl.col("target").is_finite()))


def _finite(data: pa.PolarsData) -> pl.LazyFrame:
    return data.lazyframe.select(pl.col(data.key).is_finite())


def _binary_columns(names: list[str]) -> dict[str, pa.Column]:
    return {name: pa.Column(int, checks=pa.Check.isin([0, 1])) for name in names}
