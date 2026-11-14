"""Publication cutoff and UTC alignment against checked-in source records."""
import json
from pathlib import Path
from datetime import datetime, UTC
import pytest
from coppersushi.pipelines.cnec.reserves import ReserveRecord, align
from coppersushi.pipelines.market_day import MarketDay

@pytest.mark.parametrize('case', json.loads((Path(__file__).parent/'fixtures/polish-export-caps/submission-cutoff.json').read_text()))
def test_submission_target(case):
    rows = [ReserveRecord(end=r['dtime_utc'], published=r['publication_ts_utc'], products=tuple(r[f] for f in ('fcr_g','afrr_g','mfrrd_g','rr_g'))) for r in case['purchases']]
    day = MarketDay.on(rows[0].end.date())
    evidence = align(day, rows, rows)
    for row, expected in zip(rows, ['available', 'late', 'late']):
        index = list(day.market_time_units()).index(row.end.replace(tzinfo=UTC))-4
        assert all(e.purchased.status == expected for e in evidence[index:index+4])
        if expected == 'available':
            assert evidence[index].purchased.mw == 1000

@pytest.mark.parametrize('day,count', [('2026-03-29',92), ('2026-10-25',100)])
def test_failure_and_missing_cover_dst_day(day,count):
    evidence = align(MarketDay.on(day), [], None)
    assert len(evidence) == count
    assert all(e.required.status == 'missing' and e.purchased.status == 'fetch_failed' for e in evidence)
