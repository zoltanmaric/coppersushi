"""Pandera schemas for the substation name join `substations.py` performs.

JAO names a grid element's ends and never gives a coordinate; our buses carry a
coordinate and an OpenStreetMap name. The substation name is therefore the only key
between the two datasets, and these three tables are its two sides and its result.

`strict = False` throughout, matching `data_model/jao.py`, so a caller may carry its own
columns through the join.
"""

import pandera.pandas as pa
from pandera.typing import Series


class BusNames(pa.DataFrameModel):
    """The name side of the network's bus table: one row per bus.

    Several buses share one OSM substation at different voltages, so `osm_name` is not
    unique — `substations.match` resolves that on the voltage in `bus_id`.
    """

    bus_id: Series[str] = pa.Field(unique=True)  # e.g. `relation/10047997-220`: OSM id, then the bus voltage [kV]
    osm_name: Series[str]  # The OSM substation's name; empty string where OSM has none, never NaN
    country: Series[str]  # ISO 3166-1 alpha-2

    class Config:
        strict = False
        coerce = True


class Overrides(pa.DataFrameModel):
    """Hand-made matches, one per JAO name, that win over anything the matcher computes."""

    jao_name: Series[str] = pa.Field(unique=True)  # Exactly as JAO spells it
    bus_id: Series[str]  # The bus it means; must exist in the `BusNames` frame, or `match` raises
    note: Series[str]  # Why the match needed a human

    class Config:
        strict = False
        coerce = True


class Matches(pa.DataFrameModel):
    """One row per distinct JAO substation name, matched or not.

    An unmatched or ambiguous name keeps its row with the bus columns null and `score`
    0.0, so a consumer sees the miss rather than a silently shorter table.
    """

    jao_name: Series[str] = pa.Field(unique=True)  # JAO's spelling, digits and all: `Westtirol 1` ≠ `Westtirol 2`
    bus_id: Series[str] = pa.Field(nullable=True)
    osm_id: Series[str] = pa.Field(nullable=True)  # `bus_id` without its voltage suffix
    osm_name: Series[str] = pa.Field(nullable=True)
    country: Series[str] = pa.Field(nullable=True)
    score: Series[float]  # difflib similarity of the two normalised names; 1.0 for an override or exact hit
    source: Series[str]  # override, exact, fuzzy, ambiguous (two sites share the key) or unmatched

    class Config:
        strict = False
        coerce = True
