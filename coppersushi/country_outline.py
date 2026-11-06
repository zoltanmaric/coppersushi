"""Shared display coastlines for browser country fills and cap outlines."""
from functools import lru_cache
import numpy as np
from pyproj import Transformer
from shapely import transform
from shapely.geometry import LinearRing, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
COUNTRY_CHANNEL_HALF_WIDTH_M = 500

@lru_cache(maxsize=32)
def country_rings(geometry: Polygon | MultiPolygon) -> tuple[LinearRing, ...]:
    """A schematic country boundary, excluding narrow water channels and inland holes.

    Land polygons follow riverbanks inland from the coast. Close those narrow cuts in
    metric coordinates before outlining or filling, without joining separate islands.
    """
    to_metres = Transformer.from_crs(4326, 3035, always_xy=True)
    to_lonlat = Transformer.from_crs(3035, 4326, always_xy=True)

    def project[G: BaseGeometry](geometry: G, projection: Transformer) -> G:
        return transform(geometry, lambda xy: np.column_stack(projection.transform(xy[:, 0], xy[:, 1])))

    polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
    rings: list[LinearRing] = []
    for polygon in polygons:
        closed = project(polygon, to_metres).buffer(COUNTRY_CHANNEL_HALF_WIDTH_M, join_style="mitre").buffer(
            -COUNTRY_CHANNEL_HALF_WIDTH_M, join_style="mitre")
        parts = list(closed.geoms) if isinstance(closed, MultiPolygon) else [closed]
        rings.extend(project(part.exterior, to_lonlat) for part in parts if not part.is_empty)
    return tuple(rings)

