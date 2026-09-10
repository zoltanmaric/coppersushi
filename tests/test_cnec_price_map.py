import json

import pandas as pd
import pytest

from coppersushi import REPO, cnec_market, cnec_price_map, cnecs, market
from coppersushi.data_model.cnec_price_map import CnecGeometries

FIXTURE = REPO / "tests" / "fixtures" / "synthetic-jao" / "active-fb-day.json"


def payload(zone: str, price: float) -> dict:
    return {
        "data": [
            {
                "zone": zone,
                "datetime": "2024-08-28T22:00:00Z",
                "updatedAt": "2024-08-28T12:05:00Z",
                "value": price,
                "unit": "EUR/MWh",
                "source": "example.test",
            }
        ]
    }


@pytest.fixture
def inputs():
    rows = json.loads(FIXTURE.read_text())["data"]
    constraints = cnecs.active_constraints(rows)
    ptdfs = cnecs.constraint_ptdfs(rows)
    external = cnecs.active_external_constraints(rows)
    prices = market.day_ahead_prices([payload("AT", 50.0), payload("BE", 70.0)])
    view = cnec_market.snapshot(
        constraints, ptdfs, external, prices, pd.Timestamp("2024-08-28T22:00:00Z")
    )
    buses = pd.DataFrame(
        {
            "x": [14.0, 15.0, 4.0, 5.0],
            "y": [47.5, 48.0, 50.7, 51.0],
            "country": ["AT", "AT", "BE", "BE"],
        },
        index=pd.Index(["at-1", "at-2", "be-1", "be-2"], name="Bus"),
    )
    geometries = pd.DataFrame(
        {
            "eic": ["99T-AA-BB-00003P"],
            "element_type": ["TieLine"],
            "x0": [14.4],
            "y0": [46.7],
            "x1": [15.1],
            "y1": [46.2],
            "match_status": ["matched"],
        }
    ).pipe(CnecGeometries.validate)
    return buses, geometries, view


def trace(fig, name):
    return next(item for item in fig.data if item.name == name)


def test_prices_colour_every_network_node_and_label_each_zone(inputs):
    fig = cnec_price_map.figure(*inputs)
    nodes = trace(fig, "published day-ahead price")
    assert list(nodes.marker.color) == [50.0, 50.0, 70.0, 70.0]
    assert list(trace(fig, "zone prices").text) == ["AT<br>50.00 €", "BE<br>70.00 €"]


def test_one_element_is_drawn_once_but_each_binding_contingency_remains_hoverable(inputs):
    fig = cnec_price_map.figure(*inputs)
    lines = trace(fig, "market-binding CNECs")
    assert list(lines.lon[:2]) == [14.4, 15.1]
    assert pd.isna(lines.lon[2])
    rows = trace(fig, "binding rows")
    assert len(rows.lon) == 2
    assert any("Grayspire" in text for text in rows.text)
    assert any("Kestrel" in text for text in rows.text)
    assert all("not physically overloaded" not in text for text in rows.text)


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


def selected_inputs(inputs, reference="AT"):
    buses, geometries, base = inputs
    selected = cnec_market.key_of(base.constraints.iloc[0])
    rows = json.loads(FIXTURE.read_text())["data"]
    view = cnec_market.snapshot(
        cnecs.active_constraints(rows),
        cnecs.constraint_ptdfs(rows),
        cnecs.active_external_constraints(rows),
        base.prices,
        base.interval,
        selected,
        reference,
    )
    return buses, geometries, view


def test_selected_constraint_adds_signed_influence_without_replacing_prices(inputs):
    fig = cnec_price_map.figure(*selected_inputs(inputs))
    assert list(trace(fig, "published day-ahead price").marker.color) == [50.0, 50.0, 70.0, 70.0]
    influence = trace(fig, "contribution relative to AT")
    by_text = dict(zip(influence.text, influence.marker.color))
    assert any("BE · +2.87 €/MWh" in text for text in by_text)


def test_influence_radiates_from_the_cnec_to_zones_not_over_grid_branches(inputs):
    fig = cnec_price_map.figure(*selected_inputs(inputs))
    belgium = trace(fig, "BE contribution")
    assert list(belgium.lon) == pytest.approx([14.75, 4.5])
    assert list(belgium.lat) == pytest.approx([46.45, 50.85])
    assert "not a power-flow path" in fig.layout.annotations[0].text
    assert "relative to <b>AT</b>" in fig.layout.annotations[0].text


def test_reference_change_changes_the_sign_without_touching_the_price_layer(inputs):
    fig = cnec_price_map.figure(*selected_inputs(inputs, reference="BE"))
    influence = trace(fig, "contribution relative to BE")
    values = dict(zip(influence.text, influence.marker.color))
    austrian = next(text for text in values if text.startswith("AT ·"))
    assert "-2.87 €/MWh" in austrian
    assert values[austrian] == cnec_price_map.NEGATIVE


def test_unmapped_selected_row_keeps_zonal_contributions_but_has_no_rays(inputs):
    buses, geometries, view = selected_inputs(inputs)
    geometries = geometries.assign(
        x0=None, y0=None, x1=None, y1=None, match_status="no_branch"
    ).pipe(CnecGeometries.validate)
    fig = cnec_price_map.figure(buses, geometries, view)
    assert trace(fig, "contribution relative to AT") is not None
    assert not any(item.name.endswith(" contribution") for item in fig.data)
    assert "rays cannot be anchored" in fig.layout.annotations[0].text
