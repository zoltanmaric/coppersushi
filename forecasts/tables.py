"""Validated tables at the feature, prediction and scoring stage boundaries."""
from collections.abc import Sequence

import pandera.polars as pa
from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.config import QUANTILES
from forecasts.input_types import Row
from forecasts.prices import PriceFeatures, PRICE_FEATURES, UTC
from forecasts.snapshot import WEATHER_FIELDS

MODEL_METHODS = ("prices", "weather", "demand")
FORECAST_METHODS = (*MODEL_METHODS, "reference", "system")
MISSING_FIELDS = [f"{field}_missing" for field in [*PRICE_FEATURES, *WEATHER_FIELDS]]
SOURCE_FLAGS = ("demand_source_unavailable", "weather_source_unavailable", "price_lags_unavailable")


class Features(PriceFeatures):
    """Assembled inputs, with typed clocks and explicit nullable source values.

    The two empty outcome fields preserve the input audit format; they cannot
    carry training labels or scoring truth. Weather columns follow the fixed
    location inventory. Missing indicators and source flags are binary.
    """
    delivery_date: pl.Date
    issue_cutoff_utc: UTC
    utc_offset_minutes: int
    clock_fold: int = pa.Field(isin=[0, 1])
    price_eur_mwh: float = pa.Field(nullable=True)
    target_missing: int = pa.Field(eq=1)
    quarter_of_day: int = pa.Field(ge=0, le=95)
    day_of_week: int = pa.Field(ge=0, le=6)
    month: int = pa.Field(ge=1, le=12)
    public_holiday: int = pa.Field(isin=[0, 1])
    price_timing_assumed: int = pa.Field(eq=1)
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
    def to_schema(cls) -> pa.DataFrameSchema:
        """Add the fixed weather inventory and its per-column missing flags."""
        schema = super().to_schema()
        columns = {name: pa.Column(float, nullable=True, checks=pa.Check(_finite))
                   for name in WEATHER_FIELDS}
        columns.update({name: pa.Column(int, checks=pa.Check.isin([0, 1]))
                        for name in [*MISSING_FIELDS, *SOURCE_FLAGS]})
        return schema.add_columns(columns)

    @pa.dataframe_check
    @classmethod
    def valid_inputs(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Reject leaked outcomes, invalid clocks and non-finite source values."""
        return data.lazyframe.select(
            pl.col("price_eur_mwh").is_null()
            & (pl.col("delivery_date") == pl.col("delivery_utc").dt.convert_time_zone("Europe/Berlin").dt.date())
            & pl.all_horizontal([pl.col(f).is_null() | pl.col(f).is_finite()
                                 for f in [*PRICE_FEATURES, "demand_mw"]]))


class Predictions(pa.DataFrameModel):
    """Five finite ordered quantiles per method, before outcomes are joined."""
    delivery_utc: UTC = pa.Field(unique=True)
    delivery_date: pl.Date
    demand_available: int = pa.Field(isin=[0, 1])
    selected_model: str = pa.Field(isin=[*MODEL_METHODS, "reference"])
    fallback_reason: str
    fold: pl.Date
    target_missing: int = pa.Field(eq=1)
    demand_missing: int = pa.Field(isin=[0, 1])
    demand_selected_update_utc: UTC = pa.Field(nullable=True)

    class Config:
        strict = True

    @classmethod
    def to_schema(cls) -> pa.DataFrameSchema:
        """Declare every method/quantile column from the shared fixed contract."""
        columns = {name: pa.Column(int, checks=pa.Check.isin([0, 1]))
                   for name in [*MISSING_FIELDS, *SOURCE_FLAGS]}
        for method in FORECAST_METHODS:
            columns.update({f"{method}_q{q}": pa.Column(float, checks=pa.Check(_finite)) for q in QUANTILES})
        for method in MODEL_METHODS:
            columns.update({f"{method}_raw_q{q}": pa.Column(float, checks=pa.Check(_finite)) for q in QUANTILES})
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


def feature_table(records: Sequence[Row]) -> DataFrame[Features]:
    """Parse input assembly records before entering local evaluation."""
    schema = Features.to_schema()
    frame = pl.DataFrame(records, infer_schema_length=None)
    for name, column in schema.columns.items():
        dtype = column.dtype.type
        if dtype == pl.Date:
            frame = frame.with_columns(pl.col(name).str.to_date())
        elif isinstance(dtype, pl.Datetime):
            frame = frame.with_columns(pl.col(name).cast(pl.String).str.to_datetime(format="%+", time_zone="UTC", time_unit="us"))
        else:
            frame = frame.with_columns(pl.col(name).cast(dtype, strict=True))
    return Features.validate(frame)


def _finite(data: pa.PolarsData) -> pl.LazyFrame:
    return data.lazyframe.select(pl.col(data.key).is_finite())
