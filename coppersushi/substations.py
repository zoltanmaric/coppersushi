"""Matching JAO's substation names to our OSM-derived buses.

JAO locates a grid element by naming its two ends — `substationFrom: AVELGEM` — and never
publishes a coordinate. Our network is the mirror image: every bus has a coordinate and an
OSM substation name. The name is the only join key, and the two conventions differ.

`normalise` is what makes them comparable. Each of its steps earns its place from a name
measured in the real data on 2026-09-09, where a rough normaliser matched 89 of 145 JAO
names; the misses were dominated by five shapes, one per step:

1. **Diacritics** — JAO writes ASCII, OSM writes `Mühlbach`, `Rzeszów`, `Horná Ždaňa`.
   NFKD folds most of them; `ł` and `đ` have no decomposition and are transliterated first,
   without which `Mikułowa` folds to `mikuowa` and matches nothing.
2. **Quoted inner names** — Polish OSM wraps the real name in a description:
   `Stacja elektroenergetyczna "Krosno Iskrzynia" 400/110 kV`. Both ASCII and typographic
   quotes occur, and Belgian names arrive quoted whole (`"Avelgem"`).
3. **Voltages in the name** — `400/110 kV`, and parenthesised asides.
4. **Prefixes**, operator and facility-type both: `RTP Cirkovce`, `APG Umspannwerk
   Westtirol`, `Umspannwerk Bisamberg`, `SE Rzeszów Systemowa`.
5. **Element designators trailing the site name** — `Mikulowa AT1` names a transformer at
   Mikułowa, and `Westtirol 1` a circuit at Westtirol.

The designators are dropped for comparison only. `jao_name` in the output keeps JAO's
spelling in full, because `Westtirol 1` and `Westtirol 2` are two distinct elements at one
site and a consumer must still be able to tell them apart.

A sixth shape is unfixable here and belongs in the overrides file: JAO's initial-and-dot
abbreviations, `H.Zdana` for `Horná Ždaňa`. Nothing recovers the elided word, so every
multi-token OSM name is *also* indexed under its own abbreviated form and the two meet
there.

Design: `wiki/specs/jao-grid.md`.
"""

import difflib
import logging
import re
import unicodedata

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.substations import BusNames, Matches, Overrides

logger = logging.getLogger(__name__)

# ł and đ carry no NFKD decomposition, so folding alone would delete them.
TRANSLITERATIONS = str.maketrans({"ł": "l", "Ł": "L", "đ": "d", "Đ": "D"})
QUOTED = re.compile(r'["„”“](.+?)["„”“]')
PARENTHESISED = re.compile(r"\(.*?\)")
VOLTAGE = re.compile(r"\b\d{3}\s*kv\b|\b\d+\s*/\s*\d+\s*(?:kv)?\b")
NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
DESIGNATOR = re.compile(r"\d+|(?:at|tr|t|ps)\d+")  # A transformer or circuit number, not a site name
PREFIXES = frozenset(
    {
        "apg",
        "elektroenergetyczna",
        "elia",
        "poste",
        "rozdzielnia",
        "rozvodna",
        "rtp",
        "se",
        "schaltwerk",
        "stacja",
        "statie",
        "station",
        "substation",
        "umspannwerk",
        "uw",
    }
)

UNMATCHED = "unmatched"
COLUMNS = ["jao_name", "bus_id", "osm_id", "osm_name", "country", "score", "source"]


def normalise(name: str) -> str:
    """A substation name reduced to the form the two datasets agree on.

    Empty where the name says nothing but its own decoration — an unnamed OSM substation,
    or a JAO field that is blank.
    """
    quoted = QUOTED.search(name)
    text = quoted.group(1) if quoted else name
    text = unicodedata.normalize("NFKD", text.translate(TRANSLITERATIONS))
    text = text.encode("ascii", "ignore").decode().lower()
    text = NON_ALPHANUMERIC.sub(" ", VOLTAGE.sub(" ", PARENTHESISED.sub(" ", text)))
    tokens = text.split()
    while len(tokens) > 1 and tokens[0] in PREFIXES:
        tokens.pop(0)
    while len(tokens) > 1 and DESIGNATOR.fullmatch(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def _abbreviated(key: str) -> str | None:
    """`key` with its leading word cut to an initial, the form JAO writes `H.Zdana` in."""
    tokens = key.split()
    if len(tokens) < 2 or len(tokens[0]) < 2:
        return None
    return " ".join([tokens[0][0], *tokens[1:]])


def _voltage(bus_id: str) -> int:
    """The substation voltage [kV] the bus id ends in, or −1 if it ends in anything else."""
    suffix = bus_id.rsplit("-", 1)[-1]
    return int(suffix) if suffix.isdigit() else -1


def osm_id(bus_id: str) -> str:
    """The OSM object the bus belongs to: its id without the voltage suffix."""
    return bus_id.rsplit("-", 1)[0]


def _index(buses: DataFrame[BusNames]) -> dict[str, list[str]]:
    """Normalised name → the bus ids carrying it, each name also indexed abbreviated.

    Buses whose OSM name is empty are absent: they cannot be matched on a name they lack.
    """
    index: dict[str, list[str]] = {}
    for bus_id, name in zip(buses.bus_id, buses.osm_name):
        key = normalise(name)
        if not key:
            continue
        for form in (key, _abbreviated(key)):
            if form is not None:
                index.setdefault(form, []).append(bus_id)
    return index


def _pick(jao_name: str, bus_ids: list[str]) -> str:
    """The one bus a name resolves to: the highest voltage, ties broken on the id.

    One site commonly appears as a 380 kV and a 220 kV bus, and JAO's name distinguishes
    neither. Returning both would break the one-row-per-name contract and picking
    arbitrarily would be worse, so the highest voltage wins deterministically and the
    ambiguity is logged.
    """
    chosen = max(bus_ids, key=lambda bus_id: (_voltage(bus_id), bus_id))
    if len(bus_ids) > 1:
        logger.info(
            "%r matches %d buses (%s); taking the highest voltage, %s",
            jao_name,
            len(bus_ids),
            ", ".join(sorted(bus_ids)),
            chosen,
        )
    return chosen


def match(
    jao_names: pd.Series,
    buses: DataFrame[BusNames],
    overrides: DataFrame[Overrides] | None = None,
    threshold: float = 0.87,
) -> DataFrame[Matches]:
    """One row per distinct JAO substation name, resolved to a bus where it can be.

    Overrides win outright, then an exact hit on the normalised name, then the closest
    normalised name at or above `threshold`. A name that reaches none of those keeps its
    row with `source` "unmatched" rather than disappearing.
    """
    index = _index(buses)
    keys = list(index)
    by_id = buses.set_index("bus_id")
    forced = {} if overrides is None else dict(zip(overrides.jao_name, overrides.bus_id))

    rows = []
    for jao_name in pd.unique(jao_names.dropna()):
        key = normalise(jao_name)
        if jao_name in forced:
            bus_id, score, source = forced[jao_name], 1.0, "override"
        elif key in index:
            bus_id, score, source = _pick(jao_name, index[key]), 1.0, "exact"
        else:
            close = difflib.get_close_matches(key, keys, n=1, cutoff=threshold) if key else []
            if close:
                bus_id = _pick(jao_name, index[close[0]])
                score = difflib.SequenceMatcher(None, key, close[0]).ratio()
                source = "fuzzy"
            else:
                bus_id, score, source = None, 0.0, UNMATCHED
        bus = by_id.loc[bus_id] if bus_id is not None else None
        rows.append(
            {
                "jao_name": jao_name,
                "bus_id": bus_id,
                "osm_id": None if bus is None else osm_id(bus_id),
                "osm_name": None if bus is None else bus.osm_name,
                "country": None if bus is None else bus.country,
                "score": score,
                "source": source,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS).pipe(Matches.validate)


def coverage(matches: DataFrame[Matches]) -> float:
    """The share of JAO names that reached a bus, between 0 and 1."""
    if matches.empty:
        return 0.0
    return float((matches.source != UNMATCHED).mean())
