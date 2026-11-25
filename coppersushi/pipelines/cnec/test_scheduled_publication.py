"""Scheduled timestamps select delivery dates in market time, including DST."""
from datetime import date

import pytest
from pydantic import ValidationError

from coppersushi.pipelines.cnec.job import PublicationJob


@pytest.mark.parametrize(('instant', 'delivery'), [
    ('2026-11-06T12:00:00Z', date(2026, 11, 7)),
    ('2026-07-06T11:00:00Z', date(2026, 7, 7)),
    ('2026-03-28T23:30:00Z', date(2026, 3, 30)),
    ('2026-10-24T22:30:00Z', date(2026, 10, 26)),
])
def test_scheduled_instant_pins_next_market_day(instant: str, delivery: date) -> None:
    assert PublicationJob.model_validate({'started_at': instant}).day.date == delivery


def test_schedule_requires_an_aware_instant() -> None:
    with pytest.raises(ValidationError):
        PublicationJob.model_validate({'started_at': '2026-11-06T13:00:00'})


def test_partial_publication_waits_then_replaces_the_same_manifest(monkeypatch):
    from types import SimpleNamespace
    from coppersushi.pipelines.cnec.data_sources import scheduled
    from coppersushi.pipelines.cnec.readiness import PublicationNotReady

    job = PublicationJob.model_validate({'started_at': '2026-11-19T14:50:00Z'})
    state = ('missing', None)
    source_ready = False
    writes = []
    monkeypatch.setattr(scheduled.bundles, 'publication_state', lambda *args: state)

    def prepare(day, *, refresh, allow_partial_attribution, require_valid_rows, archive_bucket):
        assert refresh and require_valid_rows and archive_bucket == 'test'
        if not source_ready and not allow_partial_attribution:
            raise PublicationNotReady('still waiting')
        return SimpleNamespace(awaiting_polish_price=not source_ready)

    monkeypatch.setattr(scheduled.bundles, 'prepare', prepare)
    monkeypatch.setattr(scheduled.bundles, 'publish', lambda *args, **kw: writes.append(kw['manifest_options']))
    assert scheduled.attempt(job, 'test').awaiting_attribution
    state = ('partial', 'previous-etag')
    assert scheduled.attempt(job, 'test').awaiting_attribution
    source_ready = True
    result = scheduled.attempt(job, 'test')
    assert result.ready and not result.awaiting_attribution
    assert writes == [{'IfNoneMatch': '*'}, {'IfMatch': 'previous-etag'}]
