"""One market-time-unit view of published prices and active flow-based constraints."""

from typing import NamedTuple, cast
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
    selected_id: int | None = None
    reference: str | None = None
    note: str = ""


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
    note = ""
    if cap_inputs is None or len(cap_inputs) != 1 or cap_inputs.iloc[0][["polish_alt", "polish_position", "import_limit", "export_limit"]].isna().any():
        note = "Poland cap attribution unavailable for this interval."
    if selected is not None:
        identity = selected.source_id
        if identity in current.source_id.values:
            chosen = current[current.source_id.eq(identity)]
            if reference_zone is None:
                raise ValueError("a selected constraint requires an explicit reference zone")
            if alpha is not None and 0 < alpha <= 1:
                contribution = cnecs.price_contributions(chosen.iloc[0], ptdfs, reference_zone, alpha).pipe(PriceContributions.validate)
            else:
                note = "Contribution unavailable: missing or zero FB scaling factor α."
        elif identity in caps.source_id.values:
            row = caps[caps.source_id.eq(identity)].iloc[0]
            reference_zone = "PL"
            cap_contribution = pd.DataFrame({"zone": CORE_ZONES, "source_id": identity,
                                         "reference_zone": "PL", "contribution": -row.delta})
            cap_contribution.loc[cap_contribution.zone.eq("PL"), "contribution"] = 0.0
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
        reference=reference_zone,
        note=note,
    )
