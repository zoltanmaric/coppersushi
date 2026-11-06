"""Synthetic, public fixtures exercise attribution independently of API or private cache."""


import copy
import json

import pandas as pd
import pytest

from coppersushi import REPO, cnec_attribution as attribution, cnec_market, cnecs
from coppersushi.market_day import MarketDay
from coppersushi.data_model.cnec_attribution import AlphaFactor, AllocationConstraint, NetPosition, PolishAlternative

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


@pytest.mark.parametrize('alpha', [.1, .5, 1])
def test_normalized_physical_contribution_scales_and_changes_reference_without_changing_spread(alpha):
    phys, ptdfs, *_ = tables()
    be = cnecs.price_contributions(phys.iloc[0], ptdfs, 'BE', alpha).set_index('zone').contribution
    de = cnecs.price_contributions(phys.iloc[0], ptdfs, 'DE', alpha).set_index('zone').contribution
    assert be.DE == pytest.approx(5 / alpha)
    assert de.BE == pytest.approx(-5 / alpha)
    for z in be.index:
        assert be[z] - be.DE == pytest.approx(de[z])
















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
