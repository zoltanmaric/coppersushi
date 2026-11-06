"""Where the Core bidding zones are: their polygons, read off a solved network's shapes.

The zone, not the node, is the unit the day-ahead market clears in, so a price map fills
zone areas rather than colouring buses. PyPSA-Eur happens to carry those areas already —
its `shapes` component holds one polygon per country — which is why no separate geographic
source is fetched.
"""

from collections.abc import Iterable

import pandas as pd
from pandera.typing import DataFrame
from shapely.ops import unary_union

from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.market import CORE_ZONES

ONSHORE = "country"
# A bidding zone is not always one country: Core's DE is Germany–Luxembourg. Parts are the
# shape identifiers the geometry source knows; a zone is the union of its parts. Sub-national
# zones (Italy, Sweden) would need a finer source than country polygons to supply their parts.
ZONE_PARTS = {zone: (zone,) for zone in CORE_ZONES} | {"DE": ("DE", "LU")}


def core_zone_shapes(
    shapes: pd.DataFrame, zones: Iterable[str] = CORE_ZONES
) -> DataFrame[BiddingZoneShapes]:
    """The requested bidding zones' onshore polygons, one row per zone, every zone present.

    A coastal country carries an offshore polygon beside its country one, so a part appears
    twice and the sea area is not what a price map fills. The onshore rows are those whose
    `type` column says `country` — read as `shapes["type"]`, never `shapes.type`, which a
    GeoDataFrame answers with the geometry type instead of the column.
    """
    zones = list(zones)
    wanted = {part for zone in zones for part in ZONE_PARTS[zone]}
    onshore = shapes[shapes["type"].eq(ONSHORE) & shapes.idx.isin(wanted)]
    if onshore.idx.duplicated().any():
        repeated = sorted(onshore.idx[onshore.idx.duplicated()])
        raise ValueError(f"several onshore shapes for: {', '.join(repeated)}")
    missing = sorted(wanted - set(onshore.idx))
    if missing:
        raise ValueError(f"no onshore shape for: {', '.join(missing)}")
    # Plain shapely objects, not geopandas' geometry dtype: what the map needs of a polygon
    # is its geo interface, and a pandas column keeps this table independent of geopandas.
    by_part = dict(zip(onshore.idx, (geometry for geometry in onshore.geometry)))
    result = pd.DataFrame(
        {
            "zone": zones,
            "geometry": [unary_union([by_part[part] for part in ZONE_PARTS[zone]]) for zone in zones],
        }
    ).astype({"geometry": object})
    return result.pipe(BiddingZoneShapes.validate)
