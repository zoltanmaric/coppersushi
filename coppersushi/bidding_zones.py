"""Where the Core bidding zones are: their polygons, read off a solved network's shapes.

The zone, not the node, is the unit the day-ahead market clears in, so a price map fills
zone areas rather than colouring buses. PyPSA-Eur happens to carry those areas already —
its `shapes` component holds one polygon per country — which is why no separate geographic
source is fetched.
"""

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.market import CORE_ZONES

ONSHORE = "country"


def core_zone_shapes(shapes: pd.DataFrame) -> DataFrame[BiddingZoneShapes]:
    """The Core bidding zones' onshore polygons, one row per zone.

    A coastal country carries an offshore polygon beside its country one, so a zone appears
    twice and the sea area is not what a price map fills. The onshore rows are those whose
    `type` column says `country` — read as `shapes["type"]`, never `shapes.type`, which a
    GeoDataFrame answers with the geometry type instead of the column.
    """
    onshore = shapes[shapes["type"].eq(ONSHORE) & shapes.idx.isin(CORE_ZONES)]
    zones = onshore.rename(columns={"idx": "zone"})[["zone", "geometry"]].reset_index(drop=True)
    # Plain shapely objects, not geopandas' geometry dtype: what the map needs of a polygon
    # is its geo interface, and a pandas column keeps this table independent of geopandas.
    zones = pd.DataFrame(zones).astype({"geometry": object})
    if zones.zone.duplicated().any():
        repeated = sorted(zones.zone[zones.zone.duplicated()])
        raise ValueError(f"several onshore shapes for: {', '.join(repeated)}")
    return zones.pipe(BiddingZoneShapes.validate)
