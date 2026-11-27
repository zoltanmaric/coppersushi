"""SMARD series 4169, native DE–LU auction prices in EUR/MWh."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from urllib.request import Request

from pydantic import BaseModel, StrictInt

from coppersushi.pipelines.market_data.edition_models import PriceRow
from coppersushi.pipelines.market_day import MarketDay


class _WeeklyPrices(BaseModel):
    series: list[tuple[StrictInt, Decimal | None]]


def request(zone: str, day: MarketDay) -> Request:
    """Fetch the specific local calendar week containing the requested delivery day."""
    if zone != "DE-LU":
        raise ValueError(f"SMARD 4169 does not represent {zone}")
    first = MarketDay.on(day.date - timedelta(days=day.date.weekday()))
    epoch_ms = int(first.start_time_utc.timestamp()) * 1000
    grain = "quarterhour" if day.market_time_unit == "15min" else "hour"
    return Request(f"https://www.smard.de/app/chart_data/4169/DE/4169_DE_{grain}_{epoch_ms}.json")


def prices(body: bytes, zone: str, day: MarketDay) -> list[PriceRow]:
    """Extract published values for this day; a null price remains missing."""
    weekly = _WeeklyPrices.model_validate(json.loads(body, parse_float=Decimal))
    rows = []
    for millis, price in weekly.series:
        try:
            interval = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=millis)
        except OverflowError as error:
            raise ValueError(f"SMARD timestamp outside the supported millisecond range: {millis}") from error
        if price is not None and day.start_time_utc <= interval < day.end_time_utc:
            rows.append(PriceRow(interval=interval, zone=zone, price=price, upstream_source="ENTSO-E"))
    return rows
