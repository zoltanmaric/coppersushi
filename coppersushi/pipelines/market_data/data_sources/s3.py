"""Immutable S3 landing records for independent publisher polls."""
from hashlib import sha256
from typing import TYPE_CHECKING
from uuid import UUID

from botocore.exceptions import ClientError
from pydantic import TypeAdapter

from coppersushi.pipelines.market_data.receipts import Receipt, ResponseReceipt

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

_receipt = TypeAdapter(Receipt)


def save_attempt(client: "S3Client", bucket: str, receipt: Receipt, body: bytes | None = None) -> None:
    """Publish a receipt after its exact response bytes are safely stored."""
    if isinstance(receipt, ResponseReceipt):
        if body is None or sha256(body).hexdigest() != receipt.body_sha256:
            raise ValueError("Response bytes must match the receipt digest")
        _put_once(client, bucket, f"market-data/bodies/{receipt.body_sha256}", body)
    elif body is not None:
        raise ValueError("A failed attempt cannot reference a response body")
    _put_once(client, bucket, _receipt_key(receipt.attempt_id), receipt.model_dump_json().encode())


def read_attempt(client: "S3Client", bucket: str, attempt_id: UUID) -> Receipt:
    """Read and validate the committed receipt at the requested identity."""
    response = client.get_object(Bucket=bucket, Key=_receipt_key(attempt_id))
    with response["Body"] as stream:
        receipt = _receipt.validate_json(stream.read())
    if receipt.attempt_id != attempt_id:
        raise ValueError(f"Receipt identity differs from requested attempt {attempt_id}")
    return receipt


def _receipt_key(attempt_id: UUID) -> str:
    return f"market-data/attempts/{attempt_id}.json"


def _put_once(client: "S3Client", bucket: str, key: str, body: bytes) -> None:
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body, IfNoneMatch="*")
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            raise
        existing = client.get_object(Bucket=bucket, Key=key)
        with existing["Body"] as stream:
            if stream.read() != body:
                raise ValueError(f"Immutable archive key has different content: {key}") from error
