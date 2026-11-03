"""One market-time-unit view of published prices and active flow-based constraints."""

from typing import NamedTuple, cast
import pandera.pandas as pa

import pandas as pd
from pandera.typing import DataFrame
from coppersushi.data_model.jao import ConstraintPtdfs, ActiveConstraints, ActiveExternalConstraints, PriceContributions
from coppersushi.data_model.cnec_attribution import AttributionContext, CountryCaps, AdjacentAttribution, AdjacentUnavailable
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
    external_constraints: DataFrame[ActiveExternalConstraints]
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
    external_constraints: DataFrame[ActiveExternalConstraints],
    prices: DataFrame[Prices],
    interval: pd.Timestamp,
    selected: ConstraintKey | None = None,
    reference_zone: str | None = None,
    context: DataFrame[AttributionContext] | None = None,
    alpha: float | None = None,
    adjacent: DataFrame[AdjacentAttribution] | AdjacentUnavailable | None = None,
) -> Snapshot:
    """Compose one interval, optionally isolating a selected row's relative price effect."""
    if interval.tzinfo is None:
        raise ValueError("interval must be timezone-aware")
    display_prices: pd.DataFrame = prices
    current = _at_interval(constraints, interval)
    external = _at_interval(external_constraints, interval)
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
        elif identity in external.source_id.values:
            row = external[external.source_id.eq(identity)].iloc[0]
            reference_zone = cnec_attribution.virtual_reference(row)
            valid = False
            if row.hub in {"ALBE", "ALDE"} and alpha is not None:
                valid = cnec_attribution.alegro_validated(
                    _at_interval(ptdfs, interval), current, external, _at_interval(prices, interval), alpha)
            elif isinstance(adjacent, pd.DataFrame) and alpha is not None:
                evidence = _at_interval(adjacent, interval)
                evidence = evidence[evidence.hub.eq(row.hub)]
                if len(evidence) == 1:
                    valid = cnec_attribution.virtual_validated(
                        row.hub, _at_interval(ptdfs, interval), current, external,
                        _at_interval(prices, interval), cap_inputs, alpha, evidence.iloc[0])
                    # Retain the adjacent quote even when attribution fails: it is an observed price.
                    _, other, _ = cnec_attribution.INTERFACES[row.hub]
                    display_prices = pd.concat([prices, pd.DataFrame({'interval': [interval], 'zone': [other],
                        'price': [evidence.adjacent_price.iloc[0]]})], ignore_index=True).pipe(ZonalPrices.validate)
            if valid and reference_zone is not None:
                owner, other, _ = cnec_attribution.INTERFACES[row.hub]
                # The selected bound contributes owner-minus-other; reverse for owner reference.
                target = owner if reference_zone == other else other
                value = row.coefficient * row.shadow_price / alpha
                contribution = pd.DataFrame({"zone": [reference_zone, target], "source_id": identity,
                    "reference_zone": reference_zone, "contribution": [0.0, value if target == owner else -value]}).pipe(PriceContributions.validate)
            else:
                if isinstance(adjacent, AdjacentUnavailable):
                    note = adjacent.reason
                elif row.hub in cnec_attribution.LOSS_HUBS:
                    note = "Endpoint contribution unavailable: loss-aware dual scaling is not validated."
                else:
                    note = "Endpoint contribution unavailable: missing inputs or unreconciled losses/ramping terms."
        else:
            raise ValueError("selected constraint matched 0 active rows")
    return Snapshot(
        interval=interval,
        prices=ZonalPrices.validate(display_prices[display_prices.interval.eq(interval)].reset_index(drop=True)),
        constraints=current,
        external_constraints=external,
        contribution=contribution,
        selected_id=None if selected is None else selected.source_id,
        caps=caps,
        reference=reference_zone,
        note=note,
    )
