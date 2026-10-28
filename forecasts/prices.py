"""Price table contract, issue-time selection and local-clock price features."""
from collections.abc import Sequence
from datetime import date, datetime
from typing import Annotated, cast

import pandera.polars as pa
import polars as pl
import pyarrow as arrow
from pandera.typing.polars import DataFrame


UTC = Annotated[pl.Datetime, "us", "UTC"]
LAGS = (1, 2, 7, 14)
SUMMARY_DAYS = (1, 7)
PRICE_FEATURES = [f"price_lag_{d}" for d in LAGS] + [
    f"price_day_{d}_{stat}" for d in SUMMARY_DAYS for stat in ("mean", "min", "max")]


class PriceVersions(pa.DataFrameModel):
    """One retained price revision per UTC delivery quarter and version ID."""
    valid_utc: UTC
    source_update_utc: UTC = pa.Field(nullable=True)
    retrieved_at_utc: UTC = pa.Field(nullable=True)
    timing_evidence: str = pa.Field(isin=["witnessed", "documented", "assumed", "unknown"])
    version_id: str
    raw_key: str
    price_eur_mwh: float = pa.Field(nullable=True, metadata={"unit": "EUR/MWh"})

    class Config:
        strict = True
        unique = ["valid_utc", "version_id"]

    @pa.check("price_eur_mwh")
    def finite_prices(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Allow missing and negative prices, but reject NaN and infinity."""
        return data.lazyframe.select(pl.col("price_eur_mwh").is_finite())


class PriceHistory(pa.DataFrameModel):
    """Selected price values: one nullable outcome per UTC delivery quarter."""
    valid_utc: UTC = pa.Field(unique=True)
    price_eur_mwh: float = pa.Field(nullable=True)

    class Config:
        strict = True

    @pa.check("price_eur_mwh")
    def finite_prices(cls, data: pa.PolarsData) -> pl.LazyFrame:
        """Reject non-finite values while retaining missing outcomes."""
        return data.lazyframe.select(pl.col("price_eur_mwh").is_finite())


class PriceFeatures(pa.DataFrameModel):
    """One row per delivery quarter; lag days use the German local calendar."""
    delivery_utc: UTC = pa.Field(unique=True)
    price_lag_1: float = pa.Field(nullable=True)
    price_lag_2: float = pa.Field(nullable=True)
    price_lag_7: float = pa.Field(nullable=True)
    price_lag_14: float = pa.Field(nullable=True)
    price_day_1_mean: float = pa.Field(nullable=True)
    price_day_1_min: float = pa.Field(nullable=True)
    price_day_1_max: float = pa.Field(nullable=True)
    price_day_7_mean: float = pa.Field(nullable=True)
    price_day_7_min: float = pa.Field(nullable=True)
    price_day_7_max: float = pa.Field(nullable=True)

    class Config:
        strict = True


def read_prices(table: arrow.Table) -> DataFrame[PriceVersions]:
    """Validate actual values as well as schema, without coercing source data."""
    frame = pl.from_arrow(table)
    assert isinstance(frame, pl.DataFrame)
    return PriceVersions.validate(frame)


def select_history(prices: DataFrame[PriceVersions], day: date, deadline: datetime,
                   live: bool = False) -> DataFrame[PriceVersions]:
    """Select earlier delivery dates and revisions available by the aware cutoff.

    Historical selection permits documented or assumed timing. Live selection
    also requires retrieval by the actual issue time. Unknown timing is excluded.
    """
    if deadline.utcoffset() is None:
        raise ValueError("Price selection requires a timezone-aware cutoff")
    eligible = prices.filter(
        (pl.col("valid_utc").dt.convert_time_zone("Europe/Berlin").dt.date() < day)
        & (pl.col("source_update_utc").is_null() | (pl.col("source_update_utc") <= deadline))
        & pl.col("timing_evidence").is_in(["witnessed", "documented", "assumed"])
    )
    if live:
        eligible = eligible.filter(pl.col("retrieved_at_utc") <= deadline)
    return latest_versions(cast(DataFrame[PriceVersions], eligible))


def latest_versions(prices: DataFrame[PriceVersions]) -> DataFrame[PriceVersions]:
    """Keep the latest revision per quarter; reject conflicting same-time values.

    A missing update is older than every known update. Equal-value ties retain
    the last input record. Conflicts at older, superseded update times also fail;
    missing values count as values, matching weather revision selection.
    """
    conflicts = prices.group_by("valid_utc", "source_update_utc").agg(
        pl.col("price_eur_mwh").n_unique().alias("values"))
    if conflicts.filter(pl.col("values") > 1).height:
        raise ValueError("Conflicting source values at the same update time")
    selected = (prices.with_row_index("_position")
            .with_columns(pl.col("_position").min().over("valid_utc").alias("_first"))
            .sort("source_update_utc", "_position", nulls_last=False)
            .unique("valid_utc", keep="last", maintain_order=True)
            .sort("_first").drop("_position", "_first"))
    return cast(DataFrame[PriceVersions], selected)


def build_price_features(prices: DataFrame[PriceHistory], delivery: Sequence[datetime]) -> DataFrame[PriceFeatures]:
    """Build local-clock lags and daily summaries from already eligible prices.

    Repeated clock quarters are averaged; nonexistent quarters remain missing.
    Daily summaries count both physical quarters on an autumn clock change.
    """
    history = _local_clock(prices.rename({"price_eur_mwh": "value"}), "valid_utc").filter(
        pl.col("value").is_not_null())
    clock = history.group_by("_day", "_quarter").agg(pl.col("value").mean())
    daily = history.group_by("_day").agg(
        pl.col("value").mean().alias("mean"), pl.col("value").min().alias("min"),
        pl.col("value").max().alias("max"))
    result = _local_clock(pl.DataFrame({"delivery_utc": delivery},
                          schema={"delivery_utc": pl.Datetime("us", "UTC")}), "delivery_utc")
    for days in LAGS:
        earlier = clock.with_columns((pl.col("_day") + pl.duration(days=days)).cast(pl.Date))
        result = result.join(earlier.rename({"value": f"price_lag_{days}"}),
                             on=["_day", "_quarter"], how="left", maintain_order="left")
    for days in SUMMARY_DAYS:
        earlier = daily.with_columns((pl.col("_day") + pl.duration(days=days)).cast(pl.Date))
        result = result.join(earlier.rename({s: f"price_day_{days}_{s}" for s in ("mean", "min", "max")}),
                             on="_day", how="left", maintain_order="left")
    return PriceFeatures.validate(result.select("delivery_utc", *PRICE_FEATURES))


def snapshot_schema() -> arrow.Schema:
    """Derive the unchanged Parquet wire schema from the price contract."""
    fields = []
    for name, column in PriceVersions.to_schema().columns.items():
        dtype = column.dtype.type
        kind = (arrow.string() if dtype == pl.String else arrow.float64() if dtype == pl.Float64
                else arrow.timestamp(dtype.time_unit, tz=dtype.time_zone))
        fields.append(arrow.field(name, kind, nullable=column.nullable, metadata=column.metadata))
    return arrow.schema(fields)


def _local_clock(frame: pl.DataFrame, timestamp: str) -> pl.DataFrame:
    local = pl.col(timestamp).dt.convert_time_zone("Europe/Berlin")
    return frame.with_columns(local.dt.date().alias("_day"),
        (local.dt.hour().cast(pl.Int16) * 4 + local.dt.minute() // 15).alias("_quarter"))
