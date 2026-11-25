"""Normalized quarter-hour and hourly auction observations for one publisher response."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

import pandera.polars as pa
import polars as pl
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from coppersushi.pipelines.market_data.response_models import ResponseReceipt

UtcColumn = Annotated[pl.Datetime, "us", "UTC"]
Money = Annotated[Decimal, Field(max_digits=28, decimal_places=10, allow_inf_nan=False)]
MoneyColumn = Annotated[pl.Decimal, 28, 10]


class AuctionObservation(BaseModel):
    """An SDAC observation and the timestamps and attribution supplied by its publisher."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    interval: AwareDatetime
    source_created_at: AwareDatetime | None = None
    source_updated_at: AwareDatetime | None = None
    upstream_source: str | None = None

    @field_validator("interval", "source_created_at", "source_updated_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class PriceRow(AuctionObservation):
    """A directly published zonal clearing price in EUR/MWh."""

    zone: str = Field(min_length=1)
    price: Money


class SpreadRow(AuctionObservation):
    """A published signed destination-minus-origin price difference in EUR/MWh."""

    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    difference: Money


class ObservationTable(pa.DataFrameModel):
    """Common immutable time and source columns on normalized publisher rows."""

    interval: UtcColumn
    source_created_at: UtcColumn | None = pa.Field(nullable=True)
    source_updated_at: UtcColumn = pa.Field(nullable=True)
    upstream_source: str = pa.Field(nullable=True)

    class Config:
        strict = True


class PriceTable(ObservationTable):
    zone: str
    price: MoneyColumn

    class Config:
        unique = ["interval", "zone"]


class SpreadTable(ObservationTable):
    origin: str
    destination: str
    difference: MoneyColumn

    class Config:
        unique = ["interval", "origin", "destination"]


@dataclass(frozen=True)
class PublishedEdition:
    """An immutable normalized edition and its S3 publication timestamp."""

    receipt: ResponseReceipt
    key: str
    published_at: datetime

    @property
    def available_at(self) -> datetime:
        """Conservatively bound availability by receipt and S3's whole-second clock."""
        return max(self.receipt.received_at, object_visible_by(self.published_at))


def object_visible_by(last_modified: datetime) -> datetime:
    """A write is definitely visible at the end of its S3 modification second."""
    return last_modified.replace(microsecond=0) + timedelta(seconds=1)
