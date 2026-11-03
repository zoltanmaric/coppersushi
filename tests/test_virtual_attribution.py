"""Pure endpoint arithmetic and gates, with synthetic inputs and no mocks or network."""

import json

import pandas as pd
import pytest

from coppersushi import REPO, cnec_attribution as attribution, cnec_market, cnec_price_map
from tests.test_cnec_attribution import page_inputs

FIXTURES = REPO / 'tests/fixtures/cnec-attribution'
CASES = json.loads((FIXTURES / 'virtual-endpoints.json').read_text())
INTERVAL = pd.Timestamp('2026-09-11T22:00:00Z')


@pytest.mark.parametrize('case', CASES, ids=[c['hub'] for c in CASES])
def test_all_new_interfaces_accept_independent_terms_and_reject_unexplained_spreads(case):
    physical, ptdfs, external, prices, inputs = [pd.DataFrame(case[k]).assign(interval=INTERVAL) for k in ['physical', 'ptdfs', 'external', 'prices', 'inputs']]
    adjacent = pd.Series(case['adjacent'])
    assert attribution.interface_spread(1.6, 10.0, adjacent.adjacent_term,
                                       20.0 if case['owner'] == 'PL' else 0.0) == pytest.approx(case['spread'])
    valid = attribution.virtual_validated(case['hub'], ptdfs, physical, external, prices, inputs, .5, adjacent)
    assert valid is (case['hub'] not in attribution.LOSS_HUBS)
    export = external.assign(coefficient=-1.0)
    export_quote = adjacent.copy()
    export_quote.adjacent_price = case['export_adjacent_price']
    assert attribution.virtual_validated(case['hub'], ptdfs, physical, export, prices, inputs, .5, export_quote) is valid
    if case['owner'] == 'PL':
        slack = inputs.assign(polish_position=0.0)
        assert not attribution.virtual_validated(case['hub'], ptdfs, physical, external, prices, slack, .5, adjacent)
    wrong_price = adjacent.copy()
    wrong_price.adjacent_price += 1.0
    assert not attribution.virtual_validated(case['hub'], ptdfs, physical, external, prices, inputs, .5, wrong_price)
    assert not attribution.virtual_validated(case['hub'], ptdfs.iloc[:1], physical, external, prices, inputs, .5, adjacent)
    assert not attribution.virtual_validated(case['hub'], ptdfs, physical, external, prices, inputs, 0, adjacent)


@pytest.mark.parametrize('hub', list(attribution.NORDIC_HUBS))
def test_nordic_outer_term_keeps_sign_and_requires_correct_interval_and_coefficients(hub):
    rows = json.loads((FIXTURES / 'nordic.json').read_text())
    assert attribution.nordic_outer_term(rows, hub, INTERVAL) == pytest.approx(-2.0)
    with pytest.raises(ValueError, match="requested interval"):
        attribution.nordic_outer_term(rows, hub, INTERVAL + pd.Timedelta(minutes=15))
    del rows[0]['ptdf_' + attribution.NORDIC_HUBS[hub]]
    with pytest.raises(ValueError, match="missing columns"):
        attribution.nordic_outer_term(rows, hub, INTERVAL)


def test_validated_interface_ray_uses_selected_dual_and_retains_adjacent_price():
    case = next(c for c in CASES if c['hub'] == 'DE_DK1_VH')
    physical, ptdfs, external, prices = [pd.DataFrame(case[k]).assign(interval=INTERVAL) for k in ['physical', 'ptdfs', 'external', 'prices']]
    adjacent = pd.DataFrame([case['adjacent']]).assign(interval=INTERVAL)
    view = cnec_market.snapshot(physical, ptdfs, external, prices, INTERVAL,
                               cnec_market.ConstraintKey(201), alpha=.5, adjacent=adjacent)
    assert view.reference == case['other']
    assert view.contribution.set_index('zone').contribution[case['owner']] == 10.0
    assert case['spread'] != 10.0
    assert view.prices.set_index('zone').price[case['other']] == pytest.approx(case['adjacent']['adjacent_price'])
    broken = adjacent.assign(adjacent_price=0.0)
    rejected = cnec_market.snapshot(physical, ptdfs, external, prices, INTERVAL,
                                   cnec_market.ConstraintKey(201), alpha=.5, adjacent=broken)
    assert rejected.selected_id == 201
    assert rejected.contribution is None

    day, mapped = page_inputs()
    drawn = view._replace(constraints=day.constraints.iloc[:0], prices=pd.concat([
        day.prices[day.prices.interval.eq(INTERVAL) & ~day.prices.zone.eq(case['owner'])], view.prices], ignore_index=True))
    figure = cnec_price_map.figure(day.zones, mapped, drawn)
    assert any(trace.name == case['owner'] + ' ray' for trace in figure.data)
    label = next(trace for trace in figure.data if trace.name == 'adjacent zone price')
    assert list(label.text) == ['DK1<br>€90.40']
    ray = next(trace for trace in figure.data if trace.name == case['owner'] + ' ray')
    assert 'Total observed spread: +9.60' in ray.hovertext
    assert 'contribution: +10.00' in ray.hovertext
    export = cnec_market.snapshot(physical, ptdfs, external.assign(coefficient=-1.0), prices, INTERVAL,
                                 cnec_market.ConstraintKey(201), alpha=.5,
                                 adjacent=adjacent.assign(adjacent_price=case['export_adjacent_price']))
    assert export.reference == case['owner']
    assert export.contribution.set_index('zone').contribution[case['other']] == 10.0


def test_adjacent_loader_distinguishes_unavailable_data_from_failure(monkeypatch, tmp_path):
    from coppersushi.data_sources import virtual_attribution as source
    from coppersushi.data_model.cnec_attribution import AdjacentUnavailable
    from coppersushi.market_day import MarketDay

    monkeypatch.setattr(source.jao, "JAO_DIR", tmp_path)
    monkeypatch.setattr(source.cache, "restore", lambda *args: False)
    day = MarketDay.containing(INTERVAL)
    assert isinstance(source.load_interval(day, INTERVAL, "ALBE"), AdjacentUnavailable)
    monkeypatch.setattr(source.jao, "_get", lambda *args, **kwargs: [])
    absent = source.load_interval(day, INTERVAL, "DE_DK1_VH")
    assert isinstance(absent, AdjacentUnavailable)
    assert "unavailable" in absent.reason
    assert not list(tmp_path.rglob("*.json"))

    def offline(*args, **kwargs):
        raise OSError("Nordic feed offline")

    monkeypatch.setattr(source.jao, "_get", offline)
    with pytest.raises(OSError, match="Nordic feed offline"):
        source.load_interval(day, INTERVAL, "DE_DK1_VH")


def test_adjacent_loader_returns_a_validated_table(monkeypatch, tmp_path):
    from coppersushi.data_sources import virtual_attribution as source
    from coppersushi.data_model.cnec_attribution import AdjacentAttribution
    from coppersushi.market_day import MarketDay

    rows = json.loads((FIXTURES / "nordic.json").read_text())
    case = next(c for c in CASES if c["hub"] == "DE_DK1_VH")
    prices = pd.DataFrame(case["prices"]).assign(interval=INTERVAL)
    monkeypatch.setattr(source.jao, "JAO_DIR", tmp_path)
    monkeypatch.setattr(source.cache, "restore", lambda *args: False)
    monkeypatch.setattr(source.cache, "publish", lambda *args: None)
    monkeypatch.setattr(source.jao, "_get", lambda *args, **kwargs: rows)
    monkeypatch.setattr(source, "_prices", lambda *args: prices)
    result = source.load_interval(MarketDay.containing(INTERVAL), INTERVAL, "DE_DK1_VH")
    assert isinstance(result, pd.DataFrame)
    AdjacentAttribution.validate(result)
    assert result.adjacent_term.iloc[0] == pytest.approx(-2.0)


def test_unavailable_adjacent_reason_is_visible():
    from coppersushi.data_model.cnec_attribution import AdjacentUnavailable

    case = next(c for c in CASES if c["hub"] == "DE_DK1_VH")
    physical, ptdfs, external, prices = [pd.DataFrame(case[k]).assign(interval=INTERVAL)
                                      for k in ["physical", "ptdfs", "external", "prices"]]
    result = cnec_market.snapshot(physical, ptdfs, external, prices, INTERVAL,
        cnec_market.ConstraintKey(201), alpha=.5, adjacent=AdjacentUnavailable("Publication pending"))
    assert result.contribution is None
    assert result.note == "Publication pending"
