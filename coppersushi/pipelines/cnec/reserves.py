"""Select independently published reserve evidence before the SDAC submission target."""
from datetime import datetime, timedelta, time, UTC
from typing import Literal, Annotated
from pydantic import BaseModel, AwareDatetime, FiniteFloat, Field, ConfigDict
from coppersushi.pipelines.market_day import MarketDay, MARKET_TZ


class AvailableReserve(BaseModel):
    """A complete eligible observation with its selected product contributions."""
    model_config = ConfigDict(extra='forbid')
    status: Literal['available']
    mw: FiniteFloat
    published_at: AwareDatetime
    products: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]


class UnavailableReserve(BaseModel):
    """Reason an eligible observation cannot be established."""
    model_config = ConfigDict(extra='forbid')
    status: Literal['missing', 'incomplete', 'late', 'ambiguous', 'fetch_failed']


ReserveObservation = Annotated[AvailableReserve | UnavailableReserve, Field(discriminator='status')]


class PolishReserves(BaseModel):
    """Independent requirement and basic purchase evidence for one delivery interval."""
    required: ReserveObservation
    purchased: ReserveObservation


class ReserveRecord(BaseModel):
    """Validated hourly source observation; timestamps are UTC instants."""
    end: AwareDatetime
    published: AwareDatetime
    products: tuple[FiniteFloat | None, FiniteFloat | None, FiniteFloat | None, FiniteFloat | None]


def select(records: list[ReserveRecord], end: datetime, cutoff: datetime) -> ReserveObservation:
    matching = [r for r in records if r.end == end]
    eligible = [r for r in matching if r.published < cutoff]
    if not eligible:
        return UnavailableReserve(status='late' if matching else 'missing')
    latest = max(r.published for r in eligible)
    versions = {r.products for r in eligible if r.published == latest}
    if len(versions) != 1:
        return UnavailableReserve(status='ambiguous')
    products = versions.pop()
    if any(v is None for v in products):
        return UnavailableReserve(status='incomplete')
    return AvailableReserve.model_validate(dict(status='available', mw=sum(v for v in products if v is not None), published_at=latest, products=products))


def align(day: MarketDay, required: list[ReserveRecord] | None, purchased: list[ReserveRecord] | None) -> list[PolishReserves]:
    cutoff = datetime.combine(day.date - timedelta(days=1), time(10, 30), MARKET_TZ).astimezone(UTC)
    def observation(rows: list[ReserveRecord] | None, end: datetime) -> ReserveObservation:
        return UnavailableReserve(status='fetch_failed') if rows is None else select(rows, end, cutoff)
    return [PolishReserves(required=observation(required, t.floor('h').to_pydatetime()+timedelta(hours=1)),
                          purchased=observation(purchased, t.floor('h').to_pydatetime()+timedelta(hours=1)))
            for t in day.market_time_units()]
