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

5. `"NA"` is a value in every text column: the feeds write the literal wherever a field
   does not apply. Left alone it is a substation called NA and a direction called NA, so
   it is blanked to `""` everywhere before anything reads a text column.

Non-physical rows — the ALEGrO external constraints and the equality constraints — carry
no element at all and are dropped before any grouping; they come back out of
`external_constraints`. What makes a row non-physical is the handbook's own definition —
the constraint names, and the absence of an element EIC — and nothing else: JAO publishes
real elements with real EICs, real limits and no location metadata at all, and classifying
by a missing field would file those as constraints.

Design: `wiki/specs/jao-grid.md`. Field meanings:
`wiki/literature/jao-core-publication-handbook.md`.
"""

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.jao import (
    ActiveConstraints,
    ActiveExternalConstraints,
    Contingencies,
    ConstraintContributions,
    ConstraintPtdfs,
    ElementEnds,
    Elements,
    ElementsWithPrices,
    ExternalConstraints,
    ExternalConstraintsWithPrices,
    ShadowPrices,
)
from coppersushi.market import CORE_ZONES

NON_PHYSICAL = ("External Constraint", "Equality Constraint")
POINT_TYPES = ("Transformer", "PST")  # elements at one substation, so `substation_from == substation_to`
PLACEHOLDER = "NA"  # what the domain feed writes where a row has no EIC, TSO or direction

KEYS = ["hour", "eic", "direction"]
CONSTRAINT_KEYS = ["hour", "name"]  # a constraint has no EIC, and only the price feed knows its direction
ACTIVE_KEYS = ["source_id"]
ACTIVE_PTDF_COLUMNS = ["source_id", "interval", "eic", "direction", "cont_name"]

# Text columns in which the feeds write `"NA"` for "does not apply".
PLACEHOLDER_COLUMNS = [
    "eic", "direction", "hub_from", "hub_to", "substation_from", "substation_to", "element_type",
]

END_COLUMNS = ["eic", "tso", "element_type", "substation_from", "substation_to"]

ELEMENT_COLUMNS = [
    "hour", "eic", "name", "tso", "direction", "hub_from", "hub_to",
    "substation_from", "substation_to", "element_type", "fmax_type",
    "u", "imax", "fmax", "frm", "fref", "ram",
    "contingency_count", "tso_disagreement",
]

# Both feeds' field names, mapped onto ours. The two pages never carry both spellings of
# a field, so one dict serves them both.
RENAME = {
    "id": "source_id",
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
    "ramMcp": "ram_mcp",
}

NAME_COLUMNS = [
    "name", "cont_name", "branch_name", "hub_from", "hub_to", "substation_from", "substation_to",
]


def blank_placeholder(values: pd.Series) -> pd.Series:
    """The feeds' `"NA"` placeholder and missing values, both as `""`."""
    return values.fillna("").astype(str).str.strip().replace(PLACEHOLDER, "")


def normalise_tso(tso: pd.Series) -> pd.Series:
    """Upper-case TSO codes, with the feeds' `"NA"` and missing values both as `""`."""
    return blank_placeholder(tso).str.upper()


def strip_names(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Strip surrounding whitespace from the named text columns, skipping absent ones.

    Nearly every `cneName` JAO publishes has a trailing space, and the same name is spelt
    with and without it across the two feeds, so nothing joins until this runs.
    """
    present = [column for column in columns if column in frame]
    return frame.assign(**{column: frame[column].str.strip() for column in present})


def _frame(rows: list[dict]) -> pd.DataFrame:
    """A feed's rows under our names: `hour` tz-aware, names stripped, `"NA"` blanked."""
    frame = pd.DataFrame(rows).rename(columns=RENAME)
    frame = frame.assign(hour=pd.to_datetime(frame.hour, utc=True, format="ISO8601"))
    frame = strip_names(frame, NAME_COLUMNS)
    present = [column for column in PLACEHOLDER_COLUMNS if column in frame]
    return frame.assign(**{column: blank_placeholder(frame[column]) for column in present})


def _is_non_physical(frame: pd.DataFrame) -> pd.Series:
    """The rows that describe a constraint rather than a network element.

    Two tells, and deliberately no more: the name's prefix, and no element EIC — the literal
    `"NA"` on the domain page, absent on the shadow-price page, `""` either way once `_frame`
    has blanked it. A missing `elementType` is *not* a tell. JAO publishes real elements whose
    location metadata is entirely absent — `St. Peter 2 - Salzburg 455`, a 220 kV APG line with
    an EIC and a real rating, but no type, hubs or substations — and reading absence as
    non-physical files those as constraints and drops them from the element table.
    """
    return (frame.name.str.startswith(NON_PHYSICAL) | frame.eic.eq("")).fillna(False).astype(bool)


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


def element_ends(rows: list[dict]) -> DataFrame[ElementEnds]:
    """Each TSO's own ends of every presolved physical element, one row per EIC and TSO.

    `elements` folds the TSOs of a shared element together, yet each TSO's DIRECT runs from
    its own `substation_from`: APG's and ČEPS's DIRECT rows on one tie-line carry PTDFs of
    opposite sign. Anything that wants to know which way a published row points needs the
    publishing TSO's own ends.
    """
    frame = _physical(_frame(rows))
    presolved = frame[frame.presolved]
    ends = (
        presolved.assign(tso=normalise_tso(presolved.tso))[END_COLUMNS]
        .drop_duplicates(ignore_index=True)
    )
    clashing = ends[ends.duplicated(["eic", "tso"], keep=False)]
    if not clashing.empty:
        names = ", ".join(sorted(set(clashing.eic)))
        raise ValueError(f"one TSO published more than one substation pair for: {names}")
    return ends.pipe(ElementEnds.validate)


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


def active_constraints(rows: list[dict]) -> DataFrame[ActiveConstraints]:
    """The physical rows of JAO's post-auction active flow-based publication.

    An element and direction can bind under more than one contingency in the same
    interval, so the contingency is part of the key. Collapsing to the element grain
    would discard a distinct market constraint and its own PTDF vector.
    """
    frame = _physical(_frame(rows)).rename(columns={"hour": "interval"})
    frame = frame.assign(tso=normalise_tso(frame.tso))
    columns = [
        "source_id", "interval", "eic", "name", "tso", "direction", "cont_name", "branch_eic",
        "hub_from", "hub_to", "shadow_price", "ram", "ram_mcp",
    ]
    active = frame[columns].reset_index(drop=True)
    repeated = active[active.duplicated(ACTIVE_KEYS, keep=False)]
    if not repeated.empty:
        names = ", ".join(sorted(set(repeated.name)))
        raise ValueError(f"repeated active flow-based row identifiers for: {names}")
    return active.pipe(ActiveConstraints.validate)


def constraint_ptdfs(rows: list[dict]) -> DataFrame[ConstraintPtdfs]:
    """Every physical active flow-based row's PTDF vector, in long Core-zone form."""
    frame = _physical(_frame(rows)).rename(columns={"hour": "interval"})
    hub_columns = {f"hub_{zone}": zone for zone in CORE_ZONES}
    missing = sorted(set(hub_columns) - set(frame.columns))
    if missing:
        raise ValueError(f"active flow-based response is missing Core PTDF columns: {missing}")
    ptdfs = frame[ACTIVE_PTDF_COLUMNS + list(hub_columns)].melt(
        id_vars=ACTIVE_PTDF_COLUMNS,
        value_vars=list(hub_columns),
        var_name="hub_column",
        value_name="ptdf",
    )
    ptdfs = ptdfs.assign(zone=ptdfs.hub_column.map(hub_columns)).drop(columns="hub_column")
    return ptdfs.sort_values(["interval", "source_id", "zone"], ignore_index=True).pipe(ConstraintPtdfs.validate)


def active_external_constraints(rows: list[dict]) -> DataFrame[ActiveExternalConstraints]:
    """Active flow-based rows with no physical element, retained for a completeness count."""
    frame = _frame(rows)
    frame = frame[_is_non_physical(frame)].rename(columns={"hour": "interval"})
    frame = frame.assign(tso=normalise_tso(frame.tso))
    columns = ["interval", "name", "tso", "direction", "shadow_price", "ram", "ram_mcp"]
    return frame[columns].reset_index(drop=True).pipe(ActiveExternalConstraints.validate)


def price_contributions(
    constraint: pd.Series,
    ptdfs: DataFrame[ConstraintPtdfs],
    reference_zone: str,
) -> DataFrame[ConstraintContributions]:
    """A binding row's zonal price contribution relative to ``reference_zone``.

    EUPHEMIA's congestion duals do not contain the common energy-price component.
    The selected row therefore explains only relative prices:
    ``-shadow_price * (PTDF_z - PTDF_reference)``.
    """
    if reference_zone not in CORE_ZONES:
        raise ValueError(f"reference zone must be one of {CORE_ZONES}: {reference_zone}")
    selected = ptdfs
    for key in ACTIVE_KEYS:
        selected = selected[selected[key].eq(constraint[key])]
    if len(selected) != len(CORE_ZONES):
        raise ValueError(f"selected constraint has {len(selected)} PTDFs, expected {len(CORE_ZONES)}")
    reference = selected.loc[selected.zone.eq(reference_zone), "ptdf"]
    if len(reference) != 1:
        raise ValueError(f"selected constraint has {len(reference)} PTDFs for {reference_zone}")
    difference = selected.ptdf - reference.iloc[0]
    return (
        selected.assign(
            reference_zone=reference_zone,
            ptdf_difference=difference,
            contribution=-float(constraint.shadow_price) * difference,
        )
        .reset_index(drop=True)
        .pipe(ConstraintContributions.validate)
    )


def external_constraints(rows: list[dict]) -> DataFrame[ExternalConstraints]:
    """The non-physical rows of either feed — the ALEGrO external and equality constraints.

    The domain feed writes a constraint once per contingency it was assessed under (as of
    2026-09), the limit the same on each row and the margin per contingency, so one row per
    hour and constraint keeps the tightest margin. The price feed names a constraint once per
    binding; its rows pass through so that `with_constraint_prices` still sees a repeated price.
    """
    frame = _frame(rows)
    frame = frame[_is_non_physical(frame)]
    frame = frame.assign(tso=normalise_tso(frame.tso))
    wanted = ["hour", "name", "tso", "direction", "fmax", "ram", "shadow_price"]
    frame = frame[[column for column in wanted if column in frame]]
    if "shadow_price" not in frame:
        frame = frame.groupby(
            CONSTRAINT_KEYS + ["tso", "direction"], as_index=False, dropna=False, sort=False
        ).agg(fmax=("fmax", "min"), ram=("ram", "min"))
    return frame.reset_index(drop=True).pipe(ExternalConstraints.validate)


def with_shadow_prices(
    elements: DataFrame[Elements], prices: DataFrame[ShadowPrices]
) -> DataFrame[ElementsWithPrices]:
    """`elements` plus the price of each binding one, NaN where it did not bind.

    Prices outside the elements' hours are irrelevant, not suspicious; a price *within*
    them that names no element is: it would mean the presolved set we built the map from
    is not the set the market cleared against, so it raises rather than dropping.
    """
    prices = prices[prices.hour.isin(elements.hour)]
    repeated = prices[prices.duplicated(subset=KEYS, keep=False)]
    if not repeated.empty:
        names = ", ".join(sorted(set(repeated.eic.astype(str))))
        raise ValueError(f"several shadow prices for one element, hour and direction: {names}")
    matched = prices.merge(elements[KEYS], on=KEYS, how="left", indicator=True)
    missing = matched[matched._merge == "left_only"]
    if not missing.empty:
        names = ", ".join(sorted(set(missing.eic.astype(str))))
        raise ValueError(f"shadow prices for elements absent from the presolved set: {names}")
    priced = prices[KEYS + ["shadow_price", "cont_name"]].rename(columns={"cont_name": "binding_contingency"})
    return elements.merge(priced, on=KEYS, how="left", validate="one_to_one").pipe(ElementsWithPrices.validate)


def with_constraint_prices(
    constraints: DataFrame[ExternalConstraints], prices: DataFrame[ExternalConstraints]
) -> DataFrame[ExternalConstraintsWithPrices]:
    """The hourly external constraints, each carrying the price it bound at, NaN where it did not.

    The two feeds describe these on different grains: the domain feed publishes every
    constraint's limit every hour, the price feed only the ones that bound. Keeping both as rows
    would put a constraint that bound on two of them, one with the limit and one with the price.

    The join is on the hour and the name alone. The domain feed writes `"NA"` for a constraint's
    direction, so only the price feed knows which sense bound, and that comes across beside the
    price rather than overwriting the blank.
    """
    prices = prices[prices.hour.isin(constraints.hour)]
    repeated = prices[prices.duplicated(subset=CONSTRAINT_KEYS, keep=False)]
    if not repeated.empty:
        names = ", ".join(sorted(set(repeated.name)))
        raise ValueError(f"several prices for one constraint and hour: {names}")
    matched = prices.merge(constraints[CONSTRAINT_KEYS], on=CONSTRAINT_KEYS, how="left", indicator=True)
    missing = matched[matched._merge == "left_only"]
    if not missing.empty:
        names = ", ".join(sorted(set(missing.name)))
        raise ValueError(f"prices for constraints the domain feed never published: {names}")
    priced = prices[CONSTRAINT_KEYS + ["shadow_price", "direction"]].rename(
        columns={"direction": "binding_direction"}
    )
    return (
        constraints.merge(priced, on=CONSTRAINT_KEYS, how="left", validate="one_to_one")
        .pipe(ExternalConstraintsWithPrices.validate)
    )
