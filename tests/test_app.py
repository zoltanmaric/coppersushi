from dash import dcc, no_update
import json
import pandas as pd
import pytest
from dash.exceptions import PreventUpdate

import app
from coppersushi import REPO, cnec_page, cnecs
from coppersushi.data_sources import jao, osm_locator
from tests.test_cnec_page import inputs


def test_failed_load_becomes_banner(monkeypatch):
    def broken():
        raise RuntimeError("networks/x.nc is a Git LFS pointer; run `git lfs pull`")

    monkeypatch.setitem(app.NETWORK_LOADERS, "broken", broken)
    fig, *_, message, is_open = app.render("/broken", 0, slider_moved=False)
    assert fig is no_update
    assert is_open and "git lfs pull" in message


def test_a_cnec_path_opens_the_price_page_on_its_day():
    assert app.is_cnec_path("/cnec/2024-08-29")
    assert app.cnec_day_from_path("/cnec/2024-08-29") == "2024-08-29"
    assert app.cnec_day_from_path("/cnec") is None
    assert not app.is_cnec_path("/opf-2024")


def test_the_cnec_link_names_no_day_so_the_page_opens_on_today(monkeypatch):
    monkeypatch.setattr(app, "mapbox_token", lambda: "token")
    links = (c for c in _components(app.app.layout) if isinstance(c, dcc.Link))
    assert next(link for link in links if link.children == "Prices and binding CNECs").href == "/cnec"
    controls = {component.id: component for component in _ids(app.show_page("/cnec"))}
    assert controls["cnec-date"].value == cnec_page.local_today()


def test_each_route_gets_only_its_own_controls(monkeypatch):
    monkeypatch.setattr(app, "mapbox_token", lambda: "token")
    network = {component.id for component in _ids(app.show_page("/opf-2024"))}
    cnec = {component.id for component in _ids(app.show_page("/cnec/2024-08-29"))}
    assert {"map", "snapshot-slider"} <= network
    assert {"cnec-map", "cnec-interval", "cnec-status"} <= cnec
    assert not network & cnec


def test_a_failed_cnec_day_becomes_banner(monkeypatch):
    def broken(day):
        raise RuntimeError("no JAO domain day cached")

    monkeypatch.setattr(app, "cnec_day", broken)
    *outputs, message, is_open = app.render_cnec("2024-08-29", 0, None, "AT")
    assert all(output is no_update for output in outputs)
    assert is_open and "no JAO domain day cached" in message


def test_cnec_retry_draws_new_endpoints_without_reloading_the_day(tmp_path, monkeypatch):
    day = inputs()
    monkeypatch.setattr(app, "cnec_day", lambda _: day)
    monkeypatch.setattr(app, "mapbox_token", lambda: "token")
    monkeypatch.setattr(app, "basemap", lambda: "dark")
    monkeypatch.setattr(jao, "JAO_DIR", tmp_path)
    located = pd.read_csv(REPO / "tests/fixtures/cnec-price-map/located-substations.csv")
    monkeypatch.setattr(osm_locator, "read_csvs", lambda: located)
    monkeypatch.setattr(osm_locator, "load_aliases", lambda: {})

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(jao, "_get", offline)
    *_, message, is_open = app.update_cnec("2024-08-29", 0, None, "AT", {"day": "2024-08-29"})
    assert is_open and "Please retry" in message
    fc = json.loads((REPO / "tests/fixtures/synthetic-jao/final-computation-hour.json").read_text())["data"]
    calls = []

    def fetch(*args, **kwargs):
        calls.append(args)
        return fc

    monkeypatch.setattr(jao, "_get", fetch)
    figure, *_, message, is_open = app.update_cnec("2024-08-29", 0, None, "AT", {"day": "2024-08-29"})
    assert not is_open and message == ""
    assert "2 of 2 active rows mapped" in figure.layout.annotations[0].text
    assert len(calls) == 1
    app.update_cnec("2024-08-29", 0, "1", "BE", {"day": "2024-08-29"})
    assert len(calls) == 1


def test_only_the_viewed_intervals_missing_elements_are_fetched(monkeypatch):
    day = inputs()
    seen = []
    fc = json.loads((REPO / "tests/fixtures/synthetic-jao/final-computation-hour.json").read_text())["data"]

    def load(interval, required):
        seen.append((interval, required))
        return cnecs.element_ends(fc)

    monkeypatch.setattr(jao, "load_element_ends", load)
    monkeypatch.setattr(osm_locator, "read_csvs", lambda: pd.read_csv(
        REPO / "tests/fixtures/cnec-price-map/located-substations.csv"
    ))
    monkeypatch.setattr(osm_locator, "load_aliases", lambda: {})
    app.cnec_geometries(day, 1)
    assert seen[0][0] == pd.Timestamp("2024-08-28T23:00:00Z")
    assert seen[0][1].empty  # The day's binding rows belong to the preceding hour.


def _components(component):
    """Every component in a layout tree, depth first."""
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    for child in children if isinstance(children, list) else [children]:
        yield from _components(child)


def _ids(component):
    """Every component in a layout tree that carries an id."""
    return (c for c in _components(component) if getattr(c, "id", None))


def test_loading_failure_reaches_the_banner_without_fetching_prices(monkeypatch):
    def unavailable(day):
        raise OSError("constraints unavailable")

    monkeypatch.setattr(jao, "load_active_day", unavailable)
    monkeypatch.setattr(app.electricity_maps, "load_day", lambda day: pytest.fail("price fetch after failure"))
    active = app.load_cnec_constraints("2024-08-29", 1)
    ready = app.load_cnec_prices(active, "2024-08-29")
    *_, message, is_open = app.update_cnec("2024-08-29", 0, None, "AT", ready)
    assert is_open and "constraints unavailable" in message
    assert ready["request"] == 1


def test_a_previous_days_completion_cannot_load_or_draw_the_selected_day(monkeypatch):
    monkeypatch.setattr(app.electricity_maps, "load_day", lambda day: pytest.fail("stale price fetch"))
    monkeypatch.setattr(app, "render_cnec", lambda *args: pytest.fail("stale map"))
    stale = {"day": "2024-08-29", "request": 0}
    with pytest.raises(PreventUpdate):
        app.load_cnec_prices(stale, "2024-08-30")
    with pytest.raises(PreventUpdate):
        app.update_cnec("2024-08-30", 0, None, "AT", stale)
