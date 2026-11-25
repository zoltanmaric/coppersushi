from datetime import UTC, date, datetime
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from coppersushi.pipelines.market_data.data_sources.poll_receipts import (
    NoResponseBody, read_attempt, read_response, save_failure, save_response,
)
from coppersushi.pipelines.market_data.receipts import FailedAttempt, Poll


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.metadata = {}
        self.interrupt_receipt = True

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch, Metadata=None):
        assert IfNoneMatch == "*"
        if self.interrupt_receipt and "/attempts/" in Key:
            self.interrupt_receipt = False
            raise TimeoutError("interrupted before receipt")
        if Key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"},
                               "ResponseMetadata": {"HTTPStatusCode": 412}}, "PutObject")
        self.objects[Key] = Body
        self.metadata[Key] = Metadata or {}

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[Key]), **self.head_object(Bucket=Bucket, Key=Key)}

    def head_object(self, *, Bucket, Key):
        return {"Metadata": self.metadata[Key]}


@pytest.mark.parametrize(("http_status", "body"), [(200, b""), (503, b"maintenance"), (599, b"\xff")])
def test_read_archived_http_response(http_status, body):
    store = MemoryS3()
    store.interrupt_receipt = False
    poll = Poll(attempt_id=uuid4(), publisher="entsoe", dataset="day_ahead_auction_prices",
                zone="DE-LU", delivery_day=date(2026, 11, 20))
    receipt = save_response(store, "bucket", poll, body, received_at=datetime.now(UTC), http_status=http_status)
    archived = read_response(store, "bucket", poll.attempt_id)
    assert archived.receipt == receipt
    assert archived.body == body
    key, = store.objects
    store.objects[key] = b"corrupted object"
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_response(store, "bucket", poll.attempt_id)
    wrong_id = uuid4()
    wrong_key = key.replace(str(poll.attempt_id), str(wrong_id))
    store.objects[wrong_key], store.metadata[wrong_key] = body, store.metadata[key]
    with pytest.raises(ValueError, match="identity differs"):
        read_response(store, "bucket", wrong_id)


def test_interrupted_poll_retry_and_independent_receipts():
    store = MemoryS3()
    poll = Poll(attempt_id=uuid4(), publisher="entsoe", dataset="day_ahead_auction_prices",
                zone="DE-LU", delivery_day=date(2026, 11, 20))
    body = b"example provider response"
    now = datetime.now(UTC)
    with pytest.raises(TimeoutError):
        save_response(store, "bucket", poll, body, received_at=now, http_status=200)
    assert not store.objects
    with pytest.raises(KeyError):
        read_attempt(store, "bucket", poll.attempt_id)
    receipt = save_response(store, "bucket", poll, body, received_at=now, http_status=200)
    assert receipt.body_sha256 == sha256(body).hexdigest()
    save_response(store, "bucket", poll, body, received_at=now, http_status=200)
    second_poll = poll.model_copy(update={"attempt_id": uuid4()})
    second = save_response(store, "bucket", second_poll, body, received_at=now, http_status=200)
    assert list(store.objects.values()) == [body, body]
    assert read_attempt(store, "bucket", second.attempt_id) == second
    failed = FailedAttempt(**poll.model_dump(), kind="failure", completed_at=now, reason="timed out")
    with pytest.raises(ValueError, match="different content"):
        save_failure(store, "bucket", failed)
    assert read_attempt(store, "bucket", poll.attempt_id) == receipt
    with pytest.raises(ValueError, match="different content"):
        save_response(store, "bucket", poll, body, received_at=now, http_status=503)
    failure = failed.model_copy(update={"attempt_id": uuid4(), "reason": "é" * 3000})
    save_failure(store, "bucket", failure)
    assert read_attempt(store, "bucket", failure.attempt_id) == failure
    with pytest.raises(NoResponseBody) as missing:
        read_response(store, "bucket", failure.attempt_id)
    assert missing.value.failure == failure
    assert failure.reason in str(missing.value)
