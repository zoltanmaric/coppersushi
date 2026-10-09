"""Synthetic, public fixtures exercise attribution independently of API or private cache."""

import copy
import json

import pandas as pd
import pytest

from coppersushi import REPO, cnec_attribution as attribution, cnec_market, cnec_page, cnecs
from coppersushi.market_day import MarketDay
from tests.test_cnec_page import read_zones

FIXTURE = REPO / "tests/fixtures/cnec-attribution"


def inputs():
    return json.loads((FIXTURE / "inputs.json").read_text())


def tables():
    data = inputs()
    rows = data['active']
    prices = pd.DataFrame(data['prices'])
    prices['interval'] = pd.to_datetime(prices.interval, utc=True)
    return cnecs.active_constraints(rows), cnecs.constraint_ptdfs(rows), cnecs.active_external_constraints(rows), prices


def context(feeds=None):
    feeds = feeds or inputs()['feeds']
    return attribution.context(MarketDay.on('2026-09-12'), *feeds.values())


def test_polish_quarters_require_four_unique_ids_and_matching_positions():
    source = inputs()['feeds']
    assert context().polish_alt.iloc[:4].tolist() == [120] * 4
    assert context().polish_alt.iloc[4:].isna().all()
    bad = copy.deepcopy(source)
    bad['polish'][0]['border_PL_SDAC_NP'] = 10
    assert pd.isna(context(bad).polish_alt.iloc[0])
    bad = copy.deepcopy(source)
    bad['polish'].pop()
    assert context(bad).polish_alt.isna().all()
    bad = copy.deepcopy(source)
    bad['polish'][1]['id'] = bad['polish'][0]['id']
    assert context(bad).polish_alt.isna().all()


def test_binding_export_cap_contributes_to_all_spreads_relative_to_poland():
    phys, ptdfs, external, prices = tables()
    interval = prices.interval.iloc[0]
    caps = attribution.country_caps(context(), prices, interval)
    assert caps.source_id.tolist() == [-2]
    assert caps.delta.iloc[0] == -20
    view = cnec_market.snapshot(phys, ptdfs, external, prices, interval,
                               cnec_market.ConstraintKey(-2), context=context(), alpha=.5)
    contribution = view.contribution.set_index('zone').contribution
    assert view.reference == 'PL'
    assert contribution.PL == 0
    assert contribution.DE == 20
    slack = context().assign(polish_position=-100)
    assert attribution.country_caps(slack, prices, interval).empty
    no_dual = prices.copy()
    no_dual.loc[no_dual.zone.eq('PL'), 'price'] = 120
    assert attribution.country_caps(context(), no_dual, interval).empty


def test_import_cap_sign_and_capacity():
    *_, prices = tables()
    data = context().assign(polish_position=-200, polish_alt=80)
    caps = attribution.country_caps(data, prices, prices.interval.iloc[0])
    assert caps.source_id.tolist() == [-1]
    assert caps.capacity.iloc[0] == 200
    assert caps.delta.iloc[0] == 20


@pytest.mark.parametrize('alpha', [.1, .5, 1])
def test_normalized_physical_contribution_scales_and_changes_reference_without_changing_spread(alpha):
    phys, ptdfs, *_ = tables()
    be = cnecs.price_contributions(phys.iloc[0], ptdfs, 'BE', alpha).set_index('zone').contribution
    de = cnecs.price_contributions(phys.iloc[0], ptdfs, 'DE', alpha).set_index('zone').contribution
    assert be.DE == pytest.approx(5 / alpha)
    assert de.BE == pytest.approx(-5 / alpha)
    for z in be.index:
        assert be[z] - be.DE == pytest.approx(de[z])


def test_alegro_paired_bounds_and_observed_spread_validate_independent_terms():
    phys, ptdfs, external, prices = tables()
    assert attribution.alegro_validated(ptdfs, phys, external, prices, .5)
    assert set(external.source_id) == {12, 13}
    for identity, expected in [(12, 5), (13, 3)]:
        view = cnec_market.snapshot(phys, ptdfs, external, prices, prices.interval.iloc[0],
                                   cnec_market.ConstraintKey(identity), alpha=.5)
        assert view.reference == 'BE'
        assert view.contribution.set_index('zone').contribution.DE == expected
    flipped = external.copy()
    flipped.loc[flipped.source_id.eq(13), 'coefficient'] = 1
    assert not attribution.alegro_validated(ptdfs, phys, flipped, prices, .5)
    bad_prices = prices.copy()
    bad_prices.loc[bad_prices.zone.eq('DE'), 'price'] += 1
    assert not attribution.alegro_validated(ptdfs, phys, external, bad_prices, .5)
    assert not attribution.alegro_validated(ptdfs, phys, external, prices, 0)


def test_reference_follows_publisher_direction_and_missing_geometry_stays_unavailable():
    phys, *_ = tables()
    mapped = pd.read_csv(FIXTURE / 'mapped.csv')
    row = phys.iloc[0]
    assert attribution.physical_reference(row, mapped, read_zones()) == 'BE'
    opposite = row.copy()
    opposite['direction'] = 'OPPOSITE'
    assert attribution.physical_reference(opposite, mapped, read_zones()) == 'DE'
    assert attribution.physical_reference(row, mapped.iloc[:0], read_zones()) is None


def test_click_ignores_unrelated_or_stale_ids_and_preserves_selected_contingency():
    options = [{'value': ''}, {'value': '12'}, {'value': '13'}]
    click = {'points': [{'customdata': ['12,13']}]}
    assert cnec_page.clicked_selection(click, options, None) == '12'
    assert cnec_page.clicked_selection(click, options, '13') == '13'
    assert cnec_page.clicked_selection(click, [{'value': ''}], None) is None
    assert cnec_page.clicked_selection({'points': [{'location': 'DE'}]}, options, '13') == '13'


@pytest.mark.parametrize('day,count', [('2024-10-27',25), ('2026-03-29',92), ('2026-10-25',100)])
def test_timeline_includes_minor_ticks_and_disambiguates_repeated_hours(day, count):
    marks = cnec_page.interval_marks(MarketDay.on(day))
    assert len(marks) == count
    labels = [v['label'] for v in marks.values() if v['label'].strip()]
    assert len(labels) == len(set(labels))
    assert all('CEST' in v or 'CET' in v for v in labels)


def page_inputs():
    from shapely.geometry import shape
    phys, ptdfs, external, prices = tables()
    features = json.loads((FIXTURE / 'zones.geojson').read_text())['features']
    zones = pd.DataFrame({'zone': [f['properties']['idx'] for f in features],
                          'geometry': [shape(f['geometry']) for f in features]})
    day = cnec_page.Day(MarketDay.on('2026-09-12'), zones, phys, ptdfs, external, prices, context())
    return day, pd.read_csv(FIXTURE / 'mapped.csv')


def test_country_outline_hits_and_selected_contribution_are_separate_from_the_observed_spread():
    day, mapped = page_inputs()
    rendered = cnec_page.render(day, mapped, 0, -2)
    hit = next(t for t in rendered.figure.data if t.name == 'select country cap')
    assert set(v[0] for v in hit.customdata) == {'-2'}
    assert rendered.reference == 'PL'
    assert 'Other Core zones: +20.00 €/MWh' in rendered.figure.layout.annotations[0].text
    # Actual DE–PL prices differ by only €10; the selected cap contributes €20, offset elsewhere.
    dots = next(t for t in rendered.figure.data if t.name == 'contribution relative to PL')
    assert any('DE · +20.00' in v for v in dots.text)
    ray = next(t for t in rendered.figure.data if t.name == 'DE ray')
    assert ray.hoverinfo == 'text'
    labels = next(t for t in rendered.figure.data if t.name == 'ray contributions')
    assert all(text == '+€20.00' for text in labels.text)
    assert 'Spread: DE − PL' in ray.hovertext
    assert 'contribution: +20.00 €/MWh' in ray.hovertext
    assert 'Total observed spread: +10.00 €/MWh' in ray.hovertext
    assert 'Remainder (other constraints / source precision): -10.00 €/MWh' in ray.hovertext
    assert any('Spread: DE − PL' in text and 'Total observed spread: +10.00' in text for text in dots.hovertext)


def test_line_interior_hits_keep_row_identity_and_missing_alpha_keeps_selection():
    day, mapped = page_inputs()
    rendered = cnec_page.render(day, mapped, 0, 10)
    hit = next(t for t in rendered.figure.data if t.name == 'select line')
    assert len(hit.lon) > 2
    assert set(v[0] for v in hit.customdata) == {'10'}
    missing = cnec_page.Day(**{**day.__dict__, 'context': None})
    unavailable = cnec_page.render(missing, mapped, 0, 10)
    assert unavailable.constraint_value == '10'
    assert any(t.name == 'selected CNEC' for t in unavailable.figure.data)
    assert not any(t.name.startswith('contribution relative') for t in unavailable.figure.data)
    assert 'missing or zero' in unavailable.figure.layout.annotations[0].text


def test_unknown_adjacent_attribution_retains_interface_selection_without_spread_fallback():
    day, mapped = page_inputs()
    external = day.external_constraints.copy()
    external.loc[external.source_id.eq(12), 'hub'] = 'DE_NO2_BigHub'
    changed = cnec_page.Day(**{**day.__dict__, 'external_constraints': external})
    rendered = cnec_page.render(changed, mapped, 0, 12)
    assert rendered.constraint_value == '12'
    assert rendered.reference == 'NO2'
    assert any(t.name == 'NordLink interface' for t in rendered.figure.data)
    assert 'Endpoint contribution unavailable' in rendered.figure.layout.annotations[0].text
    assert not any(t.name.startswith('contribution relative') for t in rendered.figure.data)


def test_shared_alegro_asset_has_both_ids_but_draws_one_interface():
    day, mapped = page_inputs()
    rendered = cnec_page.render(day, mapped, 0, 12)
    traces = [t for t in rendered.figure.data if t.name == 'ALEGrO interface']
    assert len(traces) == 1
    assert set(traces[0].customdata[0][0].split(',')) == {'12', '13'}
    assert 'DE: +5.00 €/MWh relative to BE' in rendered.figure.layout.annotations[0].text


@pytest.mark.parametrize('date', ['2024-03-31', '2024-10-27', '2026-09-12', '2026-10-25'])
def test_previous_next_moves_exactly_one_mtu_and_stops_at_day_boundaries(date):
    day = MarketDay.on(date)
    times = day.market_time_units()
    assert cnec_page.advance_interval(day, 0, -1) == 0
    assert cnec_page.advance_interval(day, len(times)-1, 1) == len(times)-1
    for index in range(1, len(times)-1):
        assert cnec_page.advance_interval(day, index, -1) == index-1
        assert cnec_page.advance_interval(day, index, 1) == index+1


@pytest.mark.parametrize("country, adjusted, other, effect, observed, remainder", [
    (170.53, 189.83, 189.82, -19.30, 19.29, -0.01),
    (189.83, 170.53, 170.54, 19.30, -19.29, 0.01),
    (100.0, 120.0, 110.0, -20.0, 10.0, -10.0),
    (120.0, 120.0, 120.0, 0.0, 0.0, 0.0),
])
def test_pure_country_cap_spread_preserves_cents_and_other_terms(
        country, adjusted, other, effect, observed, remainder):
    cap_effect = attribution.country_cap_effect(country, adjusted)
    spread = attribution.price_spread(country, other, -cap_effect)
    assert cap_effect == pytest.approx(effect)
    assert spread.observed == pytest.approx(observed)
    assert spread.selected == pytest.approx(-effect)
    assert spread.remainder == pytest.approx(remainder)
    assert spread.selected + spread.remainder == pytest.approx(spread.observed)
    assert f"{spread.observed:.2f}" == f"{observed:.2f}"
    assert f"{spread.selected:.2f}" == f"{-effect:.2f}"
