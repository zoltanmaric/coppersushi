import json

import pandas as pd
import pytest
from shapely.geometry import Point, shape

from coppersushi import REPO, cnec_market, cnec_price_map, cnecs, market
from coppersushi.data_model.cnec_price_map import MappedCnecElements

FIXTURE = REPO / "tests" / "fixtures" / "synthetic-jao" / "active-fb-day.json"


PRICE_FIXTURE = (
    REPO / "tests" / "fixtures" / "synthetic-electricity-maps" / "day-ahead-prices-hour.json"
)
MAP_FIXTURES = REPO / "tests" / "fixtures" / "cnec-price-map"


def read_zones():
    """The fixture zone shapes in the two columns ``figure`` relies on."""
    features = json.loads((MAP_FIXTURES / "zones.geojson").read_text())["features"]
    return pd.DataFrame(
        {
            "zone": [feature["properties"]["idx"] for feature in features],
            "geometry": [shape(feature["geometry"]) for feature in features],
        }
    )


@pytest.fixture
def inputs():
    rows = json.loads(FIXTURE.read_text())["data"]
    constraints = cnecs.active_constraints(rows)
    ptdfs = cnecs.constraint_ptdfs(rows)
    external = cnecs.active_external_constraints(rows)
    prices = market.day_ahead_prices(json.loads(PRICE_FIXTURE.read_text())["responses"])
    view = cnec_market.snapshot(
        constraints, ptdfs, external, prices, pd.Timestamp("2024-08-28T22:00:00Z")
    )
    zones = read_zones()
    geometries = pd.read_csv(MAP_FIXTURES / "mapped-elements.csv").pipe(
        MappedCnecElements.validate
    )
    return zones, geometries, view


def trace(fig, name):
    return next(item for item in fig.data if item.name == name)


def test_choropleth_carries_one_price_per_priced_zone_and_labels_each(inputs):
    fig = cnec_price_map.figure(*inputs)
    fill = trace(fig, "published day-ahead price")
    assert list(fill.locations) == ["AT", "BE"]
    assert list(fill.z) == [50.0, 70.0]
    assert [feature["id"] for feature in fill.geojson["features"]] == ["AT", "BE"]
    assert list(trace(fig, "zone prices").text) == ["Austria<br>€50", "Belgium<br>€70"]


def test_each_zone_label_sits_inside_its_own_zone(inputs):
    zones, _, _ = inputs
    labels = trace(cnec_price_map.figure(*inputs), "zone prices")
    shapes = dict(zip(zones.zone, zones.geometry))
    for text, lon, lat in zip(labels.text, labels.lon, labels.lat):
        zone = next(code for code, name in market.ZONE_NAMES.items() if text.startswith(name))
        assert shapes[zone].contains(Point(lon, lat))


def test_unpriced_zones_are_left_off_the_map(inputs):
    zones, geometries, view = inputs
    fill = trace(cnec_price_map.figure(zones, geometries, view), "published day-ahead price")
    assert "DE" not in list(fill.locations)


def test_prices_without_any_zone_geometry_are_refused(inputs):
    zones, geometries, view = inputs
    with pytest.raises(ValueError, match="none of the priced zones"):
        cnec_price_map.figure(zones.iloc[0:0], geometries, view)


def test_one_element_is_drawn_once_and_one_target_carries_each_binding_row(inputs):
    fig = cnec_price_map.figure(*inputs)
    lines = trace(fig, "market-binding CNECs")
    assert list(lines.lon[:2]) == [14.4, 15.1]
    assert pd.isna(lines.lon[2])
    rows = trace(fig, "binding rows")
    assert len(rows.lon) == 1
    assert "Grayspire" in rows.text[0]
    assert "Base case (no contingency)" in rows.text[0]
    assert "not physically overloaded" not in rows.text[0]
    assert rows.customdata[0][0] == "1,2"


def test_hover_carries_contingency_direction_ram_and_shadow_price(inputs):
    hover = trace(cnec_price_map.figure(*inputs), "binding rows").text[0]
    assert "Binding under:" in hover
    assert "Direction: DIRECT" in hover
    assert "RAM: 172 MW" in hover
    assert "Shadow price: 100.00 €/MWh" in hover


def test_map_states_coverage_and_what_purple_does_not_mean(inputs):
    fig = cnec_price_map.figure(*inputs)
    note = fig.layout.annotations[0].text
    assert "2 of 2 active rows mapped" in note
    assert "not physically overloaded" in note
