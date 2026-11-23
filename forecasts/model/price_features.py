"""Price lag and daily summary transforms on the market's local clock."""
from collections.abc import Sequence
from datetime import datetime

import pandera.polars as pa
from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.inputs.prices import PriceHistory, UTC
from forecasts.config import LAGS, PRICE_FEATURES, SUMMARY_DAYS


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


def _local_clock(frame: pl.DataFrame, timestamp: str) -> pl.DataFrame:
    local = pl.col(timestamp).dt.convert_time_zone("Europe/Berlin")
    return frame.with_columns(local.dt.date().alias("_day"),
        (local.dt.hour().cast(pl.Int16) * 4 + local.dt.minute() // 15).alias("_quarter"))
