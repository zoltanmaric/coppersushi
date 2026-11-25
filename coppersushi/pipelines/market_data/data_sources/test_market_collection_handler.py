from datetime import date

from coppersushi.pipelines.market_data.data_sources.market_collection_handler import PollRequest


def test_scheduler_resolves_local_day_from_scheduled_instant_at_dst_change() -> None:
    request = PollRequest.model_validate({"publisher": "entsoe", "scheduled_at": "2026-10-24T22:30Z", "day_offset": 1})
    assert request.day() == date(2026, 10, 26)
