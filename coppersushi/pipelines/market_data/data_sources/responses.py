"""Immutable S3 landing records for independent publisher polls."""
from datetime import datetime
from hashlib import sha256
import json
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import TypeAdapter

from coppersushi.pipelines.data_sources.s3 import put_once
from coppersushi.pipelines.market_data.response_models import FailedAttempt, Poll, Receipt, ResponseReceipt, StoredResponse

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_receipt = TypeAdapter(Receipt)


class NoResponseBody(ValueError):
    """The attempt ended with a transport diagnostic instead of a response."""

    def __init__(self, failure: FailedAttempt) -> None:
        self.failure = failure
        super().__init__(f"No complete response for attempt {failure.attempt_id}: {failure.reason}")


def save_response(client: "S3Client", bucket: str, poll: Poll, body: bytes, *,
                  received_at: datetime, http_status: int) -> ResponseReceipt:
    """Store the response and return the receipt for the exact bytes committed."""
    receipt = ResponseReceipt(**poll.model_dump(), kind="response", received_at=received_at,
                              http_status=http_status, body_sha256=sha256(body).hexdigest())
    _save_attempt(client, bucket, receipt, body)
    return receipt


def save_failure(client: "S3Client", bucket: str, failure: FailedAttempt) -> None:
    """Store the transport failure with its diagnostic text."""
    _save_attempt(client, bucket, failure, failure.reason.encode("utf-8"))


def read_attempt(client: "S3Client", bucket: str, attempt_id: UUID) -> Receipt:
    """Read response receipts from metadata and transport diagnostics from the failure body."""
    key = _receipt_key(attempt_id)
    stored = client.head_object(Bucket=bucket, Key=key)
    fields = json.loads(stored["Metadata"]["receipt"])
    if fields["kind"] == "failure":
        with client.get_object(Bucket=bucket, Key=key)["Body"] as stream:
            fields["reason"] = stream.read().decode("utf-8")
    return _checked_receipt(fields, attempt_id)


def read_response(client: "S3Client", bucket: str, attempt_id: UUID) -> StoredResponse:
    """Read the archived bytes and receipt together, and verify their identity and checksum."""
    stored = client.get_object(Bucket=bucket, Key=_receipt_key(attempt_id))
    with stored["Body"] as stream:
        body = stream.read()
    fields = json.loads(stored["Metadata"]["receipt"])
    if fields["kind"] == "failure":
        fields["reason"] = body.decode("utf-8")
    receipt = _checked_receipt(fields, attempt_id)
    if isinstance(receipt, FailedAttempt):
        raise NoResponseBody(receipt)
    if sha256(body).hexdigest() != receipt.body_sha256:
        raise ValueError(f"Archived response checksum mismatch for attempt {attempt_id}")
    return StoredResponse(receipt, body)


def _checked_receipt(fields: dict[str, object], attempt_id: UUID) -> Receipt:
    receipt = _receipt.validate_python(fields)
    if receipt.attempt_id != attempt_id:
        raise ValueError(f"Receipt identity differs from requested attempt {attempt_id}")
    return receipt


def _save_attempt(client: "S3Client", bucket: str, receipt: Receipt, body: bytes) -> None:
    fields = receipt.model_dump(mode="json", exclude={"reason"})
    metadata = {"receipt": json.dumps(fields, ensure_ascii=True, sort_keys=True, separators=(",", ":"))}
    size = len("receipt") + len(metadata["receipt"])
    if size > 2048:
        largest = max(fields, key=lambda name: len(json.dumps(fields[name], ensure_ascii=True)))
        raise ValueError(f"Poll {receipt.attempt_id} ({receipt.publisher}, {receipt.zone}, {receipt.delivery_day}) "
                         f"needs {size} bytes of S3 metadata; limit is 2048. Largest field: {largest}")
    put_once(client, bucket, _receipt_key(receipt.attempt_id), body, metadata=metadata)


def _receipt_key(attempt_id: UUID) -> str:
    return f"market-data/attempts/{attempt_id}"
