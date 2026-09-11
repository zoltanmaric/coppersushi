"""Turning a JAO element into the branch of our network that it is.

`substations.py` resolved JAO's substation *names* to buses. A JAO element is named by its two
ends — "a 380 kV line from AVELGEM to HORTA" — so what is left is to find the `Line` or
`Transformer` joining those two sites. Five things about JAO's tables shape how that is done,
each measured against the elements of one real day:

1. **The element's identity is its EIC alone**, not the (EIC, direction, hour) triple the domain
   feed is published on. That triple keys the *measurement* — what the limit was, in which flow
   direction, in which hour; the component does not change through the day. 105 of that day's 106
   EICs carry a single substation pair across all 24 hours, and every row has an EIC, so this
   table has one row per EIC and the hourly limits join onto it.
2. **The substation pair is unordered.** The one EIC that moved was a tie-line published as both
   `Etzenricht → Hradec` and `Hradec → Etzenricht`. Grouping on the EIC is what keeps that one
   element, so within a group the first row simply speaks for it — its name, its pair, and the
   first voltage any row states. One rule, applied to all three.
3. **`TieLine` and `Line` resolve identically** — a tie-line is an ordinary line that happens to
   cross a border. Only `cnecs.POINT_TYPES` sit inside a single substation and take the
   transformer path. Rows whose `element_type` JAO left empty are lines: they name two ends, and
   dropping them lost real monitored circuits once already.
4. **Where a substation pair carries several branches, the element's voltage picks one, read from
   the bus-name suffix** rather than from `v_nom`. Our buses are `<osm id>-<voltage>`, and an
   upstream simplification currently sets every `v_nom` to 380 while the suffix still carries the
   true voltage. Reading the suffix first is correct either side of that being fixed. `v_nom`
   breaks the remaining ties, and the branch id breaks the rest, so a tie is never an error: PR 6
   sums the limits of every element that folds onto one branch.
5. **Nothing is dropped.** An element that reaches no branch keeps its row with `match_status`
   saying how far it got, because coverage needs the denominator and the three ways of failing
   want telling apart. The matching outcome is reported first: `no_component_in_network` is a
   missing *component class* (the network has no transformers at all, which is being fixed
   elsewhere) and is only claimed once the substations themselves resolved, or every transformer
   element would read as a precondition whether or not its ends were ever found.

`bus_source` records the one geographic guess in the chain. An element's ends are looked for at
exactly the matched substation first; only if no branch joins those buses is the search widened
to every bus within `MAX_BUS_DISTANCE_KM`, and a row found that way says `nearest`, so a report
can say how much of the coverage leant on it. The widening never crosses into a substation that
some *other* JAO name matched: those are named sites, and a guess that lands on one is not a
guess about an unnamed neighbour but a corridor stolen from another element.

Design: `wiki/specs/jao-grid.md`.
"""

import logging

import numpy as np
import pandas as pd
import pypsa
import pyproj
from pandera.typing import DataFrame

from coppersushi import substations
from coppersushi.cnecs import POINT_TYPES
from coppersushi.data_model.elements import ContingencyMatches, ElementMatches, Overrides
from coppersushi.data_model.jao import Contingencies, Elements
from coppersushi.data_model.substations import Matches

logger = logging.getLogger(__name__)

MAX_BUS_DISTANCE_KM = 15.0

LINE = "Line"
TRANSFORMER = "Transformer"

MATCHED = "matched"
NO_SUBSTATION = "no_substation"
NO_BRANCH = "no_branch"
NO_COMPONENT = "no_component_in_network"

EXACT = "exact"
NEAREST = "nearest"

ELEMENT_COLUMNS = [
    "eic", "name", "element_type", "branch_id", "branch_type",
    "bus0", "bus1", "match_status", "bus_source", "score",
]
CONTINGENCY_COLUMNS = [
    "eic", "cont_name", "branch_name", "branch_id", "branch_type",
    "bus0", "bus1", "match_status", "bus_source", "circuits_out", "score",
]
CONTINGENCY_KEYS = ["eic", "cont_name", "branch_eic", "branch_name", "substation_from", "substation_to"]

geodesic = pyproj.Geod(ellps="WGS84")


def _bus_table(n: pypsa.Network) -> pd.DataFrame:
    """Every bus with the two things this module reads it for: its site, and its voltage."""
    buses = n.buses[["x", "y", "v_nom"]].copy()
    buses["substation"] = [substations.osm_id(bus_id) for bus_id in buses.index]
    buses["voltage"] = [substations.voltage(bus_id) for bus_id in buses.index]
    return buses


def _at(buses: pd.DataFrame, osm_id: str) -> set[str]:
    """The buses of one substation — every voltage level of it."""
    return set(buses.index[buses.substation == osm_id])


def _near(buses: pd.DataFrame, bus_id: str, claimed: set[str]) -> set[str]:
    """The buses within `MAX_BUS_DISTANCE_KM` of one bus, itself included.

    Buses of a substation in `claimed` — one that a different JAO name matched — are left out:
    reaching one of those is not a guess about an unnamed neighbour, it is another element's site.
    """
    origin = buses.loc[bus_id]
    _, _, metres = geodesic.inv(
        np.full(len(buses), origin.x), np.full(len(buses), origin.y), buses.x.values, buses.y.values
    )
    nearby = buses.index[metres <= MAX_BUS_DISTANCE_KM * 1000]
    return set(nearby[~buses.substation[nearby].isin(claimed)])


def _between(branches: pd.DataFrame, ends0: set[str], ends1: set[str]) -> pd.DataFrame:
    """The branches joining the two sets of buses, in either orientation."""
    forward = branches.bus0.isin(ends0) & branches.bus1.isin(ends1)
    backward = branches.bus0.isin(ends1) & branches.bus1.isin(ends0)
    return branches[forward | backward]


def _pick(candidates: pd.DataFrame, buses: pd.DataFrame, u: float) -> str:
    """The one branch an element means, chosen on the voltage its ends are named at.

    Ranked on how many of the branch's two bus names end in the element's voltage, then on how
    far the buses' `v_nom` is from it, then on the branch id so that a genuine tie — parallel
    circuits our network has not folded — resolves to the same branch every run.
    """

    def rank(branch_id: str) -> tuple[int, float, str]:
        ends = [candidates.bus0[branch_id], candidates.bus1[branch_id]]
        if pd.isna(u):
            return (0, 0.0, branch_id)
        suffix_hits = sum(buses.voltage[bus] == u for bus in ends)
        v_nom_gap = min(abs(buses.v_nom[bus] - u) for bus in ends)
        return (-suffix_hits, v_nom_gap, branch_id)

    return min(candidates.index, key=rank)


def _search(
    branches: pd.DataFrame,
    buses: pd.DataFrame,
    ends: list[tuple[set[str], str]],
    u: float,
    claimed: set[str],
):
    """A branch between the two ends, widening to nearby buses only if the sites carry none.

    `claimed` is the substations other JAO names matched, which the widening refuses to enter.
    Returns `(branch_id, bus_source)`, or `(None, "")` where even the widened search found none.
    """
    exact = [site for site, _ in ends]
    found = _between(branches, *exact)
    if not found.empty:
        return _pick(found, buses, u), EXACT
    widened = [site | _near(buses, bus_id, claimed) for site, bus_id in ends]
    found = _between(branches, *widened)
    if found.empty:
        return None, ""
    return _pick(found, buses, u), NEAREST


def _resolve(
    branch_type: str,
    sites: list[str],
    u: float,
    buses: pd.DataFrame,
    branches: dict[str, pd.DataFrame],
    matches: pd.DataFrame,
) -> dict:
    """One element or outaged branch, resolved to a component of the network or to why it wasn't.

    `sites` is the element's JAO substation names, one for a transformer or PST and two for a
    line. The matching outcome is reported first and `no_component_in_network` — the network
    having no such component class at all, which is a precondition rather than a match that
    failed — only once the substations did resolve, so that a coverage measurement never counts
    a genuine miss as a known gap.
    """
    blank = {"branch_id": None, "bus0": None, "bus1": None, "bus_source": "", "score": 0.0}
    wanted = 1 if branch_type == TRANSFORMER else 2
    known = [matches.loc[site] for site in sites if site in matches.index]
    resolved = [match for match in known if pd.notna(match.bus_id)]
    if len(sites) != wanted or len(resolved) != wanted:
        return blank | {"match_status": NO_SUBSTATION}

    score = float(min(match.score for match in resolved))
    if branches[branch_type].empty:
        return blank | {"match_status": NO_COMPONENT, "score": score}

    own = {match.osm_id for match in resolved}
    claimed = set(matches.osm_id.dropna()) - own
    ends = [(_at(buses, match.osm_id), match.bus_id) for match in resolved]
    if wanted == 1:
        ends = ends * 2  # a transformer joins two voltage levels of the one site
    branch_id, bus_source = _search(branches[branch_type], buses, ends, u, claimed)
    if branch_id is None:
        return blank | {"match_status": NO_BRANCH, "score": score}
    branch = branches[branch_type].loc[branch_id]
    return {
        "branch_id": branch_id,
        "bus0": branch.bus0,
        "bus1": branch.bus1,
        "match_status": MATCHED,
        "bus_source": bus_source,
        "score": score,
    }


def _sites(substation_from: str, substation_to: str) -> list[str]:
    """The substation names one row is published between, sorted: the pair is unordered.

    One name where both ends are the same site, which is how a transformer or PST is published.
    """
    return sorted({substation_from, substation_to} - {"", None})


def _forced(overrides: DataFrame[Overrides] | None, branches: dict[str, pd.DataFrame]) -> dict[str, dict]:
    """The overrides as resolutions, refusing any that names a branch the network hasn't got.

    `branch_type` travels with the resolution: an override exists precisely to correct a
    mis-typed element, and a `Line` id filed under `Transformer` would be looked up in the wrong
    table for ever after.
    """
    if overrides is None:
        return {}
    forced = {}
    for row in overrides.itertuples():
        table = branches.get(row.branch_type, pd.DataFrame())
        if row.branch_id not in table.index:
            raise ValueError(
                f"override for {row.eic} names {row.branch_type} {row.branch_id!r}, absent from the network"
            )
        branch = table.loc[row.branch_id]
        forced[row.eic] = {
            "branch_id": row.branch_id,
            "bus0": branch.bus0,
            "bus1": branch.bus1,
            "branch_type": row.branch_type,
            "match_status": MATCHED,
            "bus_source": EXACT,
            "score": 1.0,
        }
    return forced


def _branch_tables(n: pypsa.Network) -> dict[str, pd.DataFrame]:
    return {LINE: n.lines[["bus0", "bus1"]], TRANSFORMER: n.transformers[["bus0", "bus1"]]}


def branch_for(
    elements: DataFrame[Elements],
    matches: DataFrame[Matches],
    n: pypsa.Network,
    overrides: DataFrame[Overrides] | None = None,
) -> DataFrame[ElementMatches]:
    """One row per element EIC, carrying the branch of `n` that element is.

    `elements` arrives on JAO's own grain, one row per hour, EIC and direction; the component is
    the same on all of them, so they are collapsed to one row and the hourly limits join back on
    the EIC. Within a group the first row speaks for the element — its name and its substation
    pair — while its type and voltage are the first any row states, 105 of one real day's 106
    EICs carrying a single pair across all 24 hours.
    """
    buses = _bus_table(n)
    branches = _branch_tables(n)
    by_name = matches.set_index("jao_name")
    forced = _forced(overrides, branches)

    rows = []
    for eic, group in elements.groupby("eic", sort=True):
        element_type = next((value for value in group.element_type if value), "")
        branch_type = TRANSFORMER if element_type in POINT_TYPES else LINE
        first = group.iloc[0]
        voltages = group.u.dropna()
        resolution = forced.get(eic) or _resolve(
            branch_type,
            _sites(first.substation_from, first.substation_to),
            voltages.iloc[0] if len(voltages) else np.nan,
            buses,
            branches,
            by_name,
        )
        rows.append(
            {
                "eic": eic,
                "name": first["name"],
                "element_type": element_type,
                "branch_type": branch_type,
                **resolution,
            }
        )
    resolved = pd.DataFrame(rows, columns=ELEMENT_COLUMNS)
    logger.info("%d of %d elements resolved to a branch", (resolved.match_status == MATCHED).sum(), len(resolved))
    return resolved.pipe(ElementMatches.validate)


def contingencies_for(
    contingencies: DataFrame[Contingencies], matches: DataFrame[Matches], n: pypsa.Network
) -> DataFrame[ContingencyMatches]:
    """One row per (monitored element, contingency, branch of ours), with the circuits it takes out.

    The contingency lists repeat every hour and carry no voltage, so they are made distinct first
    and resolved on the substation pair alone. Several of JAO's branches folding onto one branch
    of ours is the normal case — parallel circuits of a corridor — and `circuits_out` counts them,
    because two circuits of three out is a reactance change and not an outage.
    """
    buses = _bus_table(n)
    branches = _branch_tables(n)
    by_name = matches.set_index("jao_name")

    distinct = contingencies.assign(
        element_type=contingencies.element_type.fillna(""),
        substation_from=contingencies.substation_from.fillna(""),
        substation_to=contingencies.substation_to.fillna(""),
        branch_name=contingencies.branch_name.fillna(""),
        branch_eic=contingencies.branch_eic.fillna(""),
        cont_name=contingencies.cont_name.fillna(""),
    ).drop_duplicates(subset=CONTINGENCY_KEYS + ["element_type"])

    rows = []
    for row in distinct.itertuples():
        branch_type = TRANSFORMER if row.element_type in POINT_TYPES else LINE
        resolution = _resolve(
            branch_type, _sites(row.substation_from, row.substation_to), np.nan, buses, branches, by_name
        )
        rows.append(
            {
                "eic": row.eic,
                "cont_name": row.cont_name,
                "branch_name": row.branch_name,
                "branch_eic": row.branch_eic,
                "branch_type": branch_type,
                **resolution,
            }
        )
    resolved = pd.DataFrame(rows)
    if resolved.empty:
        return pd.DataFrame(columns=CONTINGENCY_COLUMNS).pipe(ContingencyMatches.validate)

    # An unmatched outage has no branch id to fold onto, so it stays its own row under its name.
    resolved["fold"] = resolved.branch_id.where(resolved.branch_id.notna(), "\0" + resolved.branch_name)
    folded = resolved.groupby(["eic", "cont_name", "fold"], as_index=False).agg(
        branch_name=("branch_name", lambda names: "; ".join(sorted(set(names)))),
        branch_id=("branch_id", "first"),
        branch_type=("branch_type", "first"),
        bus0=("bus0", "first"),
        bus1=("bus1", "first"),
        match_status=("match_status", "first"),
        bus_source=("bus_source", "first"),
        circuits_out=("branch_eic", "size"),
        score=("score", "min"),
    )
    return folded[CONTINGENCY_COLUMNS].pipe(ContingencyMatches.validate)


def coverage(matched: DataFrame[ElementMatches]) -> float:
    """The share of elements that reached a branch of the network, between 0 and 1."""
    if matched.empty:
        return 0.0
    return float((matched.match_status == MATCHED).mean())
