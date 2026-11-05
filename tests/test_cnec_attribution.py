"""Synthetic, public fixtures exercise attribution independently of API or private cache."""

from dataclasses import replace

import copy
import json

import pandas as pd
import pytest

from coppersushi import REPO, cnec_attribution as attribution, cnec_market, cnec_page, cnecs
from coppersushi.market_day import MarketDay
from coppersushi.data_model.cnec_attribution import AlphaFactor, AllocationConstraint, NetPosition, PolishAlternative
from tests.test_cnec_page import read_zones

FIXTURE = REPO / "tests/fixtures/cnec-attribution"


def inputs():
    return json.loads((FIXTURE / "inputs.json").read_text())


def tables():
    data = inputs()
    rows = data['active']
    prices = pd.DataFrame(data['prices'])
    prices['interval'] = pd.to_datetime(prices.interval, utc=True)
    return cnecs.active_constraints(rows), cnecs.constraint_ptdfs(rows), prices


def context(feeds=None):
    feeds = feeds or inputs()['feeds']
    models = (AlphaFactor, AllocationConstraint, NetPosition, PolishAlternative)
    return attribution.context(MarketDay.on('2026-09-12'),
                               *[[model.model_validate(row) for row in rows]
                                 for model, rows in zip(models, feeds.values())])


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
    phys, ptdfs, prices = tables()
    interval = prices.interval.iloc[0]
    caps = attribution.country_caps(context(), prices, interval)
    assert caps.source_id.tolist() == [-2]
    assert caps.delta.iloc[0] == -20
    view = cnec_market.snapshot(phys, ptdfs, prices, interval,
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


@pytest.mark.parametrize('offset', [-0.1, 0, 0.1, -0.2, 0.2])
@pytest.mark.parametrize('side', ['import', 'export'])
def test_country_cap_saturation_allows_publication_precision(side, offset):
    *_, prices = tables()
    data = context().assign(
        polish_position=(-200 if side == 'import' else 0) + offset,
        polish_alt=80 if side == 'import' else 120,
    )
    caps = attribution.country_caps(data, prices, prices.interval.iloc[0])
    assert caps.empty == (abs(offset) > 0.11)
    if not caps.empty:
        assert caps.direction.iloc[0] == side
        assert caps.delta.iloc[0] == (20 if side == 'import' else -20)


def test_import_cap_sign_and_capacity():
    *_, prices = tables()
    data = context().assign(polish_position=-200, polish_alt=80)
    caps = attribution.country_caps(data, prices, prices.interval.iloc[0])
    assert caps.source_id.tolist() == [-1]
    assert caps.capacity.iloc[0] == 200
    assert caps.delta.iloc[0] == 20
    day, mapped = page_inputs()
    day = replace(day, context=data)
    rendered = cnec_page.render(day, mapped, 0, -1)
    hit = next(t for t in rendered.figure.data if t.name == 'select country cap')
    assert any('Net import limit: 200 MW' in text for text in hit.text if text)


@pytest.mark.parametrize('alpha', [.1, .5, 1])
def test_normalized_physical_contribution_scales_and_changes_reference_without_changing_spread(alpha):
    phys, ptdfs, *_ = tables()
    be = cnecs.price_contributions(phys.iloc[0], ptdfs, 'BE', alpha).set_index('zone').contribution
    de = cnecs.price_contributions(phys.iloc[0], ptdfs, 'DE', alpha).set_index('zone').contribution
    assert be.DE == pytest.approx(5 / alpha)
    assert de.BE == pytest.approx(-5 / alpha)
    for z in be.index:
        assert be[z] - be.DE == pytest.approx(de[z])


def test_reference_follows_publisher_direction_and_missing_geometry_stays_unavailable():
    phys, *_ = tables()
    mapped = pd.read_csv(FIXTURE / 'mapped.csv')
    row = phys.iloc[0]
    assert attribution.physical_reference(row, mapped, read_zones(), pd.DataFrame()) == 'BE'
    opposite = row.copy()
    opposite['direction'] = 'OPPOSITE'
    assert attribution.physical_reference(opposite, mapped, read_zones(), pd.DataFrame()) == 'DE'
    assert attribution.physical_reference(row, mapped.iloc[:0], read_zones(), pd.DataFrame()) is None




def page_inputs():
    from shapely.geometry import shape
    phys, ptdfs, prices = tables()
    features = json.loads((FIXTURE / 'zones.geojson').read_text())['features']
    zones = pd.DataFrame({'zone': [f['properties']['idx'] for f in features],
                          'geometry': [shape(f['geometry']) for f in features]})
    day = cnec_page.Day(MarketDay.on('2026-09-12'), zones, phys, ptdfs, prices, context())
    return day, pd.read_csv(FIXTURE / 'mapped.csv')


def test_country_outline_hits_and_selected_contribution_are_separate_from_the_observed_spread():
    day, mapped = page_inputs()
    rendered = cnec_page.render(day, mapped, 0, -2)
    hit = next(t for t in rendered.figure.data if t.name == 'select country cap')
    assert set(v[0] for v in hit.customdata) == {'-2'}
    assert any('Net export limit: 0 MW' in text for text in hit.text if text)
    assert rendered.reference == 'PL'
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
    assert any(t.name == 'selected CNEC' for t in unavailable.figure.data)
    assert not any(t.name.startswith('contribution relative') for t in unavailable.figure.data)
    assert any('missing or zero' in note for note in unavailable.notes)
    assert any('Poland cap' in note for note in unavailable.notes)


@pytest.mark.parametrize('selected', [None, 12, 13])
def test_virtual_bounds_are_hidden_and_stale_selections_are_cleared(selected):
    day, mapped = page_inputs()
    rendered = cnec_page.render(day, mapped, 0, selected)
    assert not {'12', '13'} & {option['value'] for option in rendered.constraint_options}
    assert not any('interface' in (t.name or '') or 'ALEGrO' in (t.name or '') for t in rendered.figure.data)
    assert rendered.reference is None
    assert not any((t.name or '').startswith('contribution relative') for t in rendered.figure.data)




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


@pytest.mark.parametrize(('position', 'import_limit', 'export_limit', 'alternative', 'unavailable'), [
    (453.5, 1584.0, 4959.0, float('nan'), False),  # 2026-04-03 00:00 CEST
    (0.0, 200.0, 0.0, float('nan'), True),
    (-200.0, 200.0, 0.0, float('nan'), True),
    (-199.9, 200.0, 0.0, float('nan'), True),
    (-199.8, 200.0, 0.0, float('nan'), False),
    (0.0, 200.0, 0.0, 120.0, False),
    (float('nan'), 200.0, 0.0, 120.0, True),
    (1.0, 200.0, 0.0, float('nan'), True),
])
def test_polish_cap_availability(position, import_limit, export_limit, alternative, unavailable):
    assert attribution.polish_cap_attribution_unavailable(position, import_limit, export_limit, alternative, 100.0) is unavailable


def test_polish_alternative_publication_start():
    from datetime import date
    from coppersushi.data_sources.cnec_attribution import POLISH_ALTERNATIVE_PUBLICATION_START
    assert POLISH_ALTERNATIVE_PUBLICATION_START == date(2026, 5, 6)


@pytest.mark.parametrize('polish_price', [float('nan'), float('inf')])
def test_missing_price_makes_binding_cap_attribution_unavailable(polish_price):
    assert attribution.polish_cap_attribution_unavailable(0.0, 200.0, 0.0, 120.0, polish_price)
    assert not attribution.polish_cap_attribution_unavailable(-100.0, 200.0, 0.0, 120.0, polish_price)


def test_missing_polish_price_is_reported_for_saturated_cap():
    phys, ptdfs, prices = tables()
    no_poland = prices[prices.zone.ne('PL')]
    view = cnec_market.snapshot(phys, ptdfs, no_poland, prices.interval.iloc[0], context=context())
    assert 'Poland cap attribution unavailable for this interval.' in view.notes


def test_swiss_reference_uses_core_endpoint_or_lowest_neighbour():
    phys, *_ = tables()
    row = phys.iloc[0].copy()
    row['tso'] = 'SWISSGRID'
    mapped = pd.read_csv(FIXTURE / 'mapped.csv').iloc[:1].copy()
    mapped.loc[:, 'tso'] = 'SWISSGRID'
    # First endpoint is outside the Core; the other is in Germany.
    mapped.loc[:, ['x0', 'y0']] = [100., 80.]
    prices = pd.DataFrame({'interval': [row.interval]*3, 'zone': ['AT', 'DE', 'FR'], 'price': [80., 70., 60.]})
    assert attribution.physical_reference(row, mapped, read_zones(), prices) == 'DE'
    # With neither endpoint in Core, choose the cheapest supported neighbour.
    mapped.loc[:, ['x1', 'y1']] = [101., 80.]
    assert attribution.physical_reference(row, mapped, read_zones(), prices) == 'FR'
    prices.loc[prices.zone.eq('AT'), 'price'] = 50.
    assert attribution.physical_reference(row, mapped, read_zones(), prices) == 'AT'
    assert attribution.physical_reference(row, mapped, read_zones(), prices.iloc[:2]) is None
