"""Evidence from a single publisher request for one delivery day."""
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Publisher = Literal["entsoe", "electricity_maps", "smard", "jao"]
AuctionZone = Literal["AT", "BE", "CZ", "DE-LU", "FR", "HR", "HU", "NL", "PL", "RO", "SI", "SK"]


class Poll(BaseModel):
    """Identity and scope fixed before issuing a price request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: UUID
    publisher: Publisher
    zone: AuctionZone | Literal["CORE"]
    dataset: Literal["day_ahead_auction_prices", "day_ahead_border_spreads"]
    delivery_day: date


    @model_validator(mode="after")
    def check_scope(self) -> "Poll":
        """Only the JAO feed publishes the Core-wide border spread dataset."""
        if self.publisher == "jao":
            if self.zone != "CORE" or self.dataset != "day_ahead_border_spreads":
                raise ValueError("JAO polls require the Core border spread dataset")
        elif self.zone == "CORE" or self.dataset != "day_ahead_auction_prices":
            raise ValueError("Price polls require a single bidding zone")
        elif self.publisher == "smard" and self.zone != "DE-LU":
            raise ValueError("SMARD feed 4169 represents DE-LU")
        return self


class ResponseReceipt(Poll):
    """Receipt for a complete HTTP response, including an empty or error response."""

    kind: Literal["response"]
    received_at: AwareDatetime
    http_status: Annotated[int, Field(ge=100, le=599)]
    request_url: str | None = Field(default=None, exclude_if=lambda value: value is None)
    headers: dict[str, str] = Field(default_factory=dict, exclude_if=lambda value: not value)
    body_sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


@dataclass(frozen=True)
class StoredResponse:
    """The archived HTTP bytes and the receipt that identifies them."""

    receipt: ResponseReceipt
    body: bytes


class FailedAttempt(Poll):
    """A request ended without a complete body and may have returned HTTP headers."""

    kind: Literal["failure"]
    completed_at: AwareDatetime
    reason: Annotated[str, Field(min_length=1)]
    http_status: Annotated[int, Field(ge=100, le=599)] | None = Field(default=None, exclude_if=lambda status: status is None)
    headers: dict[str, str] = Field(default_factory=dict, exclude_if=lambda headers: not headers)


Receipt = Annotated[ResponseReceipt | FailedAttempt, Field(discriminator="kind")]


class AttemptOutcome(Poll):
    """Index entry left by a completed collection and normalization attempt."""

    invocation_id: UUID | None = None
    publisher_retry_at: AwareDatetime | None = None
    completed_at: AwareDatetime
    outcome: Literal["validated", "empty", "failed"]
    rows: Annotated[int, Field(ge=0)]
    diagnostic: str | None = None
