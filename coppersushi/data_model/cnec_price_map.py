"""Typed domain-element enrichment handed to the CNEC price map.

``ActiveConstraints`` models JAO's published, row-grained result. ``MappedCnecElements``
models the separate enrichment step: the domain element is matched to a PyPSA branch and
given coordinates. This is not the Static Grid Model table, whose EIC is not a unique key.
An unresolved element keeps its row so the map reports true coverage.
"""

import pandera.pandas as pa
from pandera.typing import Series


class MappedCnecElements(pa.DataFrameModel):
    """One domain element, enriched with its matched PyPSA branch and geometry."""

    eic: Series[str] = pa.Field(unique=True)  # Domain element identity, not a static-grid row key
    element_type: Series[str]
    branch_id: Series[str] = pa.Field(nullable=True)
    branch_type: Series[str]
    x0: Series[float] = pa.Field(nullable=True)
    y0: Series[float] = pa.Field(nullable=True)
    x1: Series[float] = pa.Field(nullable=True)
    y1: Series[float] = pa.Field(nullable=True)
    match_status: Series[str] = pa.Field(
        isin=["matched", "no_substation", "no_branch", "no_component_in_network"]
    )
    bus_source: Series[str]
    score: Series[float] = pa.Field(ge=0, le=1)

    class Config:
        strict = False
        coerce = True
