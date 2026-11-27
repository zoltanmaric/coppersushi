"""Collect one publisher independently, retaining its evidence before normalization."""
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import InvalidOperation
from http import HTTPStatus
from http.client import HTTPException, IncompleteRead
import logging
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.etree.ElementTree import ParseError

from botocore.exceptions import BotoCoreError, ClientError
from pandera.errors import SchemaError

from coppersushi.pipelines.market_data.data_sources import (
    electricity_maps_auction_prices, entsoe_auction_prices, jao_border_spreads, smard_auction_prices,
)
from coppersushi.pipelines.market_data.data_sources.publisher_cooldown import PublisherCoolingDown, check_ready, save_retry_after
from coppersushi.pipelines.market_data.data_sources.editions import publish_edition
from coppersushi.pipelines.market_data.data_sources.responses import save_failure, save_diagnostic, save_response
from coppersushi.pipelines.market_data.edition_models import PriceRow, SpreadRow
from coppersushi.pipelines.market_data.response_models import AttemptOutcome, AuctionZone, FailedAttempt, Poll, Publisher
from coppersushi.pipelines.market_day import MarketDay

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_LOG = logging.getLogger(__name__)
_LOG.setLevel(logging.INFO)

_REQUEST = {
    "entsoe": entsoe_auction_prices.request, "electricity_maps": electricity_maps_auction_prices.request,
    "smard": smard_auction_prices.request, "jao": jao_border_spreads.request,
}
_PARSE: dict[str, Callable[[bytes, str, MarketDay], Sequence[PriceRow | SpreadRow]]] = {
    "entsoe": entsoe_auction_prices.prices, "electricity_maps": electricity_maps_auction_prices.prices,
    "smard": smard_auction_prices.prices, "jao": jao_border_spreads.spreads,
}
# Safe provider metadata useful for retry decisions and diagnostics.
_HEADERS = ("Content-Type", "Date", "ETag", "Last-Modified", "Retry-After", "X-Request-ID")


def collect_day(client: "S3Client", bucket: str, publisher: Publisher, delivery_day: date, *,
                zones: Sequence[AuctionZone] = ("DE-LU",),
                clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)) -> tuple[AttemptOutcome, ...]:
    """Poll each requested scope once and report its outcome."""
    if not zones or len(zones) != len(set(zones)):
        raise ValueError("Supply one or more distinct bidding zones")
    scopes: Sequence[str] = ("CORE",) if publisher == "jao" else zones
    polls = [Poll.model_validate({
        "attempt_id": uuid4(), "publisher": publisher, "zone": zone, "delivery_day": delivery_day,
        "dataset": "day_ahead_border_spreads" if publisher == "jao" else "day_ahead_auction_prices",
    }) for zone in scopes]
    outcomes: list[AttemptOutcome] = []
    for poll in polls:
        try:
            check_ready(client, bucket, publisher, clock())
        except PublisherCoolingDown as pause:
            _LOG.info("poll_deferred publisher=%s zone=%s delivery_day=%s cooldown_attempt=%s retry_at=%s",
                      publisher, poll.zone, delivery_day, pause.attempt, pause.until)
            if not outcomes:
                raise
            break
        _LOG.info("poll_started %s", _scope(poll))
        outcome = _collect(client, bucket, poll, clock)
        if outcome.outcome == "failed":
            _LOG.error("poll_failed %s reason=%s", _scope(poll), outcome.diagnostic)
            with _archive_write(poll, "save_diagnostic"):
                save_diagnostic(client, bucket, outcome)
        else:
            _LOG.info("edition_published %s outcome=%s rows=%d", _scope(poll), outcome.outcome, outcome.rows)
        outcomes.append(outcome)
    return tuple(outcomes)


def _collect(client: "S3Client", bucket: str, poll: Poll, clock: Callable[[], datetime]) -> AttemptOutcome:
    day = MarketDay.on(poll.delivery_day)
    scope = poll.model_dump()
    secrets: list[bytes] = []
    try:
        request = _REQUEST[poll.publisher](poll.zone, day)
        secrets = [value.encode() for key, value in request.header_items() if key.lower() in {"auth-token", "security_token"}]
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
    except (OSError, HTTPException, RuntimeError, BotoCoreError, ClientError) as error:
        message = _safe(f"{type(error).__name__}: {error}".encode(), secrets).decode(errors="replace")
        failure = FailedAttempt(**scope, kind="failure", completed_at=clock(), reason=message)
        return _save_failure(client, bucket, failure)

    with response:
        status = int(response.status)
        headers = {
            key: _safe(response.headers[key].encode(), secrets).decode(errors="replace")
            for key in _HEADERS if key in response.headers
        }
        with _archive_write(poll, "save_cooldown", secrets):
            save_retry_after(client, bucket, poll, status=status, retry_after=headers.get("Retry-After"),
                         observed_at=clock())
        partial = False
        try:
            raw = response.read()
        except IncompleteRead as error:
            raw, partial = error.partial, True
        except (OSError, HTTPException, RuntimeError) as error:
            message = _safe(f"HTTP {status}: {type(error).__name__}: {error}".encode(), secrets).decode(errors="replace")
            failure = FailedAttempt(**scope, kind="failure", completed_at=clock(), reason=message,
                                    http_status=status, headers=headers)
            return _save_failure(client, bucket, failure)
        received = clock()

    body = _safe(raw, secrets)
    with _archive_write(poll, "save_raw_response", secrets):
        receipt = save_response(client, bucket, poll, body, received_at=received, http_status=status,
                            request_url=request.full_url, headers=headers)
    _LOG.info("raw_saved %s http_status=%d", _scope(poll), status)
    try:
        if body != raw:
            raise ValueError("Publisher echoed a credential; original bytes were redacted")
        if partial:
            raise ValueError("HTTP response was truncated during transfer")
        if status == HTTPStatus.NOT_FOUND and poll.publisher == "electricity_maps" and b"No data for zone" in body:
            rows: Sequence[PriceRow | SpreadRow] = []
        elif status == HTTPStatus.BAD_REQUEST and poll.publisher == "entsoe" and entsoe_auction_prices.no_matching_data(body):
            rows = []
        elif status < 200 or status >= 300:
            raise ValueError(f"HTTP {status}: {body[:512].decode(errors='replace')}")
        else:
            rows = _PARSE[poll.publisher](body, poll.zone, day)
    except (ValueError, InvalidOperation, ParseError, SchemaError) as error:
        return AttemptOutcome(**scope, completed_at=clock(), outcome="failed", rows=0, diagnostic="parse_response: " + _safe(str(error).encode(), secrets).decode(errors="replace"))
    with _archive_write(poll, "publish_edition", secrets):
        try:
            publish_edition(client, bucket, receipt, rows)
        except (ValueError, InvalidOperation, SchemaError) as error:
            reason = _safe(str(error).encode(), secrets).decode(errors="replace")
            return AttemptOutcome(**scope, completed_at=clock(), outcome="failed", rows=0,
                                  diagnostic=f"publish_edition: {reason}")
    return AttemptOutcome(**scope, completed_at=clock(), outcome="validated" if rows else "empty",
                          rows=len(rows), diagnostic=None)


def _save_failure(client: "S3Client", bucket: str, failure: FailedAttempt) -> AttemptOutcome:
    with _archive_write(failure, "save_transport_failure"):
        save_failure(client, bucket, failure)
    return AttemptOutcome(attempt_id=failure.attempt_id, publisher=failure.publisher, zone=failure.zone,
                          dataset=failure.dataset, delivery_day=failure.delivery_day,
                          completed_at=failure.completed_at, outcome="failed", rows=0, diagnostic=failure.reason)


def _safe(raw: bytes, secrets: Sequence[bytes]) -> bytes:
    for secret in secrets:
        if secret:
            raw = raw.replace(secret, b"[redacted]")
    return raw


def _scope(poll: Poll) -> str:
    return (f"attempt_id={poll.attempt_id} publisher={poll.publisher} "
            f"zone={poll.zone} delivery_day={poll.delivery_day}")


@contextmanager
def _archive_write(poll: Poll, operation: str, secrets: Sequence[bytes] = ()) -> Iterator[None]:
    """Keep the attempt and failed archive operation visible when S3 cannot save a diagnostic."""
    try:
        yield
    except Exception as error:
        reason = _safe(str(error).encode(), secrets).decode(errors="replace")
        message = f"{operation} failed {_scope(poll)}: {type(error).__name__}: {reason}"
        _LOG.error("%s", message)
        raise RuntimeError(message) from None
