"""Honor a publisher's HTTP Retry-After across Lambda invocations."""
from http import HTTPStatus
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING
from uuid import UUID

from coppersushi.pipelines.data_sources.s3 import put_once
from coppersushi.pipelines.market_data.response_models import Poll, Publisher

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class PublisherCoolingDown(RuntimeError):
    """The next request must wait for the publisher's recorded retry time."""

    def __init__(self, publisher: Publisher, until: datetime, attempt: UUID) -> None:
        self.publisher = publisher
        self.until = until
        self.attempt = attempt
        super().__init__(f"{publisher} paused until {until.isoformat()} by receipt {attempt}")


def check_ready(client: "S3Client", bucket: str, publisher: Publisher, now: datetime) -> None:
    """Check unexpired immutable pauses, including those written by another invocation."""
    prefix = f"market-data/cooldowns/{publisher}/"
    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, StartAfter=prefix + _timestamp(now) + "~", MaxKeys=1)
    if response.get("Contents"):
        stamp, attempt = response["Contents"][0]["Key"].removeprefix(prefix).split("/")
        raise PublisherCoolingDown(publisher, datetime.fromisoformat(stamp), UUID(attempt))


def save_retry_after(client: "S3Client", bucket: str, poll: Poll, *, status: int,
                     retry_after: str | None, observed_at: datetime) -> None:
    """Record a pause from response headers before reading the publisher's body."""
    if status not in (HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE):
        return
    delay = retry_after.strip() if retry_after else ""
    try:
        until = (observed_at + timedelta(seconds=int(delay)) if delay.isascii() and delay.isdigit()
                 else parsedate_to_datetime(delay))
        if until.utcoffset() is None:
            raise ValueError("Retry-After date has no timezone")
    except (TypeError, ValueError, OverflowError):
        if status != HTTPStatus.TOO_MANY_REQUESTS:
            return
        # Without a usable retry time, leave the publisher at least one minute to recover.
        until = observed_at + timedelta(minutes=1)
    if until > observed_at:
        key = f"market-data/cooldowns/{poll.publisher}/{_timestamp(until)}/{poll.attempt_id}"
        put_once(client, bucket, key, b"")


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")
