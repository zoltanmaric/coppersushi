"""Immutable S3 landing records for independent publisher polls."""
from hashlib import sha256
import json
from typing import TYPE_CHECKING
from uuid import UUID

from botocore.exceptions import ClientError
from pydantic import TypeAdapter

from coppersushi.pipelines.market_data.receipts import Receipt, ResponseReceipt

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_receipt = TypeAdapter(Receipt)


def save_attempt(client: "S3Client", bucket: str, receipt: Receipt, body: bytes | None = None) -> None:
    """Commit one poll's metadata and response bytes (or transport diagnostic) together."""
    if isinstance(receipt, ResponseReceipt):
        if body is None or sha256(body).hexdigest() != receipt.body_sha256:
            raise ValueError("Response bytes must match the receipt digest")
    else:
        if body is not None:
            raise ValueError("A failed attempt cannot reference a response body")
        body = receipt.reason.encode("utf-8")
    fields = receipt.model_dump(mode="json", exclude={"reason"})
    metadata = {"receipt": json.dumps(fields, ensure_ascii=True, sort_keys=True, separators=(",", ":"))}
    size = len("receipt") + len(metadata["receipt"])
    if size > 2048:
        largest = max(fields, key=lambda name: len(json.dumps(fields[name], ensure_ascii=True)))
        raise ValueError(f"Poll {receipt.attempt_id} ({receipt.publisher}, {receipt.zone}, {receipt.delivery_day}) "
                         f"needs {size} bytes of S3 metadata; limit is 2048. Largest field: {largest}")
    key = _receipt_key(receipt.attempt_id)
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body, Metadata=metadata, IfNoneMatch="*")
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            raise
        existing = client.get_object(Bucket=bucket, Key=key)
        with existing["Body"] as stream:
            if existing["Metadata"] != metadata or stream.read() != body:
                raise ValueError(f"Immutable archive key has different content: {key}") from error


def read_attempt(client: "S3Client", bucket: str, attempt_id: UUID) -> Receipt:
    """Read response receipts from metadata and transport diagnostics from the failure body."""
    key = _receipt_key(attempt_id)
    stored = client.head_object(Bucket=bucket, Key=key)
    fields = json.loads(stored["Metadata"]["receipt"])
    if fields["kind"] == "failure":
        with client.get_object(Bucket=bucket, Key=key)["Body"] as stream:
            fields["reason"] = stream.read().decode("utf-8")
    receipt = _receipt.validate_python(fields)
    if receipt.attempt_id != attempt_id:
        raise ValueError(f"Receipt identity differs from requested attempt {attempt_id}")
    return receipt


def _receipt_key(attempt_id: UUID) -> str:
    return f"market-data/attempts/{attempt_id}"
