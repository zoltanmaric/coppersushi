from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request
from urllib.response import addinfourl
from uuid import uuid4

import pytest

from coppersushi.pipelines.market_data.data_sources import collect_market_editions, market_collection_handler
from coppersushi.pipelines.market_data.data_sources.responses import read_day_diagnostics
from coppersushi.pipelines.market_data.test_editions import DAY
from coppersushi.pipelines.market_data.test_market_collection import CollectorS3

from coppersushi.pipelines.market_data.data_sources.market_collection_handler import PollRequest


def test_scheduler_resolves_local_day_from_scheduled_instant_at_dst_change() -> None:
    request = PollRequest.model_validate({"publisher": "entsoe", "scheduled_at": "2026-10-24T22:30Z", "day_offset": 1})
    assert request.day() == date(2026, 10, 26)


@pytest.mark.parametrize("malformed_first", [True, False])
def test_retry_during_cooldown_reports_its_own_actionable_failure(monkeypatch: pytest.MonkeyPatch,
                                                                 malformed_first: bool) -> None:
    store = CollectorS3()
    monkeypatch.setenv("COPPERSUSHI_CACHE_BUCKET", "test")
    monkeypatch.setenv("ENTSOE_API_TOKEN", "test-key")
    monkeypatch.setattr(market_collection_handler.boto3, "client", lambda service: store)
    zones = ["DE-LU", "AT"] if malformed_first else ["AT"]
    requested: list[str] = []

    def respond(req: Request, timeout: int) -> addinfourl:
        requested.append(req.full_url)
        if malformed_first and len(requested) == 1:
            fixture = Path(__file__).parents[1] / "fixtures" / "entsoe_missing_resolution.xml"
            return addinfourl(BytesIO(fixture.read_bytes()), {}, req.full_url, 200)
        raise HTTPError(req.full_url, 429, "throttled", {"Retry-After": "900"}, BytesIO())

    monkeypatch.setattr(collect_market_editions, "urlopen", respond)
    event = {"publisher": "entsoe", "delivery_day": DAY.isoformat(), "zones": zones}
    invocation = SimpleNamespace(aws_request_id=str(uuid4()))
    if malformed_first:
        with pytest.raises(RuntimeError, match="resolution"):
            market_collection_handler.handler(event, invocation)
        diagnostics = read_day_diagnostics(store, "test", DAY, datetime.now(UTC) + timedelta(seconds=1))
        malformed, = [record for record in diagnostics if record.zone == "DE-LU"]
        with pytest.raises(RuntimeError) as retry:
            market_collection_handler.handler(event, invocation)
        assert str(malformed.attempt_id) in str(retry.value)
        assert "resolution" in str(retry.value)
        assert "HTTP 429" not in str(retry.value)
    else:
        assert market_collection_handler.handler(event, invocation)["status"] == "deferred"
        assert market_collection_handler.handler(event, invocation)["status"] == "deferred"

    unrelated = SimpleNamespace(aws_request_id=str(uuid4()))
    assert market_collection_handler.handler(event, unrelated)["status"] == "deferred"
    assert len(requested) == len(zones)
