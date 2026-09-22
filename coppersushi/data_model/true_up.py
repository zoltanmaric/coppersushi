"""Pandera schemas for JAO's published limits, written onto our branches as ratings.

The grain steps down twice. `Limits` is JAO's own: one row per element, direction and hour.
`Ratings` is the network's: one row per branch and hour, several elements having been summed
onto each branch. `RatingComparison` and `RatingReport` carry the audit of the second step —
how far JAO's rating of a branch is from the one our network already had.

`strict = False` throughout, matching `data_model/jao.py`.
"""

import pandera.pandas as pa
from pandera.typing import Series

from coppersushi.data_model.jao import UtcTimestamp


class Limits(pa.DataFrameModel):
    """One row per (element EIC, direction, hour): what JAO allowed that element that hour."""

    eic: Series[str]  # EIC code of the monitored element
    direction: Series[str]  # DIRECT or OPPOSITE, the sense the limit applies in
    hour: Series[UtcTimestamp]  # Market time unit, its first instant
    fmax: Series[float]  # Maximum admissible flow [MW]
    fmax_type: Series[str] = pa.Field(nullable=True)  # JAO's declared basis; see `is_hourly`
    is_hourly: Series[bool]  # Whether this element-direction's fmax actually moved over the day

    class Config:
        strict = False
        coerce = True


class Ratings(pa.DataFrameModel):
    """One row per (branch, hour): JAO's limits summed onto a branch of our network.

    `s_nom` is constant down a branch's rows — the branch's scalar rating, the largest hour —
    and `s_max_pu` derates it hour by hour, so the two multiply to the hour's limit. A branch
    whose `is_hourly` is False needs only the scalar: every `s_max_pu` on it is 1.

    `hour` is tz-aware UTC, as JAO publishes it. PyPSA snapshots are naive, meaning UTC, so
    whoever writes these onto a network drops the zone at that one point.
    """

    branch_type: Series[str]  # Line or Transformer
    branch_id: Series[str]  # The component's name in the network
    hour: Series[UtcTimestamp]
    s_nom: Series[float]  # The branch's scalar rating [MW]: its largest hourly limit
    s_max_pu: Series[float]  # The hour's limit as a fraction of `s_nom`, in (0, 1]
    is_hourly: Series[bool]  # Whether the branch's limit moved over the day
    elements: Series[int]  # JAO elements summed onto this branch

    class Config:
        strict = False
        coerce = True


class RatingComparison(pa.DataFrameModel):
    """One row per branch JAO rated: its rating against the one our network already carried."""

    branch_type: Series[str]
    branch_id: Series[str]
    v_nom: Series[float]  # Nominal voltage of the branch's buses [kV]
    jao_s_nom: Series[float]  # JAO's scalar rating [MW]
    our_s_nom: Series[float]  # The rating the network arrived with [MW]
    ratio: Series[float]  # jao_s_nom / our_s_nom
    flagged: Series[bool]  # Whether the two differ by more than `true_up.RATIO_FLAG`

    class Config:
        strict = False
        coerce = True


class RatingReport(pa.DataFrameModel):
    """One row per (branch type, voltage level): how far JAO's ratings sit from ours."""

    branch_type: Series[str]
    v_nom: Series[float]
    branches: Series[int]  # Branches JAO rated at this type and voltage
    median_ratio: Series[float]
    flagged: Series[int]  # Of those, how many differ by more than `true_up.RATIO_FLAG`

    class Config:
        strict = False
        coerce = True
