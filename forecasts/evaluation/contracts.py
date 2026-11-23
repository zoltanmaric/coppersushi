"""Unscored backtest outputs and the corresponding scoring results."""
from dataclasses import dataclass

import pandera.polars as pa
from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.config import MODEL_METHOD, PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE, QUANTILES
from forecasts.inputs.input_types import Report
from forecasts.inputs.prices import UTC

FORECAST_METHODS = (MODEL_METHOD, "reference")


class Predictions(pa.DataFrameModel):
    """Backtest rows with five ordered quantiles per method and no outcomes."""
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
        flags = [*PRICE_MISSING_FIELDS, PRICE_UNAVAILABLE]
        columns = {name: pa.Column(int, checks=pa.Check.isin([0, 1])) for name in flags}
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


@dataclass
class BacktestPredictions:
    """Fixed predictions and fit diagnostics, before joining realised prices."""
    rows: DataFrame[Predictions]
    folds: list[Report]
    failures: list[Report]
    crossing_rows: dict[str, int]


@dataclass
class EvaluationResult:
    """Predictions joined with scoring truth, plus aggregate comparisons."""
    rows: DataFrame[ScoredPredictions]
    report: Report


def _finite(data: pa.PolarsData) -> pl.LazyFrame:
    return data.lazyframe.select(pl.col(data.key).is_finite())
