"""One market-time-unit view of published prices and active flow-based constraints."""

from typing import NamedTuple, cast
import math
import pandera.pandas as pa

import pandas as pd
from pandera.typing import DataFrame
from coppersushi.pipelines.data_model.jao import ActiveConstraints
from coppersushi.pipelines.data_model.cnec_attribution import AttributionContext
from coppersushi.pipelines.data_model.cnec_attribution import CountryCaps
from coppersushi.pipelines.data_model.market import ZonalPrices

from coppersushi.pipelines.cnec import attribution as cnec_attribution
from coppersushi.pipelines.cnec.prices import CORE_ZONES


class Snapshot(NamedTuple):
    """Prepared source inputs for one market time unit."""

    interval: pd.Timestamp
    prices: DataFrame[ZonalPrices]
    constraints: DataFrame[ActiveConstraints]
    caps: DataFrame[CountryCaps]
    notes: tuple[str, ...] = ()


def daily_price_range[Prices: ZonalPrices](prices: DataFrame[Prices]) -> tuple[float, float]:
    """One scale across every supplied market-day interval and Core bidding zone."""
    values = prices.loc[prices.zone.isin(CORE_ZONES), "price"]
    if values.empty or not values.map(math.isfinite).all():
        raise ValueError("A daily price scale requires finite Core prices")
    return float(values.min()), float(values.max())


def _at_interval[Schema: pa.DataFrameModel](frame: DataFrame[Schema], interval: pd.Timestamp) -> DataFrame[Schema]:
    # Row selection preserves the validated column schema; pandas stubs erase it.
    return cast(DataFrame[Schema], frame[frame.interval.eq(interval)].reset_index(drop=True))


def snapshot[Prices: ZonalPrices](
    constraints: DataFrame[ActiveConstraints],
    prices: DataFrame[Prices],
    interval: pd.Timestamp,
    context: DataFrame[AttributionContext] | None = None,
) -> Snapshot:
    """Compose prices, physical rows, inferred country caps and availability notes."""
    if interval.tzinfo is None:
        raise ValueError("interval must be timezone-aware")
    current = _at_interval(constraints, interval)
    caps = cnec_attribution.country_caps(context, prices, interval)
    cap_inputs = None if context is None else _at_interval(context, interval)
    notes: list[str] = []
    polish_prices = prices[prices.interval.eq(interval) & prices.zone.eq("PL")]
    polish_price = float(polish_prices.price.iloc[0]) if len(polish_prices) == 1 else float("nan")
    if cap_inputs is None or len(cap_inputs) != 1 or cnec_attribution.polish_cap_attribution_unavailable(
        cap_inputs.iloc[0].polish_position, cap_inputs.iloc[0].import_limit,
        cap_inputs.iloc[0].export_limit, cap_inputs.iloc[0].polish_alt, polish_price,
    ):
        notes.append("Poland cap attribution unavailable for this interval.")
    return Snapshot(
        interval=interval,
        prices=ZonalPrices.validate(prices[prices.interval.eq(interval)].reset_index(drop=True)),
        constraints=current,
        caps=caps,
        notes=tuple(notes),
    )
