"""Evidence from a single publisher request for one delivery day."""
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Poll(BaseModel):
    """Identity and scope fixed before issuing a price request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: UUID
    publisher: Literal["entsoe", "electricity_maps"]
    zone: Literal["DE-LU"]
    dataset: Literal["day_ahead_auction_prices"]
    delivery_day: date


class ResponseReceipt(Poll):
    """Receipt for a complete HTTP response, including an empty or error response."""

    kind: Literal["response"]
    received_at: AwareDatetime
    http_status: Annotated[int, Field(ge=100, le=599)]
    body_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


@dataclass(frozen=True)
class StoredResponse:
    """The archived HTTP bytes and the receipt that identifies them."""

    receipt: ResponseReceipt
    body: bytes


class FailedAttempt(Poll):
    """A request ended without a complete response."""

    kind: Literal["failure"]
    completed_at: AwareDatetime
    reason: Annotated[str, Field(min_length=1)]


Receipt = Annotated[ResponseReceipt | FailedAttempt, Field(discriminator="kind")]
