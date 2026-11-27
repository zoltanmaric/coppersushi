"""JAO Core priceSpread: signed destination-minus-origin auction price differences."""
from datetime import datetime
from decimal import Decimal
import json
from urllib.parse import urlencode
from urllib.request import Request

from pydantic import BaseModel, StrictBool, StrictInt

from coppersushi.pipelines.data_model.market import CORE_ZONES
from coppersushi.pipelines.market_data.edition_models import SpreadRow
from coppersushi.pipelines.market_day import MarketDay


PAGE_SIZE = 100_000


class _Page(BaseModel):
    rejected: StrictBool
    messages: object = None
    totalRows: StrictInt | None = None
    data: list[dict[str, object]]


def request(zone: str, day: MarketDay) -> Request:
    """Request a full Core day in one documented page."""
    if zone != "CORE":
        raise ValueError("JAO priceSpread returns the Core region")
    params = {"FromUtc": day.start_time_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
              "ToUtc": day.end_time_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "Take": PAGE_SIZE}
    return Request("https://publicationtool.jao.eu/core/api/data/priceSpread?" + urlencode(params))


def spreads(body: bytes, zone: str, day: MarketDay) -> list[SpreadRow]:
    """Keep reported Core borders and refuse truncated pages and timezone-free intervals."""
    page = _Page.model_validate(json.loads(body, parse_float=Decimal))
    if page.rejected:
        raise ValueError(f"JAO rejected the request: {page.messages}")
    if page.totalRows is None and len(page.data) >= PAGE_SIZE:
        raise ValueError("JAO response reached the page limit without a total count")
    if page.totalRows is not None and len(page.data) != page.totalRows:
        raise ValueError(f"Incomplete JAO priceSpread page: {len(page.data)} of {page.totalRows}")
    result = []
    for record in page.data:
        interval = datetime.fromisoformat(str(record.get("dateTimeUtc")))
        if interval.utcoffset() is None:
            raise ValueError("JAO spread interval lacks timezone")
        for name, value in record.items():
            parts = name.split("_")
            if len(parts) != 3 or parts[0] != "border" or value is None:
                continue
            _, start, end = parts
            if start in CORE_ZONES and end in CORE_ZONES:
                result.append(SpreadRow(interval=interval, origin=_zone(start), destination=_zone(end),
                                        difference=Decimal(str(value))))
    return result


def _zone(zone: str) -> str:
    return "DE-LU" if zone == "DE" else zone
