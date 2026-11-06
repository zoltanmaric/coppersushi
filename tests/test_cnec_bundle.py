"""Real published inputs survive the day-data boundary without figure construction."""
import json
from pathlib import Path
import pandas as pd
from coppersushi import cnec_bundle
from coppersushi.cnec_bundle import Day
from coppersushi.data_model.cnec_bundle import DayBundle
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.cnec_attribution import AttributionContext
from coppersushi.data_model.jao import ActiveConstraints, ConstraintPtdfs
from coppersushi.data_model.market import ZonalPrices
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.market_day import MarketDay, MARKET_TZ

ROOT = Path(__file__).parent / 'fixtures/cnec-attribution/observed'

def table(name, schema):
    frame = pd.read_csv(ROOT / f'{name}.csv')
    frame.interval = pd.to_datetime(frame.interval, utc=True)
    return schema.validate(frame)

def test_bundle_preserves_published_coefficients_and_explicit_interval_identity():
    constraints = table('physical', ActiveConstraints)
    ptdfs = table('ptdfs', ConstraintPtdfs)
    prices = table('prices', ZonalPrices)
    context = table('context', AttributionContext)
    timestamp = pd.Timestamp(next(iter(json.loads((ROOT / 'selection.json').read_text()))))
    day = MarketDay.on(timestamp.tz_convert(MARKET_TZ).date())
    indices = list(day.market_time_units())
    index = indices.index(timestamp)
    zones = BiddingZoneShapes.validate(pd.DataFrame(columns=['zone', 'geometry']))
    geometry = MappedCnecElements.validate(pd.DataFrame(columns=list(MappedCnecElements.to_schema().columns)))
    bundle = cnec_bundle.build(Day(day, zones, constraints, ptdfs, prices, context), {index: geometry})
    decoded = DayBundle.model_validate_json(bundle.model_dump_json())
    assert len(decoded.labels) == len(indices)
    assert [i.index for i in decoded.intervals] == [index]
    for row in decoded.intervals[0].constraints:
        expected = ptdfs[ptdfs.interval.eq(timestamp) & ptdfs.source_id.eq(row.source_id)]
        assert row.ptdfs == dict(zip(expected.zone, expected.ptdf))
        assert row.geometry is None
    assert decoded.intervals[0].alpha == context[context.interval.eq(timestamp)].alpha.iloc[0]


def test_empty_upstream_attribution_cannot_be_published_as_a_quiet_day():
    from coppersushi.data_model.cnec_bundle import MarketInterval
    import pytest
    interval = MarketInterval(index=0,label='00:00',prices={'DE':100},constraints=[],alpha=None,caps=[],notes=[])
    bundle = DayBundle(day='2026-11-01',labels=['00:00'],zones=[],elements={},intervals=[interval],price_range=[100,100])
    with pytest.raises(ValueError,match='Attribution publication is incomplete'):
        cnec_bundle.validate_publication(bundle)


def test_partial_interval_set_cannot_replace_the_day_manifest():
    import pytest
    bundle = DayBundle(day='2026-11-01',labels=['00:00'],zones=[],elements={},intervals=[],price_range=[100,100])
    with pytest.raises(ValueError,match='Only complete days'):
        cnec_bundle.validate_publication(bundle)


def test_publication_shares_metadata_and_uses_one_shape_per_interval():
    from coppersushi.data_model.cnec_bundle import MarketInterval
    intervals = [MarketInterval(index=i,label=str(i),prices={'DE':100+i},constraints=[],alpha=1,caps=[],notes=[]) for i in range(2)]
    bundle = DayBundle(day='2026-11-01',labels=['0','1'],zones=[],elements={},intervals=intervals,price_range=[100,101])
    generation, files = cnec_bundle.publication_files(bundle)
    assert len(generation) == 24
    assert files[-1][0].endswith('/manifest.json')
    metadata = json.loads(files[0][1])
    assert 'intervals' not in metadata
    assert [json.loads(content)['index'] for _,content in files[1:-1]] == [0,1]
    assert all('zones' not in json.loads(content) for _,content in files[1:-1])
