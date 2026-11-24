from datetime import UTC, date, datetime
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from coppersushi.pipelines.market_data.data_sources.s3 import read_attempt, save_attempt
from coppersushi.pipelines.market_data.receipts import FailedAttempt, Poll, ResponseReceipt


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.interrupt_receipt = True

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch):
        assert IfNoneMatch == "*"
        if self.interrupt_receipt and "/attempts/" in Key:
            self.interrupt_receipt = False
            raise TimeoutError("interrupted before receipt")
        if Key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"},
                               "ResponseMetadata": {"HTTPStatusCode": 412}}, "PutObject")
        self.objects[Key] = Body

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[Key])}


def test_interrupted_poll_retry_and_independent_receipts():
    store = MemoryS3()
    poll = Poll(attempt_id=uuid4(), publisher="entsoe", dataset="day_ahead_auction_prices",
                zone="DE-LU", delivery_day=date(2026, 11, 20))
    body = b"example provider response"
    now = datetime.now(UTC)
    receipt = ResponseReceipt(**poll.model_dump(), kind="response", status=200,
                              received_at=now, body_sha256=sha256(body).hexdigest())
    with pytest.raises(TimeoutError):
        save_attempt(store, "bucket", receipt, body)
    with pytest.raises(KeyError):
        read_attempt(store, "bucket", poll.attempt_id)
    save_attempt(store, "bucket", receipt, body)
    save_attempt(store, "bucket", receipt, body)
    second = receipt.model_copy(update={"attempt_id": uuid4()})
    save_attempt(store, "bucket", second, body)
    assert len(store.objects) == 3
    assert read_attempt(store, "bucket", second.attempt_id) == second
    failed = FailedAttempt(**poll.model_dump(), kind="failure", completed_at=now, reason="timed out")
    with pytest.raises(ValueError, match="different content"):
        save_attempt(store, "bucket", failed)
    assert read_attempt(store, "bucket", poll.attempt_id) == receipt
