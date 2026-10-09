"""One market-time-unit view of published prices and active flow-based constraints."""

from typing import NamedTuple

import pandas as pd

from coppersushi import cnecs, cnec_attribution
from coppersushi.market import CORE_ZONES


class ConstraintKey(NamedTuple):
    """The publication's stable identifier for one physical row."""

    source_id: int


class Snapshot(NamedTuple):
    """Everything the CNEC page shows for one market time unit."""

    interval: pd.Timestamp
    prices: pd.DataFrame
    constraints: pd.DataFrame
    external_constraints: pd.DataFrame
    contribution: pd.DataFrame | None
    selected_id: int | None = None
    caps: pd.DataFrame | None = None
    reference: str | None = None
    note: str = ""


def key_of(constraint: pd.Series) -> ConstraintKey:
    return ConstraintKey(int(constraint.source_id))


def _at_interval(frame: pd.DataFrame, interval: pd.Timestamp) -> pd.DataFrame:
    return frame[frame.interval.eq(interval)].reset_index(drop=True)


def snapshot(
    constraints: pd.DataFrame,
    ptdfs: pd.DataFrame,
    external_constraints: pd.DataFrame,
    prices: pd.DataFrame,
    interval: pd.Timestamp,
    selected: ConstraintKey | None = None,
    reference_zone: str | None = None,
    context: pd.DataFrame | None = None,
    alpha: float | None = None,
) -> Snapshot:
    """Compose one interval, optionally isolating a selected row's relative price effect."""
    if interval.tzinfo is None:
        raise ValueError("interval must be timezone-aware")
    current = _at_interval(constraints, interval)
    external = _at_interval(external_constraints, interval)
    contribution = None
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
                contribution = cnecs.price_contributions(chosen.iloc[0], ptdfs, reference_zone, alpha)
            else:
                note = "Contribution unavailable: missing or zero FB scaling factor α."
        elif identity in caps.source_id.values:
            row = caps[caps.source_id.eq(identity)].iloc[0]
            reference_zone = "PL"
            contribution = pd.DataFrame({"zone": CORE_ZONES, "source_id": identity,
                                         "reference_zone": "PL", "contribution": -row.delta})
            contribution.loc[contribution.zone.eq("PL"), "contribution"] = 0.0
        elif identity in external.source_id.values:
            row = external[external.source_id.eq(identity)].iloc[0]
            reference_zone = cnec_attribution.virtual_reference(row)
            valid = row.hub in {"ALBE", "ALDE"} and alpha is not None and cnec_attribution.alegro_validated(
                _at_interval(ptdfs, interval), current, external, _at_interval(prices, interval), alpha)
            if valid and reference_zone is not None:
                owner, other, _ = cnec_attribution.INTERFACES[row.hub]
                # The selected bound contributes owner-minus-other; reverse for owner reference.
                target = owner if reference_zone == other else other
                value = row.coefficient * row.shadow_price / alpha
                contribution = pd.DataFrame({"zone": [reference_zone, target], "source_id": identity,
                    "reference_zone": reference_zone, "contribution": [0.0, value if target == owner else -value]})
            else:
                note = "Endpoint contribution unavailable: interface attribution is not validated for these inputs."
        else:
            raise ValueError("selected constraint matched 0 active rows")
    return Snapshot(
        interval=interval,
        prices=_at_interval(prices, interval),
        constraints=current,
        external_constraints=external,
        contribution=contribution,
        selected_id=None if selected is None else selected.source_id,
        caps=caps,
        reference=reference_zone,
        note=note,
    )
