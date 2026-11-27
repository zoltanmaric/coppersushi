"""Resolve the pinned operating configuration and the scheduler's Berlin delivery date."""
import hashlib
import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import boto3
from metaflow import current
from pydantic import AwareDatetime, BaseModel, TypeAdapter

from forecasts.operations.jobs import Settings


class ConfigurationPin(BaseModel):
    bucket: str
    key: str
    version_id: str
    sha256: str


def settings_from_pin(value: str) -> Settings:
    pin = ConfigurationPin.model_validate_json(value)
    response = boto3.client("s3").get_object(Bucket=pin.bucket, Key=pin.key, VersionId=pin.version_id)
    raw = response["Body"].read()
    if hashlib.sha256(raw).hexdigest() != pin.sha256:
        raise ValueError("Operating configuration checksum mismatch")
    return Settings.model_validate_json(raw)


def delivery_date(scheduled_at: str) -> date:
    instant = TypeAdapter(AwareDatetime).validate_python(scheduled_at)
    return instant.astimezone(ZoneInfo("Europe/Berlin")).date() + timedelta(days=1)


def trace() -> dict[str, str]:
    return {"workflow": current.flow_name, "run": current.run_id, "task": current.pathspec,
            "batch_job": os.environ["AWS_BATCH_JOB_ID"]}
