"""JAO's Core publication feeds, turned into tidy element tables.

The domain feed (`finalComputation`) and the shadow-price feed describe the same objects
with four quirks that every consumer would otherwise re-discover:

1. The feeds disagree on field names — `cneName`/`cneEic` on the domain page,
   `cnecName`/`cnecEic` on the shadow-price page — and on TSO casing (`TENNETGMBH`
   against `TennetGmbh`).
2. `contName` is free text whose format is the TSO's own; the structured `contingencies`
   list, one entry per outaged branch, is the field to read.
3. The EIC identifies the *element*, not the row: an element appears once per contingency
   it is monitored against, so a row is not a CNEC and the grain is
   (hour, element, direction).
4. Where two TSOs monitor one element they may publish different `fmax`. The market is
   held by the tighter rating, so that is the one kept, and the disagreement is recorded.

Non-physical rows — the ALEGrO external constraints and the equality constraints — carry
no element at all and are dropped before any grouping; they come back out of
`external_constraints`.

Design: `wiki/specs/jao-grid.md`. Field meanings:
`wiki/literature/jao-core-publication-handbook.md`.
"""

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.jao import (
    Contingencies,
    Elements,
    ElementsWithPrices,
    ExternalConstraints,
    ShadowPrices,
)

NON_PHYSICAL = ("External Constraint", "Equality Constraint")
POINT_TYPES = ("Transformer", "PST")  # elements at one substation, so `substation_from == substation_to`
PLACEHOLDER = "NA"  # what the domain feed writes where a row has no EIC, TSO or direction

KEYS = ["hour", "eic", "direction"]

ELEMENT_COLUMNS = [
    "hour", "eic", "name", "tso", "direction", "hub_from", "hub_to",
    "substation_from", "substation_to", "element_type", "fmax_type",
    "u", "imax", "fmax", "frm", "fref", "ram",
    "contingency_count", "tso_disagreement",
]

# Both feeds' field names, mapped onto ours. The two pages never carry both spellings of
# a field, so one dict serves them both.
RENAME = {
    "dateTimeUtc": "hour",
    "cneEic": "eic",
    "cnecEic": "eic",
    "cneName": "name",
    "cnecName": "name",
    "contName": "cont_name",
    "branchEic": "branch_eic",
    "branchName": "branch_name",
    "hubFrom": "hub_from",
    "hubTo": "hub_to",
    "substationFrom": "substation_from",
    "substationTo": "substation_to",
    "elementType": "element_type",
    "fmaxType": "fmax_type",
    "shadowPrice": "shadow_price",
}

NAME_COLUMNS = [
    "name", "cont_name", "branch_name", "hub_from", "hub_to", "substation_from", "substation_to",
]


def normalise_tso(tso: pd.Series) -> pd.Series:
    """Upper-case TSO codes, with the feeds' `"NA"` and missing values both as `""`."""
    return tso.fillna("").astype(str).str.strip().str.upper().replace(PLACEHOLDER, "")


def strip_names(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Strip surrounding whitespace from the named text columns, skipping absent ones.

    Nearly every `cneName` JAO publishes has a trailing space, and the same name is spelt
    with and without it across the two feeds, so nothing joins until this runs.
    """
    present = [column for column in columns if column in frame]
    return frame.assign(**{column: frame[column].str.strip() for column in present})


def _frame(rows: list[dict]) -> pd.DataFrame:
    """A feed's rows under our names, with `hour` tz-aware and every name stripped."""
    frame = pd.DataFrame(rows).rename(columns=RENAME)
    frame = frame.assign(hour=pd.to_datetime(frame.hour, utc=True, format="ISO8601"))
    return strip_names(frame, NAME_COLUMNS)


def _is_non_physical(frame: pd.DataFrame) -> pd.Series:
    """The rows that describe a constraint rather than a network element.

    Three independent tells, because no single one holds in both feeds: the name's prefix,
    an EIC that is the literal `"NA"` (domain feed) or absent (shadow-price feed), and a
    missing element type.
    """
    tells = frame.name.str.startswith(NON_PHYSICAL) | frame.eic.isna() | frame.eic.eq(PLACEHOLDER)
    if "element_type" in frame:
        tells |= frame.element_type.isna()
    return tells.fillna(False).astype(bool)


def _physical(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[~_is_non_physical(frame)]


def _check_one_fmax_per_tso(frame: pd.DataFrame) -> None:
    """Raise unless every element whose `fmax` varies has two TSOs behind the variation.

    Differing ratings from two operators is the known quirk; differing ratings from one is
    a feed we do not understand, and quietly taking the minimum would hide it.
    """
    grouped = frame.groupby(KEYS)
    inconsistent = frame[(grouped.fmax.transform("nunique") > 1) & (grouped.tso.transform("nunique") < 2)]
    if not inconsistent.empty:
        names = ", ".join(sorted(set(inconsistent.eic.astype(str))))
        raise ValueError(f"one TSO published differing fmax for: {names}")


def elements(rows: list[dict]) -> DataFrame[Elements]:
    """The presolved physical elements of a domain feed, one row per hour, EIC and direction."""
    frame = _physical(_frame(rows))
    frame = frame[frame.presolved]
    frame = frame.assign(tso=normalise_tso(frame.tso))
    _check_one_fmax_per_tso(frame)
    grouped = frame.groupby(KEYS, as_index=False)
    aggregated = set(KEYS) | {"fmax", "ram", "contingency_count", "tso_disagreement"}
    firsts = {column: (column, "first") for column in ELEMENT_COLUMNS if column in frame and column not in aggregated}
    return (
        grouped.agg(
            **firsts,
            fmax=("fmax", "min"),  # the tighter of two TSOs' ratings is what binds the market
            ram=("ram", "min"),
            contingency_count=("fmax", "size"),
            tso_disagreement=("fmax", lambda ratings: ratings.nunique() > 1),
        )[ELEMENT_COLUMNS]
        .pipe(Elements.validate)
    )


def contingencies(rows: list[dict]) -> DataFrame[Contingencies]:
    """One row per outaged branch of every contingency behind a presolved element."""
    frame = _physical(_frame(rows))
    frame = frame[frame.presolved]
    exploded = frame[KEYS + ["cont_name", "contingencies"]].explode("contingencies").reset_index(drop=True)
    branches = strip_names(pd.DataFrame(list(exploded.contingencies)).rename(columns=RENAME), NAME_COLUMNS)
    branch_columns = ["branch_eic", "branch_name", "substation_from", "substation_to", "element_type"]
    return pd.concat(
        [exploded.drop(columns="contingencies"), branches[branch_columns]], axis="columns"
    ).pipe(Contingencies.validate)


def shadow_prices(rows: list[dict]) -> DataFrame[ShadowPrices]:
    """The physical rows of the shadow-price feed, on the same grain as `elements`."""
    frame = _physical(_frame(rows))
    frame = frame.assign(tso=normalise_tso(frame.tso))
    columns = ["hour", "eic", "name", "tso", "direction", "cont_name", "shadow_price", "ram", "fmax"]
    return frame[columns].reset_index(drop=True).pipe(ShadowPrices.validate)


def external_constraints(rows: list[dict]) -> DataFrame[ExternalConstraints]:
    """The non-physical rows of either feed — the ALEGrO external and equality constraints."""
    frame = _frame(rows)
    frame = frame[_is_non_physical(frame)]
    frame = frame.assign(tso=normalise_tso(frame.tso))
    wanted = ["hour", "name", "tso", "direction", "fmax", "ram", "shadow_price"]
    columns = [column for column in wanted if column in frame]
    return frame[columns].reset_index(drop=True).pipe(ExternalConstraints.validate)


def with_shadow_prices(elements: pd.DataFrame, prices: pd.DataFrame) -> DataFrame[ElementsWithPrices]:
    """`elements` plus the price of each binding one, NaN where it did not bind.

    Prices outside the elements' hours are irrelevant, not suspicious; a price *within*
    them that names no element is: it would mean the presolved set we built the map from
    is not the set the market cleared against, so it raises rather than dropping.
    """
    prices = prices[prices.hour.isin(elements.hour)]
    matched = prices.merge(elements[KEYS], on=KEYS, how="left", indicator=True)
    missing = matched[matched._merge == "left_only"]
    if not missing.empty:
        names = ", ".join(sorted(set(missing.eic.astype(str))))
        raise ValueError(f"shadow prices for elements absent from the presolved set: {names}")
    priced = prices[KEYS + ["shadow_price", "cont_name"]].rename(columns={"cont_name": "binding_contingency"})
    return elements.merge(priced, on=KEYS, how="left", validate="one_to_one").pipe(ElementsWithPrices.validate)
