"""Native Electricity Maps price-day-ahead/actual publications."""
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request

from coppersushi import REPO
from coppersushi.pipelines.data_model.market import ElectricityMapsPriceResponse
from coppersushi.pipelines.data_sources.credentials import token
from coppersushi.pipelines.market_data.edition_models import PriceRow
from coppersushi.pipelines.market_day import MarketDay


def request(zone: str, day: MarketDay) -> Request:
    """Fetch one zone and explicitly request the native resolution."""
    params = {"zone": _zone(zone), "start": day.start_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "end": day.end_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
              "temporalGranularity": _resolution(day)}
    req = Request("https://api.electricitymap.org/v4/price-day-ahead/actual?" + urlencode(params))
    req.add_unredirected_header("auth-token", token("ELECTRICITY_MAPS_API_KEY", REPO / ".secrets/.electricity_maps_api_key"))
    return req


def prices(body: bytes, zone: str, day: MarketDay) -> list[PriceRow]:
    """Validate the product envelope and preserve each interval's source attribution."""
    payload = ElectricityMapsPriceResponse.model_validate_json(body)
    if payload.zone != _zone(zone) or payload.temporalGranularity != _resolution(day):
        raise ValueError(f"Unexpected Electricity Maps response for {zone} on {day.date}")
    if any(row.zone != payload.zone for row in payload.data):
        raise ValueError(f"Unexpected zone in Electricity Maps records for {zone}")
    return [PriceRow(interval=row.datetime, zone=zone, price=Decimal(str(row.value)),
                     source_created_at=row.createdAt, source_updated_at=row.updatedAt,
                     upstream_source=row.source) for row in payload.data]


def _zone(zone: str) -> str:
    return "DE" if zone == "DE-LU" else zone


def _resolution(day: MarketDay) -> str:
    return "15_minutes" if day.market_time_unit == "15min" else "hourly"
