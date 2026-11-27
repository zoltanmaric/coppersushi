"""Resolve the pinned operating configuration and the scheduler's Berlin delivery date."""
import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import boto3
from metaflow import current
from pydantic import AwareDatetime, TypeAdapter

from forecasts.operations.artifacts import Artifacts, ObjectPin

from forecasts.operations.jobs import Settings


def settings_from_pin(value: str, *, scheduled_live: str = "no") -> Settings:
    pin = ObjectPin.model_validate_json(value)
    raw = Artifacts(boto3.client("s3"), pin.bucket, None).pinned(pin).data
    settings = Settings.model_validate_json(raw)
    if scheduled_live not in {"yes", "no"} or (scheduled_live == "yes" and settings.replay is not None):
        raise ValueError("Live schedule requires production settings")
    return settings


def delivery_date(scheduled_at: str) -> date:
    instant = TypeAdapter(AwareDatetime).validate_python(scheduled_at)
    return instant.astimezone(ZoneInfo("Europe/Berlin")).date() + timedelta(days=1)


def trace() -> dict[str, str]:
    return {"workflow": current.flow_name, "run": current.run_id, "task": current.pathspec,
            "batch_job": os.environ["AWS_BATCH_JOB_ID"]}
