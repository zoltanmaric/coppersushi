"""Publish immutable publisher editions and read every edition eligible at a cutoff."""
from collections.abc import Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError
from pandera.errors import SchemaError
from polars.exceptions import PolarsError

from coppersushi.pipelines.market_data.data_sources.parquet import SCHEMA_VERSION, decode_table, encode_table
from coppersushi.pipelines.market_data.edition_models import PriceRow, PublishedEdition, SpreadRow, object_visible_by
from coppersushi.pipelines.market_data.response_models import ResponseReceipt

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def publish_edition(client: "S3Client", bucket: str, receipt: ResponseReceipt,
                    rows: Sequence[PriceRow | SpreadRow]) -> None:
    """Commit validated rows for an already-landed receipt in one conditional write."""
    key = _edition_key(receipt)
    data = encode_table(receipt, rows)
    try:
        client.put_object(Bucket=bucket, Key=key, Body=data, Metadata=_metadata(receipt), IfNoneMatch="*")
    except ClientError as error:
        if error.response["ResponseMetadata"]["HTTPStatusCode"] != 412:
            raise
        saved_receipt, saved_rows = _read_edition(client, bucket, key)
        if saved_receipt != receipt or set(saved_rows) != set(rows):
            raise ValueError(f"Conflicting edition at {key}") from error


def read_editions(client: "S3Client", bucket: str, day: date,
                  cutoff: datetime) -> list[tuple[PublishedEdition, list[PriceRow | SpreadRow]]]:
    """Read all eligible editions, including validated tables with zero rows."""
    if cutoff.utcoffset() is None:
        raise ValueError("Edition discovery requires an aware cutoff")
    editions = []
    pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=_day_prefix(day))
    for page in pages:
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key.endswith(".parquet") or object_visible_by(item["LastModified"]) > cutoff:
                continue
            receipt, rows = _read_edition(client, bucket, key)
            edition = PublishedEdition(receipt=receipt, key=key, published_at=item["LastModified"])
            if edition.available_at <= cutoff:
                editions.append((edition, rows))
    return sorted(editions, key=lambda entry: entry[0].key)


def _read_edition(client: "S3Client", bucket: str, key: str) -> tuple[ResponseReceipt, list[PriceRow | SpreadRow]]:
    response = client.get_object(Bucket=bucket, Key=key)
    with response["Body"] as stream:
        data = stream.read()
    try:
        receipt, rows = decode_table(data)
    except (PolarsError, SchemaError, ValueError) as error:
        raise ValueError(f"Invalid Parquet edition at {key}: {error}") from error
    if key != _edition_key(receipt) or response.get("Metadata", {}) != _metadata(receipt):
        raise ValueError(f"Incorrect edition identity at {key}")
    return receipt, rows


def _metadata(receipt: ResponseReceipt) -> dict[str, str]:
    return {"schema-version": SCHEMA_VERSION, "attempt-id": str(receipt.attempt_id)}


def _day_prefix(day: date) -> str:
    return f"market-data/editions/v{SCHEMA_VERSION}/{day}/"


def _edition_key(receipt: ResponseReceipt) -> str:
    return f"{_day_prefix(receipt.delivery_day)}{receipt.attempt_id}.parquet"
