"""One independent market publisher poll, invoked by Scheduler or a researcher."""
from datetime import date, timedelta
import os
from typing import Literal, Protocol, get_args
from uuid import UUID

import boto3
from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from coppersushi.pipelines.market_data.data_sources.responses import read_invocation_failures
from coppersushi.pipelines.market_data.response_models import AttemptOutcome, AuctionZone, Publisher
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.market_data.data_sources.collect_market_editions import collect_day
from coppersushi.pipelines.market_data.data_sources.publisher_cooldown import PublisherCoolingDown


class PollRequest(BaseModel):
    """A fixed delivery day or an offset from the scheduled Berlin date."""

    model_config = ConfigDict(extra="forbid")

    publisher: Publisher
    zones: tuple[AuctionZone, ...] | None = None
    delivery_day: date | None = None
    scheduled_at: AwareDatetime | None = None
    day_offset: Literal[0, 1] | None = None

    @model_validator(mode="after")
    def check_day(self) -> "PollRequest":
        if self.zones is not None:
            if not self.zones or len(set(self.zones)) != len(self.zones):
                raise ValueError("Requested zone list must be nonempty and unique")
            if self.publisher == "smard" and self.zones != ("DE-LU",):
                raise ValueError("SMARD only supplies DE-LU")
        if self.delivery_day is None:
            if self.scheduled_at is None or self.day_offset is None:
                raise ValueError("Scheduled collection needs a timestamp and delivery-day offset")
        elif self.scheduled_at is not None or self.day_offset is not None:
            raise ValueError("Choose a fixed delivery day or a scheduled poll")
        return self

    def day(self) -> date:
        """Resolve the delivery date in the market timezone."""
        if self.delivery_day is not None:
            return self.delivery_day
        assert self.scheduled_at is not None and self.day_offset is not None
        return MarketDay.containing(self.scheduled_at).date + timedelta(days=self.day_offset)


class _Invocation(Protocol):
    aws_request_id: str


def handler(event: dict, context: _Invocation) -> dict:
    """Store every zone attempt before surfacing publisher failures to Lambda."""
    request = PollRequest.model_validate(event)
    day = request.day()
    zones = request.zones or (("DE-LU",) if request.publisher == "smard" else get_args(AuctionZone))
    client = boto3.client("s3")
    bucket = os.environ["COPPERSUSHI_CACHE_BUCKET"]
    invocation_id = UUID(context.aws_request_id)
    try:
        attempts = collect_day(client, bucket, request.publisher, day, zones=zones, invocation_id=invocation_id)
    except PublisherCoolingDown as active:
        return _deferred(request, day, active, read_invocation_failures(client, bucket, day, invocation_id))
    failures = [attempt for attempt in attempts if attempt.outcome == "failed"]
    _raise_failures([failure for failure in failures if failure.publisher_retry_at is None])
    if failures:
        throttle = failures[-1]
        assert throttle.publisher_retry_at is not None
        pause = PublisherCoolingDown(request.publisher, throttle.publisher_retry_at, throttle.attempt_id)
        recovered = {attempt.zone for attempt in attempts if attempt.outcome != "failed"}
        previous = read_invocation_failures(client, bucket, day, invocation_id)
        return _deferred(request, day, pause, [failure for failure in previous if failure.zone not in recovered])
    return {"publisher": request.publisher, "delivery_day": day.isoformat(),
            "attempt_ids": [str(attempt.attempt_id) for attempt in attempts]}


def _deferred(request: PollRequest, day: date, pause: PublisherCoolingDown, failures: list[AttemptOutcome]) -> dict:
    _raise_failures(failures)
    return {"publisher": request.publisher, "delivery_day": day.isoformat(),
            "status": "deferred", "retry_at": pause.until.isoformat(), "attempt_id": str(pause.attempt)}


def _raise_failures(failures: list[AttemptOutcome]) -> None:
    if failures:
        details = "; ".join(f"{f.publisher} {f.delivery_day} {f.zone} attempt {f.attempt_id}: {f.diagnostic}" for f in failures)
        raise RuntimeError(f"Failed market polls: {details}")
