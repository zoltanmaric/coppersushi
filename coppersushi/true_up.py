"""JAO's published limits, written onto the branches of our network as ratings.

JAO publishes, for every hour it presolved, the maximum flow `fmax` it allowed each monitored
element in each direction. `elements.py` has already said which branch of our network each
element is. What is left is arithmetic, and four things about the feed shape it — each measured
against the elements of one real day, the measurements themselves recorded in the PR body
because JAO's terms forbid redistributing them:

1. **`(eic, direction, hour)` keys the limit.** No element-direction carries two `fmax` inside
   one hour; a multi-branch contingency does not split it. `cnecs.elements` already collapses
   to that grain and raises if one TSO published two ratings, so the dedupe here is only a
   guard for limits arriving another way, and it keeps the tighter value.

2. **`fmax_type` does not say whether a limit is constant — the data does.** The column takes
   three values, not two, and the declared type predicts almost nothing: over the day's hours
   `fmax` moved for most `DYNAMIC` element-directions, for a fifth of the `SEASONAL` ones, and
   for two declared `FIXED` — one German 380 kV line labelled `FIXED` took seven distinct values
   spanning 210 MW. So `is_hourly` is `nunique() > 1` over the day, never the label: trusting it
   would have written that line a scalar rating and thrown the swing away.

3. **Several elements fold onto one branch.** Our network folds a corridor's parallel circuits
   into a single component, so the branch's rating is the sum of its elements' `fmax`, taken
   after rule 1's dedupe. The two directions are then collapsed by taking the tighter: PyPSA's
   `s_nom` bounds the magnitude of the flow, so it is the smaller of the two that binds.

4. **`frm` is not written.** JAO's flow reliability margin is what it holds back inside its own
   calculation, a parameter of the security constraint rather than part of a branch's physical
   rating. `comparison` leaves our own `s_max_pu` headroom out for the same reason: it compares
   physical rating with physical rating.

Design: `wiki/specs/jao-grid.md`.
"""

import logging

import numpy as np
import pandas as pd
import pypsa
from pandera.typing import DataFrame

from coppersushi.data_model.elements import ElementMatches
from coppersushi.data_model.jao import Elements
from coppersushi.data_model.true_up import Limits, RatingComparison, RatingReport, Ratings
from coppersushi.elements import MATCHED, bus_voltage

logger = logging.getLogger(__name__)

RATIO_FLAG = 2.0  # a branch whose two ratings differ by more than this factor is reported

LIMIT_KEYS = ["eic", "direction", "hour"]
BRANCH_KEYS = ["branch_type", "branch_id"]

LIMIT_COLUMNS = LIMIT_KEYS + ["fmax", "fmax_type", "is_hourly"]
RATING_COLUMNS = BRANCH_KEYS + ["hour", "s_nom", "s_max_pu", "is_hourly", "elements"]
COMPARISON_COLUMNS = BRANCH_KEYS + ["v_nom", "jao_s_nom", "our_s_nom", "ratio", "flagged"]
REPORT_COLUMNS = ["branch_type", "v_nom", "branches", "median_ratio", "flagged"]


def limits(elements: DataFrame[Elements]) -> DataFrame[Limits]:
    """JAO's `fmax` on its own grain, each element-direction told constant or hourly.

    `is_hourly` is measured over whatever span `elements` covers — a day, in practice — and
    never read from `fmax_type`, which does not predict it (rule 2).
    """
    deduped = elements.groupby(LIMIT_KEYS, as_index=False).agg(
        fmax=("fmax", "min"),  # the tighter rating is the one that bound the market
        fmax_type=("fmax_type", "first"),
    )
    moved = deduped.groupby(["eic", "direction"]).fmax.transform("nunique") > 1
    limited = deduped.assign(is_hourly=moved)[LIMIT_COLUMNS].sort_values(LIMIT_KEYS, ignore_index=True)
    logger.info(
        "%d of %d element-directions have an hourly limit",
        limited[limited.is_hourly].groupby(["eic", "direction"]).ngroups,
        limited.groupby(["eic", "direction"]).ngroups,
    )
    return limited.pipe(Limits.validate)


def ratings(limits: DataFrame[Limits], matches: DataFrame[ElementMatches]) -> DataFrame[Ratings]:
    """One row per (branch, hour): the elements JAO monitored there, summed onto our branch.

    Elements that reached no branch are dropped — they have nothing to be written onto — so the
    coverage denominator stays in `matches`, where `elements.coverage` reads it.
    """
    resolved = matches[matches.match_status == MATCHED][["eic"] + BRANCH_KEYS]
    joined = limits.merge(resolved, on="eic", how="inner")
    if joined.empty:
        empty = pd.DataFrame(columns=RATING_COLUMNS).assign(hour=pd.to_datetime([], utc=True))
        return empty.pipe(Ratings.validate)

    per_direction = joined.groupby(BRANCH_KEYS + ["direction", "hour"], as_index=False).agg(
        fmax=("fmax", "sum"),  # parallel circuits of one corridor, folded onto one component
        elements=("eic", "nunique"),
    )
    per_hour = per_direction.groupby(BRANCH_KEYS + ["hour"], as_index=False).agg(
        fmax=("fmax", "min"),  # `s_nom` bounds the magnitude, so the tighter direction binds
        elements=("elements", "max"),
    )
    scalar = per_hour.groupby(BRANCH_KEYS).fmax.agg(s_nom="max", distinct="nunique")
    rated = per_hour.join(scalar, on=BRANCH_KEYS)
    rated["s_max_pu"] = np.where(rated.s_nom > 0, rated.fmax / rated.s_nom, 1.0)
    rated["is_hourly"] = rated.distinct > 1
    return (
        rated[RATING_COLUMNS]
        .sort_values(BRANCH_KEYS + ["hour"], ignore_index=True)
        .pipe(Ratings.validate)
    )


def _branch_voltages(n: pypsa.Network) -> pd.DataFrame:
    """Every branch's type, name, own rating and voltage level.

    The voltage is the higher of its two bus-name suffixes, as in `elements.py`: an upstream
    simplification currently sets every `v_nom` to 380 while the suffix still carries the true
    voltage, and `v_nom` is the fallback where a bus is named some other way.
    """
    rows = []
    for branch_type, static in (("Line", n.lines), ("Transformer", n.transformers)):
        for branch_id, branch in static.iterrows():
            suffixes = [bus_voltage(branch.bus0), bus_voltage(branch.bus1)]
            fallback = max(n.buses.v_nom[branch.bus0], n.buses.v_nom[branch.bus1])
            rows.append(
                {
                    "branch_type": branch_type,
                    "branch_id": branch_id,
                    "v_nom": float(max(suffixes)) if max(suffixes) > 0 else float(fallback),
                    "our_s_nom": float(branch.s_nom),
                }
            )
    return pd.DataFrame(rows, columns=BRANCH_KEYS + ["v_nom", "our_s_nom"])


def comparison(ratings: DataFrame[Ratings], n: pypsa.Network) -> DataFrame[RatingComparison]:
    """One row per rated branch: JAO's scalar rating against the one the network arrived with.

    Both sides are physical ratings, with neither party's headroom taken off — JAO's `frm` nor
    our `s_max_pu` — so the ratio measures the two ratings and nothing else.
    """
    jao = ratings.groupby(BRANCH_KEYS, as_index=False).s_nom.max().rename(columns={"s_nom": "jao_s_nom"})
    compared = jao.merge(_branch_voltages(n), on=BRANCH_KEYS, how="inner")
    compared["ratio"] = np.where(compared.our_s_nom > 0, compared.jao_s_nom / compared.our_s_nom, np.inf)
    compared["flagged"] = (compared.ratio > RATIO_FLAG) | (compared.ratio < 1 / RATIO_FLAG)
    return (
        compared[COMPARISON_COLUMNS]
        .sort_values(BRANCH_KEYS, ignore_index=True)
        .pipe(RatingComparison.validate)
    )


def report(comparison: DataFrame[RatingComparison]) -> DataFrame[RatingReport]:
    """The comparison summarised per voltage level, lines and transformers kept apart."""
    if comparison.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS).pipe(RatingReport.validate)
    summarised = comparison.groupby(["branch_type", "v_nom"], as_index=False).agg(
        branches=("branch_id", "size"),
        median_ratio=("ratio", "median"),
        flagged=("flagged", "sum"),
    )
    return summarised[REPORT_COLUMNS].sort_values(["branch_type", "v_nom"], ignore_index=True).pipe(RatingReport.validate)
