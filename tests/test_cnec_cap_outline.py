"""Pure geometry regressions for the country-cap display outline."""

import json


from shapely.geometry import MultiPolygon, Point, Polygon, box, shape

from coppersushi import REPO
from coppersushi.country_outline import country_rings


def test_real_polish_riverbanks_do_not_become_an_inland_cap_border():
    fixture = REPO / 'tests/fixtures/cnec-price-map/poland-inland-channel.geojson'
    land = shape(json.loads(fixture.read_text())['geometry'])
    inland = box(18.1, 52.6, 19.4, 54.0)
    assert land.boundary.intersects(inland)  # This source reproduced the visible false border.
    displayed = MultiPolygon([Polygon(ring) for ring in country_rings(land)])
    assert not displayed.boundary.intersects(inland)


def test_lakes_are_not_outlined_and_nearby_islands_remain_separate():
    mainland = Polygon(box(18, 52, 18.2, 52.2).exterior.coords,
                       [box(18.05, 52.05, 18.1, 52.1).exterior.coords])
    island = box(18.205, 52.05, 18.22, 52.1)
    rings = country_rings(MultiPolygon([mainland, island]))
    assert len(rings) == 2
    assert sum(Polygon(ring).covers(Point(18.075, 52.075)) for ring in rings) == 1
    assert sum(Polygon(ring).covers(island.representative_point()) for ring in rings) == 1
