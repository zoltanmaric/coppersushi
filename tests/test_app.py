from dash import html, no_update
import pandas as pd
import pytest
from dash.exceptions import PreventUpdate

import app
from coppersushi import REPO


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


def test_the_cnec_link_names_no_day_so_the_page_opens_on_today(monkeypatch):
    monkeypatch.setattr(app, "mapbox_token", lambda: "token")
    links = (c for c in _components(app.show_page("/opf-2024")) if isinstance(c, html.A))
    assert next(link for link in links if link.children == "Prices and binding CNECs").href == "/cnec"


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


def test_unsupported_cnec_dates_redirect_to_undated_view(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "test-public-token")
    client = app.server.test_client()
    response = client.get('/cnec/2025-11-04')
    assert response.status_code == 302
    assert response.headers['Location'] == '/cnec'
    assert client.get('/cnec/2026-11-01').status_code == 200
