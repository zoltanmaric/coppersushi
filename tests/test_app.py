from dash import dcc, html, no_update
import json
import pandas as pd
import pytest
from dash.exceptions import PreventUpdate

import app
from coppersushi.market_day import MarketDay
from coppersushi import REPO, cnec_page, cnecs
from coppersushi.data_sources import jao, osm_locator
from tests.test_cnec_page import inputs, mapped_elements


@pytest.fixture(autouse=True)
def synthetic_catalog(monkeypatch):
    monkeypatch.setenv('COPPERSUSHI_ELEMENT_CATALOG', str(REPO/'tests/fixtures/element-catalog'))


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
    monkeypatch.setattr(app, "basemap", lambda: {"version": 8, "sources": {}, "layers": []})
    links = (c for c in _components(app.show_page("/opf-2024")) if isinstance(c, html.A))
    assert next(link for link in links if link.children == "Prices and binding CNECs").href == "/cnec"
    controls = {component.id: component for component in _ids(app.show_page("/cnec"))}
    assert controls["cnec-view"].default_day == cnec_page.local_today()


def test_each_route_gets_only_its_own_controls(monkeypatch):
    monkeypatch.setattr(app, "mapbox_token", lambda: "token")
    monkeypatch.setattr(app, "basemap", lambda: {"version": 8, "sources": {}, "layers": []})
    network = {component.id for component in _ids(app.show_page("/opf-2024"))}
    cnec = {component.id for component in _ids(app.show_page("/cnec/2025-11-05"))}
    assert {"map", "snapshot-slider"} <= network
    assert {"cnec-view"} <= cnec
    assert not network & cnec




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
    unavailable = app.render_cnec(MarketDay.on("2024-08-29"), 0, None)
    assert len(next(t for t in unavailable.figure.data if t.name == "binding line ends").lon) == 0
    assert [option["value"] for option in unavailable.constraint_options] == ["", "1", "2"]
    fc = json.loads((REPO / "tests/fixtures/synthetic-jao/final-computation-hour.json").read_text())["data"]
    calls = []

    def fetch(*args, **kwargs):
        calls.append(args)
        return fc

    monkeypatch.setattr(jao, "_get", fetch)
    result = app.render_cnec(MarketDay.on("2024-08-29"), 0, None)
    assert len(next(t for t in result.figure.data if t.name == "binding line ends").lon) > 0
    assert len(calls) == 1
    app.render_cnec(MarketDay.on("2024-08-29"), 0, "1")
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
    assert not seen  # An interval with no binding rows needs no endpoint discovery.
    app.cnec_geometries(day, 0)
    assert seen[0][0] == pd.Timestamp("2024-08-28T22:00:00Z")
    assert not seen[0][1].empty


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






@pytest.mark.parametrize("mode", ['embed', 'full'])
def test_root_rollout_keeps_permanent_urls_stable(mode, monkeypatch):
    monkeypatch.setattr(app, "mapbox_token", lambda: "token")
    monkeypatch.setattr(app, "basemap", lambda: {"version": 8, "sources": {}, "layers": []})
    assert app.is_embed_path('/', mode) is (mode == 'embed')
    assert app.is_embed_path('/embed/opf-2024', mode)
    assert not app.is_embed_path('/opf-2024', mode)
    assert app.network_key_from_path('/') == app.network_key_from_path('/embed/opf-2024') == 'opf-2024'
    for path in ['/', '/embed/opf-2024', '/opf-2024']:
        page = app.show_page(path, root_view=mode)
        links = [c.href for c in _components(page) if isinstance(c, html.A)]
        assert links == ([] if app.is_embed_path(path, mode) else ['/opf-2024', '/cnec'])
        assert {'map', 'snapshot-slider', 'opf-time'} <= {c.id for c in _ids(page)}


@pytest.mark.parametrize('path', ['/v1', '/opf-2013', '/missing'])
def test_retired_or_unknown_views_do_not_fall_back_to_any_model(path):
    assert app.network_key_from_path(path) is None
    assert not {'map', 'snapshot-slider'} & {c.id for c in _ids(app.show_page(path))}
    with pytest.raises(PreventUpdate):
        app.render(path, 0, False)
    assert 'v1' not in app.NETWORK_LOADERS and 'opf-2013' not in app.NETWORK_LOADERS


def test_opf_clock_and_slider_share_the_local_day_and_noon_default():
    table = pd.read_csv(REPO / 'tests/fixtures/opf-embed/snapshots.csv')
    snapshots = pd.DatetimeIndex(pd.to_datetime(table.snapshot, utc=True))
    maximum, marks, selected, label = app.opf_snapshot_state(snapshots, 0, False)
    assert maximum == 3 and selected == 3
    assert label == '29 Aug 2024 · 12:00 CEST'
    assert [marks[i]['label'] for i in range(4)] == ['00:00', ' ', ' ', '12:00']
    assert app.opf_snapshot_state(snapshots, 1, True)[-1] == '29 Aug 2024 · 01:00 CEST'

    # NetCDF snapshots are naive UTC; they must give the same local clock.
    assert app.opf_snapshot_state(snapshots.tz_localize(None), 1, True) == app.opf_snapshot_state(snapshots, 1, True)


def test_page_shell_does_not_load_the_opf_runtime():
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-c', "import sys, app; assert 'pypsa' not in sys.modules; assert app.server.test_client().get('/').status_code == 200"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_base_day_does_not_fetch_attribution(monkeypatch):
    from types import SimpleNamespace
    day = inputs()
    monkeypatch.setattr(app, '_cnec_days', {})
    monkeypatch.setattr(app, 'core_zones', lambda: day.zones)
    monkeypatch.setattr(jao, 'load_active_day', lambda _: SimpleNamespace(
        constraints=day.constraints, ptdfs=day.ptdfs))
    monkeypatch.setattr(app.electricity_maps, 'load_day', lambda _: day.prices)
    from coppersushi.data_sources import cnec_attribution
    monkeypatch.setattr(cnec_attribution, 'load_day', lambda _: pytest.fail('blocking enrichment'))
    assert app.cnec_day(MarketDay.on('2024-08-29')).context is None










@pytest.mark.parametrize("context_file", ["historical-context.csv", "missing-context.csv"])
def test_browser_enrichment_roundtrip_preserves_contributions(monkeypatch, context_file):
    from dataclasses import replace
    day = inputs()
    fixtures = REPO / 'tests/fixtures/cnec-attribution'
    context = pd.read_csv(fixtures / context_file).assign(
        interval=lambda f: pd.to_datetime(f.interval, utc=True))
    polish_price = pd.read_csv(fixtures / 'polish-price.csv').assign(
        interval=lambda f: pd.to_datetime(f.interval, utc=True))
    day = replace(day, context=context, prices=pd.concat([day.prices, polish_price]))
    attribution = {'day': '2024-08-29', 'complete': False,
                   'rows': json.loads(day.context.to_json(orient='records', date_format='iso'))}
    monkeypatch.setattr(app, 'cnec_day', lambda _: replace(day, context=None))
    monkeypatch.setattr(app, 'cnec_geometries', lambda *_: mapped_elements())
    monkeypatch.setattr(app, 'mapbox_token', lambda: None)
    monkeypatch.setattr(app, 'basemap', lambda: 'white-bg')
    result = app.render_cnec(MarketDay.on('2024-08-29'), 0, '1', app.AttributionPayload.model_validate(attribution))
    expected = cnec_page.render(day, mapped_elements(), 0, '1', basemap='white-bg')
    assert result.figure.to_json() == expected.figure.to_json()







def test_missing_render_interval_does_not_default_to_midnight(monkeypatch):
    monkeypatch.setattr(app, "cnec_day", lambda _: inputs())
    with pytest.raises(TypeError):
        app.render_cnec(MarketDay.on("2024-08-29"), None, None)


def test_cnec_mount_uses_react_component_and_has_no_loading_callback_chain(monkeypatch):
    monkeypatch.setattr(app, 'mapbox_token', lambda: 'token')
    monkeypatch.setattr(app, 'basemap', lambda: {'version': 8, 'sources': {}, 'layers': []})
    page = app.show_page('/cnec/2025-11-05')
    view = next(c for c in _components(page) if getattr(c, 'id', None) == 'cnec-view')
    assert view.to_plotly_json() == {
        'namespace': 'coppersushi_cnec', 'type': 'CnecView',
        'props': {'id': 'cnec-view', 'default_day': cnec_page.local_today(), 'min_day': '2025-11-05', 'token': 'token', 'basemap': {'version': 8, 'sources': {}, 'layers': [], 'sprite': '/assets/cnec-markers'}},
    }
    dependencies = app.server.test_client().get('/_dash-dependencies').json
    assert all('cnec-' not in callback['output'] for callback in dependencies)


def test_unsupported_cnec_dates_redirect_to_undated_view():
    client = app.server.test_client()
    response = client.get('/cnec/2025-11-04')
    assert response.status_code == 302
    assert response.headers['Location'] == '/cnec'
    assert client.get('/cnec/2025-11-05').status_code == 200
    redirect_component = app.show_page('/cnec/2025-11-04').children
    assert redirect_component.href == '/cnec'
    assert not app.unsupported_cnec_path('/opf-2024')


def test_cnec_date_navigation_keeps_the_react_page_mounted():
    assert app.route_page('/cnec/2026-11-03', 'cnec') == (app.no_update, app.no_update)
    assert app.route_page('/cnec/2026-11-04', 'cnec') == (app.no_update, app.no_update)
