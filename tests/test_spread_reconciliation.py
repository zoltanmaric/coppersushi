"""Reconcile independent published prices against the map's pure calculations."""

import json
from itertools import combinations
from pathlib import Path

import pandas as pd
import pytest

from coppersushi import cnec_market
from coppersushi.data_model.cnec_attribution import AttributionContext
from coppersushi.data_model.jao import ActiveConstraints, ConstraintPtdfs
from coppersushi.data_model.market import ZonalPrices
from coppersushi.market import CORE_ZONES

FIXTURE = Path(__file__).parent / 'fixtures/cnec-attribution/observed'
INTERVALS = json.loads((FIXTURE / 'selection.json').read_text())
PRICE_ZONES = {'AT', 'BE', 'CZ', 'DE', 'FR', 'HU', 'NL', 'PL', 'SI'}


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


@pytest.mark.parametrize('interval', INTERVALS)
@pytest.mark.parametrize('reference', CORE_ZONES)
def test_published_country_spreads_reconcile(published, interval, reference):
    physical, ptdfs, prices, context = published
    interval = pd.Timestamp(interval)
    inputs = context[context.interval.eq(interval)]
    assert len(inputs) == 1
    options = dict(context=context, alpha=inputs.alpha.iloc[0])
    args = (physical, ptdfs, prices, interval)
    current = cnec_market.snapshot(*args, **options)
    observed = current.prices.set_index('zone').price
    assert set(observed.index) == PRICE_ZONES
    total = pd.Series(0., index=CORE_ZONES)
    for identity in [*current.constraints.source_id, *current.caps.source_id]:
        selected = cnec_market.snapshot(
            *args, selected=cnec_market.ConstraintKey(identity),
            reference_zone=reference, **options,
        )
        assert selected.contribution is not None
        term = selected.contribution.set_index('zone').contribution
        total += term - term.loc[reference]
    for origin, destination in combinations(observed.index, 2):
        assert total[destination] - total[origin] == pytest.approx(
            observed[destination] - observed[origin], abs=.02, rel=0,
        ), (interval, origin, destination, reference)
