from dash import no_update

import app


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
    *outputs, message, is_open = app.render_cnec("2024-08-29", 0)
    assert all(output is no_update for output in outputs)
    assert is_open and "no JAO domain day cached" in message


def _ids(component):
    """Every component in a layout tree that carries an id."""
    if getattr(component, "id", None):
        yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    for child in children if isinstance(children, list) else [children]:
        yield from _ids(child)
