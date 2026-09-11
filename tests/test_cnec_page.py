import json

import pandas as pd
from shapely.geometry import shape

from coppersushi import REPO, cnec_page, cnecs, market
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.market_day import MarketDay

ACTIVE = REPO / "tests/fixtures/synthetic-jao/active-fb-day.json"
PRICES = REPO / "tests/fixtures/synthetic-electricity-maps/day-ahead-prices-hour.json"
MAP = REPO / "tests/fixtures/cnec-price-map"


def read_zones() -> pd.DataFrame:
    """The fixture zone shapes in the two columns the map relies on."""
    features = json.loads((MAP / "zones.geojson").read_text())["features"]
    return pd.DataFrame(
        {
            "zone": [feature["properties"]["idx"] for feature in features],
            "geometry": [shape(feature["geometry"]) for feature in features],
        }
    )


def inputs() -> cnec_page.Day:
    rows = json.loads(ACTIVE.read_text())["data"]
    return cnec_page.Day(
        market_day=MarketDay.on("2024-08-29"),
        zones=read_zones(),
        mapped_elements=pd.read_csv(MAP / "mapped-elements.csv").pipe(
            MappedCnecElements.validate
        ),
        constraints=cnecs.active_constraints(rows),
        ptdfs=cnecs.constraint_ptdfs(rows),
        external_constraints=cnecs.active_external_constraints(rows),
        prices=market.day_ahead_prices(json.loads(PRICES.read_text())["responses"]),
    )


def descendants(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    for child in children if isinstance(children, list) else [children]:
        yield from descendants(child)


def test_layout_starts_on_the_supplied_day_and_exposes_all_controls():
    page = cnec_page.layout("2024-08-29")
    controls = {
        component.id: component
        for component in descendants(page)
        if getattr(component, "id", None)
    }
    assert controls["cnec-date"].value == "2024-08-29"
    assert {
        "cnec-constraint",
        "cnec-reference-zone",
        "cnec-map",
        "cnec-interval",
        "cnec-status",
    } <= set(controls)


def test_a_historical_day_has_every_hour_and_timezone_disambiguated_marks():
    rendered = cnec_page.render(inputs(), 0, None, "AT")
    assert rendered.interval_max == 23
    assert rendered.interval_marks[0]["label"] == "00:00"
    assert rendered.interval_marks[22]["label"] == "22:00" and 23 not in rendered.interval_marks


def test_binding_rows_are_sorted_by_shadow_price_and_keep_their_source_id():
    rendered = cnec_page.render(inputs(), 0, None, "AT")
    assert [option["value"] for option in rendered.constraint_options] == ["", "1", "2"]
    assert "100.00 €/MWh" in rendered.constraint_options[1]["label"]
    assert "base case" in rendered.constraint_options[2]["label"]


def test_selecting_a_row_adds_its_reference_based_influence():
    rendered = cnec_page.render(inputs(), 0, "1", "BE")
    assert rendered.constraint_value == "1"
    assert any(trace.name == "contribution relative to BE" for trace in rendered.figure.data)


def test_a_selection_from_another_interval_is_cleared():
    day = inputs()
    later_prices = day.prices.assign(interval=pd.Timestamp("2024-08-28T23:00:00Z"))
    later = cnec_page.Day(**{**day.__dict__, "prices": later_prices})
    rendered = cnec_page.render(later, 1, "1", "AT")
    assert rendered.constraint_value is None
    assert rendered.constraint_options == [cnec_page.NO_SELECTION]
