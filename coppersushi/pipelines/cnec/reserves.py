"""Select independently published reserve evidence before the SDAC submission target."""
from datetime import datetime, timedelta, time, UTC
from typing import Literal
from pydantic import BaseModel, AwareDatetime, FiniteFloat
from coppersushi.pipelines.market_day import MarketDay, MARKET_TZ


class ReserveObservation(BaseModel):
    """Eligible upward capacity, or an explicit reason why it cannot be established."""
    status: Literal['available', 'missing', 'incomplete', 'late', 'ambiguous', 'fetch_failed']
    mw: FiniteFloat | None = None
    published_at: AwareDatetime | None = None


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
        return ReserveObservation(status='late' if matching else 'missing')
    latest = max(r.published for r in eligible)
    versions = {r.products for r in eligible if r.published == latest}
    if len(versions) != 1:
        return ReserveObservation(status='ambiguous')
    products = versions.pop()
    if any(v is None for v in products):
        return ReserveObservation(status='incomplete')
    return ReserveObservation(status='available', mw=sum(v for v in products if v is not None), published_at=latest)


def align(day: MarketDay, required: list[ReserveRecord] | None, purchased: list[ReserveRecord] | None) -> list[PolishReserves]:
    cutoff = datetime.combine(day.date - timedelta(days=1), time(10, 30), MARKET_TZ).astimezone(UTC)
    def observation(rows: list[ReserveRecord] | None, end: datetime) -> ReserveObservation:
        return ReserveObservation(status='fetch_failed') if rows is None else select(rows, end, cutoff)
    return [PolishReserves(required=observation(required, t.floor('h').to_pydatetime()+timedelta(hours=1)),
                          purchased=observation(purchased, t.floor('h').to_pydatetime()+timedelta(hours=1)))
            for t in day.market_time_units()]
