"""ENTSO-E A44 prices from the coupled day-ahead auction (EUR/MWh)."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request
from xml.etree import ElementTree as XML

from coppersushi import REPO
from coppersushi.pipelines.data_sources.credentials import token
from coppersushi.pipelines.market_data.edition_models import PriceRow
from coppersushi.pipelines.market_day import MarketDay

# ENTSO-E's BZN (bidding zone) identifiers, distinct from national areas.
BIDDING_ZONES = {
    "AT": "10YAT-APG------L", "BE": "10YBE----------2", "CZ": "10YCZ-CEPS-----N",
    "DE-LU": "10Y1001A1001A82H", "FR": "10YFR-RTE------C", "HR": "10YHR-HEP------M",
    "HU": "10YHU-MAVIR----U", "NL": "10YNL----------L", "PL": "10YPL-AREA-----S",
    "RO": "10YRO-TEL------P", "SI": "10YSI-ELES-----O", "SK": "10YSK-SEPS-----K",
}


def request(zone: str, day: MarketDay) -> Request:
    """Request the UTC market day with credentials confined to the outbound header."""
    eic = BIDDING_ZONES[zone]
    params = {"documentType": "A44", "in_Domain": eic, "out_Domain": eic,
              "periodStart": day.start_time_utc.strftime("%Y%m%d%H%M"),
              "periodEnd": day.end_time_utc.strftime("%Y%m%d%H%M")}
    req = Request("https://web-api.tp.entsoe.eu/api?" + urlencode(params))
    req.add_unredirected_header("SECURITY_TOKEN", token("ENTSOE_API_TOKEN", REPO / ".secrets/.entsoe_api_token"))
    return req


def prices(body: bytes, zone: str, day: MarketDay) -> list[PriceRow]:
    """Select native SDAC series and expand A03 change points within their own period."""
    root = XML.fromstring(body)
    if root.tag.endswith("Acknowledgement_MarketDocument"):
        reason = root.findtext("{*}Reason/{*}text") or ""
        if "no matching data" in reason.lower():
            return []
        raise ValueError(f"ENTSO-E acknowledgement: {reason}")
    if root.findtext("{*}type") != "A44":
        raise ValueError("Expected ENTSO-E A44 price document")
    eic = BIDDING_ZONES[zone]
    rows = []
    for series in root.findall("{*}TimeSeries"):
        if (series.findtext("{*}in_Domain.mRID"), series.findtext("{*}out_Domain.mRID")) != (eic, eic):
            raise ValueError(f"Unexpected bidding zone in ENTSO-E price response for {zone}")
        if (series.findtext("{*}contract_MarketAgreement.type") != "A01"
                or series.findtext("{*}auction.type") != "A01"
                or series.findtext("{*}classificationSequence_AttributeInstanceComponent.position") not in (None, "1")):
            continue
        if series.findtext("{*}currency_Unit.name") != "EUR" or series.findtext("{*}price_Measure_Unit.name") != "MWH":
            raise ValueError(f"Expected EUR/MWh for {zone}")
        curve = series.findtext("{*}curveType")
        if curve not in {"A01", "A03"}:
            raise ValueError(f"Unsupported ENTSO-E curve {curve}")
        for period in series.findall("{*}Period"):
            resolution = "PT15M" if day.market_time_unit == "15min" else "PT60M"
            if period.findtext("{*}resolution") == resolution:
                rows.extend(_period(period, zone, day, curve))
    return rows


def no_matching_data(body: bytes) -> bool:
    """Identify ENTSO-E's explicit no-data acknowledgement on an HTTP 400 response."""
    try:
        root = XML.fromstring(body)
    except XML.ParseError:
        return False
    reason = root.findtext("{*}Reason/{*}text") or ""
    return root.tag.endswith("Acknowledgement_MarketDocument") and "no matching data" in reason.lower()


def _period(period: XML.Element, zone: str, day: MarketDay, curve: str) -> list[PriceRow]:
    step = timedelta(minutes=15 if day.market_time_unit == "15min" else 60)
    start = _utc(period.findtext("{*}timeInterval/{*}start"))
    end = _utc(period.findtext("{*}timeInterval/{*}end"))
    slots, fraction = divmod(end - start, step)
    if fraction or slots <= 0 or slots > 100:
        raise ValueError(f"Invalid ENTSO-E period {start}..{end}")
    points: dict[int, Decimal] = {}
    for point in period.findall("{*}Point"):
        position = int(point.findtext("{*}position") or "")
        if not 1 <= position <= slots or position in points:
            raise ValueError(f"Invalid ENTSO-E point position {position}")
        points[position] = Decimal(point.findtext("{*}price.amount") or "")
    rows = []
    value = None
    for position in range(1, slots + 1):
        value = points.get(position, value if curve == "A03" else None)
        interval = start + (position - 1) * step
        if value is not None and day.start_time_utc <= interval < day.end_time_utc:
            rows.append(PriceRow(interval=interval, zone=zone, price=value))
    return rows


def _utc(raw: str | None) -> datetime:
    value = datetime.fromisoformat(raw or "")
    if value.utcoffset() is None:
        raise ValueError("A44 period boundary has no timezone")
    return value.astimezone(UTC)
