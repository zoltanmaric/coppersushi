"""Pandera schema for the substation coordinates `data_sources/osm_locator.py` caches.

Its own module rather than a section of `static_grid.py`: the table is an interim import of
someone else's hand corrections, to be deleted whole when the matcher of
`wiki/specs/jao-grid.md` derives coordinates from the workbook itself.

One row per CSV row, names verbatim and duplicates kept: which locator name answers which
JAO name is a matching decision, and it is made once, in the pure matcher.
Coordinates are WGS 84 degrees, in the `x`/`y` order the source publishes them.
`strict = False` matches `data_model/jao.py`.
"""

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series


class LocatedSubstations(pa.DataFrameModel):
    """One row per located substation name of one TSO template."""

    name: Series[str]  # The Static Grid Model substation name, verbatim
    x: Series[float]  # Longitude [°]
    y: Series[float]  # Latitude [°]
    osm_id: Series[pd.Int64Dtype] = pa.Field(nullable=True)  # OSM object the name was matched to
    template: Series[str]  # TSO template the row came from, e.g. AT, D2, FR225kv — the only country hint

    class Config:
        strict = False
        coerce = True
