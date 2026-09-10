"""Typed geometry handed to the CNEC price map.

The geometry producer is deliberately separate: JAO supplies the EIC and endpoint
identity but not coordinates. A row stays present when it is unresolved so the map can
report its true coverage rather than silently dropping it.
"""

import pandera.pandas as pa
from pandera.typing import Series


class CnecGeometries(pa.DataFrameModel):
    """One physical element EIC, located on the map or carrying why it was not."""

    eic: Series[str] = pa.Field(unique=True)
    element_type: Series[str]
    x0: Series[float] = pa.Field(nullable=True)
    y0: Series[float] = pa.Field(nullable=True)
    x1: Series[float] = pa.Field(nullable=True)
    y1: Series[float] = pa.Field(nullable=True)
    match_status: Series[str]

    class Config:
        strict = False
        coerce = True
