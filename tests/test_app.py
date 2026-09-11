import importlib
from pathlib import Path
from unittest import mock

import pytest
from dash import dcc, no_update

import app
from coppersushi import cnec_page
from coppersushi.data_sources import jao


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


def test_the_cnec_link_names_no_day_so_the_page_opens_on_today():
    links = (c for c in _components(app.app.layout) if isinstance(c, dcc.Link))
    assert next(link for link in links if link.children == "Prices and binding CNECs").href == "/cnec"
    controls = {component.id: component for component in _ids(app.show_page("/cnec"))}
    assert controls["cnec-date"].value == cnec_page.local_today()


def test_each_route_gets_only_its_own_controls():
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


def test_the_jao_day_route_renders_one_hour_of_it(monkeypatch):
    """The route composes JAO's day and hands the slider the hours to cycle it by."""
    monkeypatch.setenv("MAPBOX_TOKEN", "not-a-token")
    if not app.JAO_DAYS:  # gitignored: JAO's terms forbid redistributing its rows
        pytest.skip("no market day in data/jao; run `python -m coppersushi.data_sources.jao fetch <day>`")
    fig, maximum, marks, value, message, is_open = app.render(f"/jao/{app.JAO_DAYS[-1]}", 5, slider_moved=True)
    assert not is_open and message == ""
    assert (maximum, value) == (23, 5)  # the CET market day, an hour at a time
    visible = [index for index, trace in enumerate(fig.data) if trace.visible]
    assert visible == list(range(5 * app.jao_map.NUM_TRACES_PER_HOUR, 6 * app.jao_map.NUM_TRACES_PER_HOUR))


def test_the_app_still_imports_where_no_market_day_was_fetched():
    """`.dockerignore` drops `data/`, so the deployed image has no `data/jao` at all.

    JAO's terms forbid redistributing its rows, so that directory can never ship. Reading it
    with `iterdir` raised at import and took the whole app down with it, `/network` included.
    """
    with mock.patch.object(jao, "JAO_DIR", Path("/nonexistent/data/jao")):
        reloaded = importlib.reload(app)
    assert reloaded.JAO_DAYS == [] and reloaded.JAO_KEYS == {}
    importlib.reload(app)  # the other tests share the module
