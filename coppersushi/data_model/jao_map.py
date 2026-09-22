"""Pandera schema for the one frame `jao_map.py` draws from.

JAO's day and our network meet here: a matched element (`data_model/elements.py`) gains the
hourly limit and shadow price JAO published for it (`data_model/jao.py`), plus the coordinates
of the branch it resolved to. One row per (snapshot, element) — the map's own grain, since a
frame is drawn per snapshot and an element is drawn once in it.

`snapshot` is **naive**, PyPSA's convention, and that is deliberate: `jao_map.to_snapshot` is
the single point where JAO's tz-aware UTC hours become it (`coppersushi/AGENTS.md`,
explicit-timezones).
"""

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series


class HourlyElements(pa.DataFrameModel):
    """One row per (snapshot, element EIC): what JAO measured, and where we drew it."""

    snapshot: Series[pd.Timestamp]  # Naive UTC, matching `pypsa.Network.snapshots`
    eic: Series[str]
    name: Series[str]  # The TSO's name for the element
    tso: Series[str]
    element_type: Series[str]  # JAO's: Line, TieLine, Transformer, PST, or "" where it published none
    branch_type: Series[str]  # Line or Transformer: which of our component tables it landed in
    branch_id: Series[str]  # The component's name in the network
    end0: Series[str]  # bus0 as substation name and id, for the hover
    end1: Series[str]  # bus1 likewise; the same site as end0 for a transformer
    x0: Series[float]  # Longitude of the branch's bus0
    y0: Series[float]  # Latitude of the branch's bus0
    x1: Series[float]  # Longitude of bus1; equal to x0 for a transformer, which is one site
    y1: Series[float]
    fmax: Series[float]  # Maximum admissible flow this hour [MW]
    ram: Series[float]  # Remaining available margin this hour [MW], the tighter direction's
    margin: Series[float]  # Ours: ram / fmax, the share of the element left to the market
    shadow_price: Series[float] = pa.Field(nullable=True)  # [EUR/MWh]; NaN where it did not bind
    binding: Series[bool]  # Ours: the shadow-price feed carried this element in this hour

    class Config:
        strict = False
        coerce = True
