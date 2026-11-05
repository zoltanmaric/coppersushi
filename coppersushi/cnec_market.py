"""One market-time-unit view of published prices and active flow-based constraints."""

from typing import NamedTuple, cast
import math
import pandera.pandas as pa

import pandas as pd
from pandera.typing import DataFrame
from coppersushi.data_model.jao import ConstraintPtdfs, ActiveConstraints, PriceContributions
from coppersushi.data_model.cnec_attribution import AttributionContext, CountryCaps
from coppersushi.data_model.market import ZonalPrices

from coppersushi import cnecs, cnec_attribution
from coppersushi.market import CORE_ZONES


class ConstraintKey(NamedTuple):
    """The publication's stable identifier for one physical row."""

    source_id: int


class Snapshot(NamedTuple):
    """Everything the CNEC page shows for one market time unit."""

    interval: pd.Timestamp
    prices: DataFrame[ZonalPrices]
    constraints: DataFrame[ActiveConstraints]
    contribution: DataFrame[PriceContributions] | None
    caps: DataFrame[CountryCaps]
    price_range: tuple[float, float]
    selected_id: int | None = None
    reference: str | None = None
    notes: tuple[str, ...] = ()


def daily_price_range[Prices: ZonalPrices](prices: DataFrame[Prices]) -> tuple[float, float]:
    """One scale across every supplied market-day interval and Core bidding zone."""
    values = prices.loc[prices.zone.isin(CORE_ZONES), "price"]
    if values.empty or not values.map(math.isfinite).all():
        raise ValueError("A daily price scale requires finite Core prices")
    return float(values.min()), float(values.max())


def key_of(constraint: pd.Series) -> ConstraintKey:
    return ConstraintKey(int(constraint.source_id))


def _at_interval[Schema: pa.DataFrameModel](frame: DataFrame[Schema], interval: pd.Timestamp) -> DataFrame[Schema]:
    # Row selection preserves the validated column schema; pandas stubs erase it.
    return cast(DataFrame[Schema], frame[frame.interval.eq(interval)].reset_index(drop=True))


def snapshot[Prices: ZonalPrices](
    constraints: DataFrame[ActiveConstraints],
    ptdfs: DataFrame[ConstraintPtdfs],
    prices: DataFrame[Prices],
    interval: pd.Timestamp,
    selected: ConstraintKey | None = None,
    reference_zone: str | None = None,
    context: DataFrame[AttributionContext] | None = None,
    alpha: float | None = None,
) -> Snapshot:
    """Compose one interval, optionally isolating a selected row's relative price effect."""
    if interval.tzinfo is None:
        raise ValueError("interval must be timezone-aware")
    display_prices: pd.DataFrame = prices
    current = _at_interval(constraints, interval)
    contribution: DataFrame[PriceContributions] | None = None
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
    if selected is not None:
        identity = selected.source_id
        if identity in current.source_id.values:
            chosen = current[current.source_id.eq(identity)]
            if reference_zone is None:
                raise ValueError("a selected constraint requires an explicit reference zone")
            if alpha is not None and 0 < alpha <= 1:
                contribution = cnecs.price_contributions(chosen.iloc[0], ptdfs, reference_zone, alpha).pipe(PriceContributions.validate)
            else:
                notes.append("Contribution unavailable: missing or zero FB scaling factor α.")
        elif identity in caps.source_id.values:
            row = caps[caps.source_id.eq(identity)].iloc[0]
            reference_zone = reference_zone or "PL"
            cap_contribution = pd.DataFrame({"zone": CORE_ZONES, "source_id": identity,
                                         "reference_zone": "PL", "contribution": -row.delta})
            cap_contribution.loc[cap_contribution.zone.eq("PL"), "contribution"] = 0.0
            baseline = cap_contribution.loc[cap_contribution.zone.eq(reference_zone), "contribution"]
            if len(baseline) != 1:
                raise ValueError("reference must be a Core bidding zone")
            cap_contribution = cap_contribution.assign(
                contribution=cap_contribution["contribution"] - baseline.iloc[0], reference_zone=reference_zone)
            contribution = PriceContributions.validate(cap_contribution)
        else:
            raise ValueError("selected constraint matched 0 active rows")
    return Snapshot(
        interval=interval,
        prices=ZonalPrices.validate(display_prices[display_prices.interval.eq(interval)].reset_index(drop=True)),
        constraints=current,
        contribution=contribution,
        selected_id=None if selected is None else selected.source_id,
        caps=caps,
        price_range=daily_price_range(prices),
        reference=reference_zone,
        notes=tuple(notes),
    )
