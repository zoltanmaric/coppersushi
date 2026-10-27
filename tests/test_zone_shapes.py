import json

import geopandas as gpd
import pandas as pd

from coppersushi import REPO, bidding_zones
from coppersushi.data_sources import zone_shapes


def test_bundled_outlines_preserve_the_same_zone_polygons(tmp_path):
    features = json.loads((REPO / 'tests/fixtures/bidding-zones/zone-shapes.geojson').read_text())['features']
    source = gpd.GeoDataFrame.from_features(features, crs='EPSG:4326')
    expected = bidding_zones.core_zone_shapes(source, ('AT', 'BE', 'DE'))
    path = tmp_path / 'zones.geojson'
    zone_shapes.write(expected, path)
    actual = zone_shapes.read(path)
    pd.testing.assert_frame_equal(actual, expected)
    assert actual[actual.zone.eq('DE')].geometry.iloc[0].bounds == (5.7, 49.4, 15.0, 55.0)
