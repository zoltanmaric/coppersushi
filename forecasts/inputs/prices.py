"""Price table contracts and issue-time version selection."""
from datetime import date, datetime
from typing import cast

import pandera.polars as pa
import polars as pl
import pyarrow as arrow
from pandera.typing.polars import DataFrame

from forecasts.inputs.availability import available_at
from forecasts.inputs.schemas import PriceVersions, UTC


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
    eligible = prices.filter(
        (pl.col("valid_utc").dt.convert_time_zone("Europe/Berlin").dt.date() < day)
        & available_at(deadline, live=live)
    )
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
