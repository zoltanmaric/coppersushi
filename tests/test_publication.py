"""Scheduled timestamps select delivery dates in market time, including DST."""
from datetime import date

import pytest
from pydantic import ValidationError

from coppersushi.data_sources.publication import PublicationJob
from coppersushi.publication import PublicationReceipt, PublicationNotReady, REQUIRED_PUBLICATIONS, require_received
from coppersushi.market_day import MarketDay
from coppersushi import cnecs


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


def receipts(day: MarketDay) -> list[PublicationReceipt]:
    return [PublicationReceipt(businessDayUtc=day.start_time_utc, page=page, status='Received')
            for page in REQUIRED_PUBLICATIONS]


@pytest.mark.parametrize('status', ['Expected', 'Pending'])
def test_missing_active_publication_waits_then_accepts_received(status: str) -> None:
    day = MarketDay.on('2026-11-07')
    rows = receipts(day)
    rows[0] = PublicationReceipt.model_validate({**rows[0].model_dump(), 'status': status})
    with pytest.raises(PublicationNotReady, match='Active FB Constraints'):
        require_received(day, rows)
    require_received(day, receipts(day))


def test_received_empty_binding_set_is_valid() -> None:
    day = MarketDay.on('2026-11-07')
    require_received(day, receipts(day))
    assert cnecs.active_constraints([]).empty
    assert cnecs.constraint_ptdfs([]).empty


def test_missing_or_wrong_day_receipts_cannot_publish() -> None:
    day = MarketDay.on('2026-11-07')
    for rows in ([], receipts(day)[1:], receipts(MarketDay.on('2026-11-06'))):
        with pytest.raises(PublicationNotReady):
            require_received(day, rows)


def test_duplicate_receipt_is_invalid_not_pending() -> None:
    day = MarketDay.on('2026-11-07')
    rows = receipts(day)
    with pytest.raises(ValueError, match='Duplicate'):
        require_received(day, rows + rows[:1])
