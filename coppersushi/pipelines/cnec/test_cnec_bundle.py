from coppersushi import REPO
"""Real published inputs survive the day-data boundary without figure construction."""
import json
from pathlib import Path
import pandas as pd
from coppersushi.pipelines.cnec import bundle as cnec_bundle
from coppersushi.pipelines.cnec.bundle import Day
from coppersushi.pipelines.cnec.models import DayBundle
from coppersushi.pipelines.data_model.cnec_price_map import MappedCnecElements
from coppersushi.pipelines.data_model.cnec_attribution import AttributionContext
from coppersushi.pipelines.data_model.jao import ActiveConstraints
from coppersushi.pipelines.data_model.jao import ConstraintPtdfs
from coppersushi.pipelines.data_model.market import ZonalPrices
from coppersushi.pipelines.data_model.network_views import BiddingZoneShapes
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.market_day import MARKET_TZ

ROOT = REPO / 'coppersushi/testdata/cnec-attribution/observed'

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
        assert row.eic == constraints.loc[constraints.source_id.eq(row.source_id), "eic"].iloc[0]
        assert row.geometry is None
    assert decoded.intervals[0].alpha == context[context.interval.eq(timestamp)].alpha.iloc[0]


def test_empty_upstream_attribution_cannot_be_published_as_a_quiet_day():
    from coppersushi.pipelines.cnec.models import MarketInterval
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
    from coppersushi.pipelines.cnec.models import MarketInterval
    intervals = [MarketInterval(index=i,label=str(i),prices={'DE':100+i},constraints=[],alpha=1,caps=[],notes=[]) for i in range(2)]
    bundle = DayBundle(day='2026-11-01',labels=['0','1'],zones=[],elements={},intervals=intervals,price_range=[100,101])
    generation, files = cnec_bundle.publication_files(bundle)
    assert len(generation) == 24
    assert files[-1][0].endswith('/manifest.json')
    metadata = json.loads(files[0][1])
    assert 'intervals' not in metadata
    assert [json.loads(content)['index'] for _,content in files[1:-1]] == [0,1]
    assert all('zones' not in json.loads(content) for _,content in files[1:-1])


def test_geometry_budget_retains_locations_and_every_interval():
    from coppersushi.pipelines.cnec.data_sources.bundles import resolve_day_geometry
    from coppersushi.pipelines.grid.data_sources.element_catalog import mapped_elements
    from coppersushi import REPO

    day = MarketDay.on('2026-11-07')
    times = day.market_time_units()
    row = table('physical', ActiveConstraints).iloc[[0]]
    constraints = pd.concat([row.assign(interval=t, source_id=i) for i, t in enumerate(times)], ignore_index=True).pipe(ActiveConstraints.validate)
    empty = MappedCnecElements.validate(pd.DataFrame(columns=list(MappedCnecElements.to_schema().columns)))
    located = mapped_elements(REPO / 'coppersushi/testdata/element-catalog')
    ticks = iter([0., 0., 30., 61.])
    calls = []

    def resolve(hour, required, previous, pending):
        calls.append(hour)
        assert list(required.interval) == list(pd.date_range(hour, periods=4, freq='15min'))
        if len(calls) == 2:
            assert previous.equals(located)
        return located

    geometry = resolve_day_geometry(day, constraints, empty, set(), resolve=resolve, clock=lambda: next(ticks))
    assert calls == list(day.hours()[:2])
    assert list(geometry) == list(range(96))
    assert all(frame.equals(located) for frame in geometry.values())


def test_partial_attribution_requires_explicit_policy_and_preserves_note():
    import pytest
    from coppersushi.pipelines.cnec.models import MarketInterval
    note = 'Poland cap attribution unavailable for this interval.'
    interval = MarketInterval(index=0, label='00:00', prices={'DE':100},
                              constraints=[], alpha=1, caps=[], notes=[note])
    day = DayBundle(day='2025-11-05', labels=['00:00'], zones=[], elements={},
                    intervals=[interval], price_range=[100,100])
    with pytest.raises(ValueError, match='Attribution publication is incomplete'):
        cnec_bundle.publication_files(day)
    _, files = cnec_bundle.publication_files(day, allow_partial_attribution=True)
    assert json.loads(files[1][1])['notes'] == [note]
    for broken in (interval.model_copy(update={'alpha':None}),
                   interval.model_copy(update={'notes':['Unknown missing source']})):
        with pytest.raises(ValueError, match='Attribution publication is incomplete'):
            cnec_bundle.publication_files(day.model_copy(update={'intervals':[broken]}),
                                          allow_partial_attribution=True)
