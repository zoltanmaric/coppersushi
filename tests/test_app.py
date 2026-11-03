from dash import dcc, no_update
import json
import pandas as pd
import pytest
from dash.exceptions import PreventUpdate

import app
from coppersushi import REPO, cnec_page, cnecs
from coppersushi.data_sources import jao, osm_locator
from tests.test_cnec_page import inputs, mapped_elements


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
    links = (c for c in _components(app.show_page("/opf-2024")) if isinstance(c, dcc.Link))
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
    result = app.cnec_outputs(app.render_cnec("2024-08-29", 0, None))
    outputs, (message, is_open) = result[:6], result[6:8]
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
    result = app.render_cnec("2024-08-29", 0, None)
    assert result.view is None and "Please retry" in result.error
    fc = json.loads((REPO / "tests/fixtures/synthetic-jao/final-computation-hour.json").read_text())["data"]
    calls = []

    def fetch(*args, **kwargs):
        calls.append(args)
        return fc

    monkeypatch.setattr(jao, "_get", fetch)
    result = app.render_cnec("2024-08-29", 0, None)
    figure = result.view.figure
    assert result.error == ""
    assert "2 of 2 active rows mapped" in figure.layout.annotations[0].text
    assert len(calls) == 1
    app.render_cnec("2024-08-29", 0, "1")
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
    result = app.open_cnec(ready, "2024-08-29", 1)
    message, is_open = result[6:8]
    assert is_open and "constraints unavailable" in message
    assert ready["request"] == 1


def test_a_previous_days_completion_cannot_load_or_draw_the_selected_day(monkeypatch):
    monkeypatch.setattr(app.electricity_maps, "load_day", lambda day: pytest.fail("stale price fetch"))
    monkeypatch.setattr(app, "render_cnec", lambda *args: pytest.fail("stale map"))
    stale = {"day": "2024-08-29", "request": 0}
    with pytest.raises(PreventUpdate):
        app.load_cnec_prices(stale, "2024-08-30")
    with pytest.raises(PreventUpdate):
        app.open_cnec(stale, "2024-08-30", 0)


@pytest.mark.parametrize("mode", ['embed', 'full'])
def test_root_rollout_keeps_permanent_urls_stable(mode, monkeypatch):
    monkeypatch.setattr(app, "mapbox_token", lambda: "token")
    assert app.is_embed_path('/', mode) is (mode == 'embed')
    assert app.is_embed_path('/embed/opf-2024', mode)
    assert not app.is_embed_path('/opf-2024', mode)
    assert app.network_key_from_path('/') == app.network_key_from_path('/embed/opf-2024') == 'opf-2024'
    for path in ['/', '/embed/opf-2024', '/opf-2024']:
        page = app.show_page(path, root_view=mode)
        links = [c.href for c in _components(page) if isinstance(c, dcc.Link)]
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
        constraints=day.constraints, ptdfs=day.ptdfs, external_constraints=day.external_constraints))
    monkeypatch.setattr(app.electricity_maps, 'load_day', lambda _: day.prices)
    monkeypatch.setattr(app.attribution_source, 'load_day', lambda _: pytest.fail('blocking enrichment'))
    assert app.cnec_day('2024-08-29').context is None


def test_enrichment_waits_for_base_map_and_is_scoped_to_retry(monkeypatch):
    day = '2024-08-29'
    token = {'day': day, 'request': 0}
    calls = []
    monkeypatch.setattr(app.attribution_source, 'load_day', lambda d: calls.append(d) or inputs().context)
    with pytest.raises(PreventUpdate):
        app.load_cnec_attribution(None, day, 0)
    with pytest.raises(PreventUpdate):
        app.load_cnec_attribution(token, day, 1)
    assert not calls
    result = app.load_cnec_attribution(token, day, 0)
    assert result['rows'] and calls == [day]
    # Returning to the same day must enrich its newly opened base map again.
    assert app.load_cnec_attribution(token, day, 0)["rows"] == result["rows"]
    next_token = {'day': day, 'request': 1}
    assert app.load_cnec_attribution(next_token, day, 1)['request'] == 1
    assert len(calls) == 3


def test_enrichment_preserves_current_interval_and_selection(monkeypatch):
    token = {'day': '2024-08-29', 'request': 2}
    attribution = {**token, 'rows': json.loads(inputs().context.to_json(orient='records', date_format='iso'))}
    seen = []
    view = cnec_page.render(inputs(), mapped_elements(), 0, None)
    monkeypatch.setattr(app, 'render_cnec', lambda *args: seen.append(args) or app.CnecRender(view))
    result = app.enrich_cnec(attribution, token['day'], 2, 7, '42', token)
    assert seen == [(token['day'], 7, '42', attribution)]
    assert result['figure'] is view.figure
    assert result['options'] == view.constraint_options
    assert (result['interval'], result['selected']) == (7, '42')
    for stale in [{**attribution, 'day': '2024-08-30'}, {**attribution, 'request': 1}]:
        with pytest.raises(PreventUpdate):
            app.enrich_cnec(stale, token['day'], 2, 7, '42', token)
    assert len(seen) == 1


def test_enrichment_failure_leaves_base_map_usable_and_retryable(monkeypatch):
    from types import SimpleNamespace
    token = {'day': '2024-08-29', 'request': 0}
    def offline(_):
        raise OSError('offline')
    monkeypatch.setattr(app.attribution_source, 'load_day', offline)
    failed = app.load_cnec_attribution(token, token['day'], 0)
    assert failed == {**token, 'complete': False, 'error': 'Attribution failed: offline'}
    with pytest.raises(PreventUpdate):
        app.enrich_cnec(failed, token['day'], 0, 0, None, token)
    monkeypatch.setattr(app, 'ctx', SimpleNamespace(triggered_id='cnec-next'))
    seen = []
    monkeypatch.setattr(app, 'render_cnec', lambda *args: seen.append(args) or app.CnecRender(None, 'unavailable'))
    app.update_cnec(None, 0, 1, 0, None, failed, token['day'], token, [], token, 0)
    assert seen[0][1] == 1
    monkeypatch.setattr(app.attribution_source, 'load_day', lambda _: inputs().context)
    assert 'rows' in app.load_cnec_attribution({**token, 'request': 1}, token['day'], 1)


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
    attribution = {'day': '2024-08-29', 'request': 0, 'complete': False,
                   'rows': json.loads(day.context.to_json(orient='records', date_format='iso'))}
    monkeypatch.setattr(app, 'cnec_day', lambda _: replace(day, context=None))
    monkeypatch.setattr(app, 'cnec_geometries', lambda *_: mapped_elements())
    monkeypatch.setattr(app, 'mapbox_token', lambda: None)
    monkeypatch.setattr(app, 'basemap', lambda: 'white-bg')
    result = app.render_cnec('2024-08-29', 0, '1', attribution)
    expected = cnec_page.render(day, mapped_elements(), 0, '1', basemap='white-bg')
    assert result.error == ""
    assert result.view.figure.to_json() == expected.figure.to_json()


def test_enrichment_render_error_reaches_browser_with_selection_scope(monkeypatch):
    token = {'day': '2024-08-29', 'request': 0}
    payload = {**token, 'rows': json.loads(inputs().context.to_json(orient='records', date_format='iso'))}
    monkeypatch.setattr(app, 'render_cnec', lambda *args: app.CnecRender(None, 'render failed'))
    assert app.enrich_cnec(payload, token['day'], 0, 3, '42', token) == {
        **token, 'interval': 3, 'selected': '42', 'error': 'render failed',
    }


def test_browser_enrichment_displays_only_current_render_errors():
    import re
    import subprocess
    source = (REPO / 'app.py').read_text()
    callback = re.search(r'"""(function\(view, day, retries, interval, selected\).*?)"""', source, re.S).group(1)
    script = 'const apply = ' + callback + ';\n' + '''
        const assert = require('node:assert/strict');
        global.window = {dash_clientside: {no_update: 'unchanged'}};
        const view = {day: '2024-08-29', request: 1, interval: 3, selected: '42', error: 'render failed'};
        assert.deepEqual(apply(view, view.day, 1, 3, '42'),
                         ['unchanged', 'unchanged', 'unchanged', 'render failed', true]);
        for (const args of [['2024-08-30', 1, 3, '42'], [view.day, 2, 3, '42'],
                            [view.day, 1, 4, '42'], [view.day, 1, 3, '43']]) {
            assert.deepEqual(apply(view, ...args), Array(5).fill('unchanged'));
        }
        const success = {...view, error: undefined, figure: {}, options: [], reference: 'Reference: DE'};
        assert.deepEqual(apply(success, view.day, 1, 3, '42'), [{}, [], 'Reference: DE', '', false]);
    '''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)
