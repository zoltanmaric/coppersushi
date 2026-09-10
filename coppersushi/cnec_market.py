"""One market-time-unit view of published prices and Active FB constraints."""

from typing import NamedTuple

import pandas as pd

from coppersushi import cnecs, market


class ConstraintKey(NamedTuple):
    """The natural key of one physical row within a market time unit."""

    eic: str
    direction: str
    cont_name: str


class Snapshot(NamedTuple):
    """Everything the CNEC page shows for one market time unit."""

    interval: pd.Timestamp
    prices: pd.DataFrame
    constraints: pd.DataFrame
    external_constraints: pd.DataFrame
    contribution: pd.DataFrame | None


def key_of(constraint: pd.Series) -> ConstraintKey:
    return ConstraintKey(constraint.eic, constraint.direction, constraint.cont_name)


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
) -> Snapshot:
    """Compose one interval, optionally isolating a selected row's relative price effect."""
    if interval.tzinfo is None:
        raise ValueError("interval must be timezone-aware")
    current = _at_interval(constraints, interval)
    external = _at_interval(external_constraints, interval)
    contribution = None
    if selected is not None:
        chosen = current[
            current.eic.eq(selected.eic)
            & current.direction.eq(selected.direction)
            & current.cont_name.eq(selected.cont_name)
        ]
        if len(chosen) != 1:
            raise ValueError(f"selected constraint matched {len(chosen)} active rows")
        if reference_zone is None:
            raise ValueError("a selected constraint requires an explicit reference zone")
        contribution = cnecs.price_contributions(chosen.iloc[0], ptdfs, reference_zone)
    return Snapshot(
        interval=interval,
        prices=market.prices_at(prices, interval),
        constraints=current,
        external_constraints=external,
        contribution=contribution,
    )
