"""Pure geometry regressions for the country-cap display outline."""

import json

import pandas as pd

from shapely.geometry import MultiPolygon, Point, Polygon, box, shape

from coppersushi import REPO
from coppersushi.cnec_price_map import _country_rings, _price_traces, _cap_traces


def test_real_polish_riverbanks_do_not_become_an_inland_cap_border():
    fixture = REPO / 'tests/fixtures/cnec-price-map/poland-inland-channel.geojson'
    land = shape(json.loads(fixture.read_text())['geometry'])
    inland = box(18.1, 52.6, 19.4, 54.0)
    assert land.boundary.intersects(inland)  # This source reproduced the visible false border.
    assert all(not ring.intersects(inland) for ring in _country_rings(land))
    fill, _ = _price_traces(pd.DataFrame([{'zone': 'PL', 'geometry': land, 'price': 100.0}]), None)
    displayed = shape(fill.geojson['features'][0]['geometry'])
    assert not displayed.boundary.intersects(inland)


def test_lakes_are_not_outlined_and_nearby_islands_remain_separate():
    mainland = Polygon(box(18, 52, 18.2, 52.2).exterior.coords,
                       [box(18.05, 52.05, 18.1, 52.1).exterior.coords])
    island = box(18.205, 52.05, 18.22, 52.1)
    rings = _country_rings(MultiPolygon([mainland, island]))
    assert len(rings) == 2
    assert sum(Polygon(ring).covers(Point(18.075, 52.075)) for ring in rings) == 1
    assert sum(Polygon(ring).covers(island.representative_point()) for ring in rings) == 1


def test_cap_highlight_preserves_every_display_boundary_vertex():
    fixture = REPO / 'tests/fixtures/cnec-price-map/poland-inland-channel.geojson'
    land = shape(json.loads(fixture.read_text())['geometry'])
    caps = pd.DataFrame([{'source_id': -2, 'name': 'Poland export cap', 'direction': 'export',
                         'capacity': 100.0, 'shadow_price': 2.0}])
    outline = next(t for t in _cap_traces(pd.DataFrame([{'zone': 'PL', 'geometry': land}]), caps, -2)
                   if t.name == 'binding country cap')
    highlighted = set(zip(outline.lon, outline.lat))
    assert all(point in highlighted for ring in _country_rings(land) for point in ring.coords)
