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
