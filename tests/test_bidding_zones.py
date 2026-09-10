import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import shape

from coppersushi import REPO, bidding_zones

FIXTURE = REPO / "tests" / "fixtures" / "bidding-zones" / "zone-shapes.geojson"


def zone_shapes() -> gpd.GeoDataFrame:
    """The fixture as PyPSA hands its shapes over: a GeoDataFrame with a `type` column.

    A GeoDataFrame and not a plain frame on purpose. Its `geometry` column has geopandas'
    own dtype, and `.type` on it answers with the geometry type rather than the column, so
    a test built from a plain frame passes while the real network fails.
    """
    features = json.loads(FIXTURE.read_text())["features"]
    return gpd.GeoDataFrame(
        {
            "idx": [feature["properties"]["idx"] for feature in features],
            "type": [feature["properties"]["type"] for feature in features],
        },
        geometry=[shape(feature["geometry"]) for feature in features],
        crs="EPSG:4326",
    )


ZONES = ("AT", "BE", "DE")


def test_a_coastal_zone_contributes_its_country_and_not_its_offshore_area():
    zones = bidding_zones.core_zone_shapes(zone_shapes(), ZONES)
    assert list(zones.zone) == ["AT", "BE", "DE"]
    belgium = zones[zones.zone.eq("BE")].geometry.iloc[0]
    assert belgium.bounds == (3.0, 50.0, 5.0, 51.5)  # the country, not the North Sea


def test_polygons_come_back_as_plain_shapely_objects():
    """The map takes a pandas column of shapely objects, not a geopandas geometry column."""
    zones = bidding_zones.core_zone_shapes(zone_shapes(), ZONES)
    assert zones.geometry.dtype == object
    assert all(hasattr(polygon, "__geo_interface__") for polygon in zones.geometry)


def test_zones_outside_core_are_left_out():
    assert "GB" not in set(bidding_zones.core_zone_shapes(zone_shapes(), ZONES).zone)


def test_germany_luxembourg_is_one_zone_from_two_countries():
    germany = bidding_zones.core_zone_shapes(zone_shapes(), ZONES).set_index("zone").geometry["DE"]
    assert germany.bounds == (5.7, 49.4, 15.0, 55.0)  # reaches west over Luxembourg
    assert "LU" not in set(bidding_zones.core_zone_shapes(zone_shapes(), ZONES).zone)


def test_a_zone_whose_part_is_missing_is_refused_rather_than_dropped():
    with pytest.raises(ValueError, match="no onshore shape for: FR, LU"):
        bidding_zones.core_zone_shapes(zone_shapes()[zone_shapes().idx.ne("LU")], ("DE", "FR"))


def test_a_zone_with_two_onshore_shapes_is_refused():
    shapes = zone_shapes()
    doubled = pd.concat([shapes, shapes[shapes.idx.eq("AT")]], ignore_index=True)
    with pytest.raises(ValueError, match="several onshore shapes for: AT"):
        bidding_zones.core_zone_shapes(doubled, ZONES)
