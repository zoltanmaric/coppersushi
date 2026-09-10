"""Place JAO's monitored elements on the map from their published substation names.

An interim stand-in for the `match_elements` step of `wiki/specs/jao-grid.md`: that work
matches an element to a PyPSA branch and inherits the branch's coordinates, this places an
element from its two substations alone and touches no network. JAO's domain feed names both
endpoints of every monitored element, so no element name is parsed here — the sole inference
is which located substation a published name means. Three things make that inference:

- **Two keys per name.** JAO spells German umlauts both ways: transliterated (`Roehrsdorf`
  for Röhrsdorf) and dropped (`Durnrohr` for Dürnrohr). Every name is keyed both ways and a
  hit on either counts.
- **Aliases for the sites the locator files under another name**, hand-listed and committed.
- **Proximity where a name is not unique.** Two substations 554 km apart are both `St. Peter`.
  A monitored element joins substations near each other, so where a name means several
  places the combination with the shortest span wins.

Measured against the locator on 2026-09-11's 162 published substations: 133 hit a key
outright, 10 after a trim, and the rest are absent from the locator or ambiguous alone.
"""

import itertools
import math
import re
import unicodedata
from collections.abc import Iterator

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.jao import ElementEnds

Point = tuple[float, float]

POINT_TYPES = ("Transformer", "PST")
SOURCE = "osm-locator"
UNRESOLVED = "unresolved"
# Points this close are one site recorded twice, not a choice to make: the duplicated
# national templates repeat sites at ~1e-13 degrees, and `OTHERCOUNTRIES` repeats three of
# them — same OSM id — with coordinates rounded up to 418 m away. Distinct substations
# sharing a name are hundreds of kilometres apart, so this threshold separates them safely.
SAME_SITE_DEGREES = 0.01  # ~1.1 km
EXPANSIONS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
EXACT, TAP, TRIMMED = 1.0, 0.8, 0.6


def _clean(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _folded(name: str) -> str:
    """The name with its combining marks dropped: Dürnrohr becomes `durnrohr`."""
    decomposed = unicodedata.normalize("NFKD", str(name))
    return _clean("".join(c for c in decomposed if not unicodedata.combining(c)))


def _expanded(name: str) -> str:
    """The name with German umlauts spelled out: Röhrsdorf becomes `roehrsdorf`."""
    expanded = "".join(EXPANSIONS.get(c.lower(), c) for c in str(name))
    return _folded(expanded)


def keys(name: str) -> list[str]:
    """Both spellings a published substation name may be recorded under."""
    folded, expanded = _folded(name), _expanded(name)
    return [folded] if folded == expanded else [folded, expanded]


def _variants(name: str, aliases: dict[str, str]) -> Iterator[tuple[str, float]]:
    """Keys to try, best first, each with the confidence a hit on it deserves."""
    base = keys(name)
    if alias := aliases.get(_folded(name)):
        base = keys(alias) + base
    yield from ((key, EXACT) for key in base)
    # A tap point on a corridor is published as `Y_Mellach`; the site is `Mellach`.
    yield from ((key[2:], TAP) for key in base if key.startswith("y "))
    for key in base:
        tokens = key.split()
        for cut in range(len(tokens) - 1, 0, -1):
            # Trailing equipment tokens: `Mikulowa PST1` is located as `Mikulowa`.
            yield " ".join(tokens[:cut]), TRIMMED


def _cluster(points: list[Point]) -> list[Point]:
    """One point per distinct place among repeated records of the same substations."""
    places: list[Point] = []
    for x, y in points:
        if not any(
            abs(x - px) <= SAME_SITE_DEGREES and abs(y - py) <= SAME_SITE_DEGREES
            for px, py in places
        ):
            places.append((x, y))
    return places


def substation_index(substations: pd.DataFrame) -> dict[str, list[Point]]:
    """Every key a located substation answers to, and the distinct places it can mean."""
    located: dict[str, list[Point]] = {}
    for row in substations.itertuples():
        for key in keys(row.name):
            located.setdefault(key, []).append((float(row.x), float(row.y)))
    return {key: _cluster(points) for key, points in located.items()}


def _candidates(name, index: dict[str, list[Point]], aliases: dict[str, str]):
    """The places a published substation name can mean, under its best-scoring key."""
    if pd.isna(name):
        return None
    for key, score in _variants(str(name), aliases):
        if key in index:
            return key, index[key], score
    return None


def _closest(from_places: list[Point], to_places: list[Point]) -> tuple[Point, Point]:
    """The pair of candidate places with the shortest span between them."""
    return min(
        itertools.product(from_places, to_places),
        key=lambda pair: math.dist(pair[0], pair[1]),
    )


def _placement(element, index: dict[str, list[Point]], aliases: dict[str, str]) -> dict:
    """Where one monitored element is drawn, or why it is not drawn at all."""
    ends = [
        _candidates(element.substation_from, index, aliases),
        _candidates(element.substation_to, index, aliases),
    ]
    unplaced = {
        "branch_id": None,
        "x0": None,
        "y0": None,
        "x1": None,
        "y1": None,
        "match_status": "no_substation",
        "bus_source": UNRESOLVED,
        "score": 0.0,
    }
    if any(end is None for end in ends):
        return unplaced
    (from_key, from_places, from_score), (to_key, to_places, to_score) = ends
    if from_key == to_key:
        # A transformer or phase shifter sits at one site, so there is no span to
        # disambiguate with: an ambiguous name leaves it unplaced rather than guessed.
        if len(from_places) > 1:
            return unplaced
        start = end = from_places[0]
    else:
        start, end = _closest(from_places, to_places)
    return {
        # No PyPSA branch is consulted, so the located pair is the drawn identity: both
        # directions of one element, and both TSOs' orientations, share one line.
        "branch_id": f"{SOURCE}/{'--'.join(sorted([from_key, to_key]))}",
        "x0": start[0],
        "y0": start[1],
        "x1": end[0],
        "y1": end[1],
        "match_status": "matched",
        "bus_source": SOURCE,
        "score": min(from_score, to_score),
    }


def locate_elements(
    ends: DataFrame[ElementEnds],
    substations: pd.DataFrame,
    aliases: dict[str, str] | None = None,
) -> DataFrame[MappedCnecElements]:
    """One row per publishing TSO and element, placed between its substations where located.

    `x0`/`y0` is the TSO's own `substation_from`, so that TSO's DIRECT runs from `(x0, y0)`
    to `(x1, y1)`. Two TSOs monitoring one tie-line publish it under one EIC but each from
    its own end — `Etzenricht - Hradec` and `Hradec - Etzenricht` — and get two rows drawn
    over one another under one `branch_id`.

    An element with an endpoint the locator does not hold keeps its row without coordinates,
    so the map can say how much of the published set it is showing. `aliases` names the
    sites the locator files under a different name, keyed by the published name.
    """
    index = substation_index(substations)
    by_alias = {_folded(published): located for published, located in (aliases or {}).items()}
    rows = [
        {
            "eic": element.eic,
            "tso": element.tso,
            "element_type": element.element_type,
            "branch_type": "Transformer" if element.element_type in POINT_TYPES else "Line",
            **_placement(element, index, by_alias),
        }
        for element in ends.itertuples()
    ]
    return pd.DataFrame(rows, columns=list(MappedCnecElements.to_schema().columns)).pipe(
        MappedCnecElements.validate
    )
