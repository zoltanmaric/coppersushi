"""Immutable writes shared by pipeline storage adapters."""
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def put_once(client: "S3Client", bucket: str, key: str, body: bytes, *, metadata: dict[str, str] | None = None) -> None:
    """Create an immutable object, accepting retries with identical bytes and metadata."""
    try:
        client.put_object(Bucket=bucket, Key=key, Body=body, Metadata=metadata or {}, IfNoneMatch="*")
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            raise
        existing = client.get_object(Bucket=bucket, Key=key)
        with existing["Body"] as stream:
            if existing.get("Metadata", {}) != (metadata or {}) or stream.read() != body:
                raise ValueError(f"Immutable S3 key has different content: {key}") from error
