"""Reconcile independent published prices against the map's pure calculations."""

import json
from itertools import combinations
from pathlib import Path

import pandas as pd
import pytest

from coppersushi import cnec_market, cnecs
from coppersushi.data_model.cnec_attribution import AttributionContext
from coppersushi.data_model.jao import ActiveConstraints, ConstraintPtdfs
from coppersushi.data_model.market import ZonalPrices
from coppersushi.market import CORE_ZONES

FIXTURE = Path(__file__).parent / 'fixtures/cnec-attribution/observed'
INTERVALS = json.loads((FIXTURE / 'selection.json').read_text())
PRICE_ZONES = {'AT', 'BE', 'CZ', 'DE', 'FR', 'HU', 'NL', 'PL', 'SI'}
COMPOSITION_REFERENCE = 'DE'


def read_table(name, schema):
    frame = pd.read_csv(FIXTURE / f'{name}.csv')
    frame.interval = pd.to_datetime(frame.interval, utc=True)
    return schema.validate(frame)


@pytest.fixture(scope='module')
def published():
    return (
        read_table('physical', ActiveConstraints),
        read_table('ptdfs', ConstraintPtdfs),
        read_table('prices', ZonalPrices),
        read_table('context', AttributionContext),
    )


@pytest.fixture(scope='module', params=INTERVALS)
def interval_view(published, request):
    physical, ptdfs, prices, context = published
    interval = pd.Timestamp(request.param)
    inputs = context[context.interval.eq(interval)]
    assert len(inputs) == 1
    options = dict(context=context, alpha=inputs.alpha.iloc[0])
    args = (physical, ptdfs, prices, interval)
    current = cnec_market.snapshot(*args, **options)
    contributions = {}
    for identity in [*current.constraints.source_id, *current.caps.source_id]:
        selected = cnec_market.snapshot(
            *args, selected=cnec_market.ConstraintKey(identity),
            reference_zone=COMPOSITION_REFERENCE, **options,
        )
        assert selected.contribution is not None
        contributions[identity] = selected.contribution
    return current, contributions, options['alpha']


@pytest.mark.parametrize('reference', CORE_ZONES)
def test_published_country_spreads_reconcile(published, interval_view, reference):
    physical, ptdfs, prices, context = published
    current, composed, alpha = interval_view
    observed = current.prices.set_index('zone').price
    assert set(observed.index) == PRICE_ZONES
    total = pd.Series(0., index=CORE_ZONES)
    for _, constraint in current.constraints.iterrows():
        contribution = cnecs.price_contributions(constraint, ptdfs, reference, alpha)
        # Check snapshot wiring once; exercise the calculation for every reference.
        if reference == COMPOSITION_REFERENCE:
            pd.testing.assert_frame_equal(contribution, composed[constraint.source_id])
        term = contribution.set_index('zone').contribution
        total += term - term.loc[reference]
    for identity in current.caps.source_id:
        selected = cnec_market.snapshot(physical, ptdfs, prices, current.interval,
            cnec_market.ConstraintKey(identity), reference, context=context, alpha=alpha)
        assert selected.reference == reference
        term = selected.contribution.set_index('zone').contribution
        assert term[reference] == 0
        original = composed[identity].set_index('zone').contribution
        pd.testing.assert_series_equal(term, original - original[reference])
        total += term - term.loc[reference]
    for origin, destination in combinations(observed.index, 2):
        assert total[destination] - total[origin] == pytest.approx(
            observed[destination] - observed[origin], abs=.02, rel=0,
        ), (current.interval, origin, destination, reference)
