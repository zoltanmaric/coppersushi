from datetime import UTC, date, datetime
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from coppersushi.pipelines.market_data.data_sources.s3 import read_attempt, save_failure, save_response
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


def test_interrupted_poll_retry_and_independent_receipts():
    store = MemoryS3()
    poll = Poll(attempt_id=uuid4(), publisher="entsoe", dataset="day_ahead_auction_prices",
                zone="DE-LU", delivery_day=date(2026, 11, 20))
    body = b"example provider response"
    now = datetime.now(UTC)
    with pytest.raises(TimeoutError):
        save_response(store, "bucket", poll, body, received_at=now, status=200)
    assert not store.objects
    with pytest.raises(KeyError):
        read_attempt(store, "bucket", poll.attempt_id)
    receipt = save_response(store, "bucket", poll, body, received_at=now, status=200)
    assert receipt.body_sha256 == sha256(body).hexdigest()
    save_response(store, "bucket", poll, body, received_at=now, status=200)
    second_poll = poll.model_copy(update={"attempt_id": uuid4()})
    second = save_response(store, "bucket", second_poll, body, received_at=now, status=200)
    assert list(store.objects.values()) == [body, body]
    assert read_attempt(store, "bucket", second.attempt_id) == second
    failed = FailedAttempt(**poll.model_dump(), kind="failure", completed_at=now, reason="timed out")
    with pytest.raises(ValueError, match="different content"):
        save_failure(store, "bucket", failed)
    assert read_attempt(store, "bucket", poll.attempt_id) == receipt
    with pytest.raises(ValueError, match="different content"):
        save_response(store, "bucket", poll, body, received_at=now, status=503)
    failure = failed.model_copy(update={"attempt_id": uuid4(), "reason": "é" * 3000})
    save_failure(store, "bucket", failure)
    assert read_attempt(store, "bucket", failure.attempt_id) == failure
