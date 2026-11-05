"""HTTP boundaries preserve independent layers and surface real failures."""
from types import SimpleNamespace

import pytest
from flask import Flask

import cnec_http
from coppersushi import cnec_page
from coppersushi.data_model.cnec_attribution import attribution_to_browser
from coppersushi.data_model.cnec_api import EnrichedRequest
from coppersushi.market_day import MarketDay
from tests.test_cnec_page import inputs, mapped_elements


@pytest.fixture
def client(monkeypatch):
    day = inputs()
    monkeypatch.setattr(cnec_http.jao, 'load_active_day', lambda _: SimpleNamespace(
        constraints=day.constraints))
    monkeypatch.setattr(cnec_http.electricity_maps, 'load_day', lambda _: day.prices)
    monkeypatch.setattr(cnec_http.cnec_attribution, 'load_day', lambda _: day.context)
    def render(view: EnrichedRequest):
        return cnec_page.render(day, mapped_elements(), view.interval, view.selected, basemap='white-bg')
    server = Flask(__name__)
    cnec_http.register(server, cnec_http.Services(lambda: day.zones, lambda: 'token',
        lambda: 'white-bg', lambda *_: mapped_elements(), render))
    return server.test_client()


VIEW = {'day': '2024-08-29', 'interval': 0, 'selected': None}


def test_prices_do_not_wait_for_constraints_or_attribution(client, monkeypatch):
    monkeypatch.setattr(cnec_http.jao, 'load_active_day', lambda _: pytest.fail('constraints requested'))
    monkeypatch.setattr(cnec_http.cnec_attribution, 'load_day', lambda _: pytest.fail('attribution requested'))
    result = client.post('/api/cnec/prices', json=VIEW)
    assert result.status_code == 200
    assert result.json['figure']['data'][0]['type'] == 'choroplethmapbox'


def test_constraints_do_not_wait_for_prices_or_attribution(client, monkeypatch):
    monkeypatch.setattr(cnec_http.electricity_maps, 'load_day', lambda _: pytest.fail('prices requested'))
    monkeypatch.setattr(cnec_http.cnec_attribution, 'load_day', lambda _: pytest.fail('attribution requested'))
    result = client.post('/api/cnec/constraints', json=VIEW)
    assert result.status_code == 200
    assert [o['value'] for o in result.json['options']] == ['', '1', '2']
    assert any(t['name'] == 'market-binding CNECs' for t in result.json['figure']['data'])


def test_attribution_is_fetchable_without_a_selection(client):
    result = client.get('/api/cnec/attribution/2024-08-29')
    assert result.status_code == 200 and result.json['rows']


def test_invalid_input_and_mismatched_attribution_are_rejected(client):
    assert client.post('/api/cnec/prices', json={**VIEW, 'interval': -1}).status_code == 400
    assert client.post('/api/cnec/prices', json={**VIEW, 'interval': 24}).status_code == 400
    assert client.post('/api/cnec/prices', json={'day': VIEW['day']}).status_code == 400
    payload = attribution_to_browser(inputs().context, MarketDay.on('2024-08-30')).model_dump(mode='json')
    result = client.post('/api/cnec/enriched', json={**VIEW, 'attribution': payload})
    assert result.status_code == 400 and 'another market day' in result.json['error']


def test_loader_failure_is_an_error_not_an_empty_layer(client, monkeypatch):
    def broken(_):
        raise RuntimeError('publisher unavailable')
    monkeypatch.setattr(cnec_http.electricity_maps, 'load_day', broken)
    result = client.post('/api/cnec/prices', json=VIEW)
    assert result.status_code == 500 and result.json == {'error': 'publisher unavailable'}


def test_clock_change_day_preserves_both_repeated_hours(client):
    result = client.get('/api/cnec/day/2026-10-25')
    assert result.status_code == 200
    assert len(result.json['labels']) == 100
    assert any('02:00 CEST' in label for label in result.json['labels'])
    assert any('02:00 CET' in label for label in result.json['labels'])


@pytest.mark.parametrize("content_type,body,status", [
    (None, None, 415),
    ("text/plain", "hello", 415),
    ("application/json", "{broken", 400),
])
def test_json_boundary_preserves_http_errors(content_type, body, status):
    from flask import request
    from coppersushi.data_model.cnec_api import ApiError

    server = Flask(__name__)

    @server.post('/json')
    @cnec_http.json_endpoint
    def json_input() -> ApiError:
        request.get_json()
        return ApiError(error="unreachable for invalid input")

    response = server.test_client().post('/json', data=body, content_type=content_type)
    assert response.status_code == status
    assert response.is_json
    assert response.json['error'].startswith(str(status))


def test_location_fetch_failure_keeps_known_line_and_constraint_choices(tmp_path, monkeypatch):
    from coppersushi.data_sources import element_catalog, jao, osm_locator
    from tests.test_cnec_page import inputs, mapped_elements
    from coppersushi import REPO
    day = inputs()
    constraints = day.constraints.copy()
    constraints.loc[constraints.index[-1], ['eic', 'name']] = ['99T-NEW', 'New unmapped line']
    monkeypatch.setattr(jao, 'JAO_DIR', tmp_path)
    def offline(*args, **kwargs):
        raise OSError('upstream unavailable')
    monkeypatch.setattr(jao, '_get', offline)
    monkeypatch.setattr(element_catalog, 'mapped_elements', lambda _: mapped_elements())
    monkeypatch.setattr(osm_locator, 'read_csvs', lambda: pytest.fail('no endpoint was discovered'))
    monkeypatch.setattr(cnec_http.jao, 'load_active_day', lambda _: SimpleNamespace(constraints=constraints))
    server = Flask(__name__)
    cnec_http.register(server, cnec_http.Services(lambda: day.zones, lambda: 'token',
        lambda: 'white-bg', lambda interval, rows: element_catalog.resolve(
            interval, rows, REPO/'tests/fixtures/element-catalog'), lambda _: None))
    result = server.test_client().post('/api/cnec/constraints', json=VIEW)
    assert result.status_code == 200
    assert [o['value'] for o in result.json['options']] == ['', '1', '2']
    assert len(next(t for t in result.json['figure']['data'] if t['name'] == 'binding line ends')['lon']) == 2
    assert any(t['name'] == 'market-binding CNECs' for t in result.json['figure']['data'])
