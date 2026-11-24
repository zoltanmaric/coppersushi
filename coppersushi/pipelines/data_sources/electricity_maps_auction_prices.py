"""Direct zonal auction prices from Electricity Maps at the native market resolution."""
from datetime import datetime
from io import BytesIO
import logging
import urllib.error
import urllib.parse
import urllib.request

from coppersushi import REPO
from coppersushi.pipelines.data_sources import credentials
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.data_model.market import ElectricityMapsPriceResponse, IncompletePrices

logger = logging.getLogger(__name__)
BASE_URL = "https://api.electricitymap.org/v4/price-day-ahead/actual"
TOKEN_FILE = REPO / ".secrets" / ".electricity_maps_api_key"
TIMEOUT_SECONDS = 60
# The route's names for the market time units `MarketDay.market_time_unit` can name.
TEMPORAL_GRANULARITY = {"h": "hourly", "15min": "15_minutes"}


def api_token() -> str:
    """The API credential, never included in a URL or log message."""
    return credentials.token("ELECTRICITY_MAPS_API_KEY", TOKEN_FILE)


def query(zone: str, day: MarketDay) -> dict[str, str]:
    """The route's parameters: one zone, the day's UTC window, and its market time unit."""
    return {
        "zone": zone,
        "start": _stamp(day.start_time_utc),
        "end": _stamp(day.end_time_utc),
        "temporalGranularity": TEMPORAL_GRANULARITY[day.market_time_unit],
    }


def fetch_zone(zone: str, day: MarketDay, token: str) -> ElectricityMapsPriceResponse:
    """Read direct auction prices for one zone and verify the response identity."""
    logger.info("electricity maps: GET published prices for %s on %s", zone, day.date)
    url = f"{BASE_URL}?{urllib.parse.urlencode(query(zone, day))}"
    request = urllib.request.Request(url, headers={"auth-token": token})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = ElectricityMapsPriceResponse.model_validate_json(response.read())
    except urllib.error.HTTPError as error:
        with error:
            body = error.read()
        safe_body = body.replace(token.encode(), b"[redacted]") if token else body
        request_id = error.headers.get("X-Request-ID") if error.headers else None
        detail = (f"Electricity Maps GET {url} returned HTTP {error.code} {error.reason}; "
                  f"request_id={request_id!r}, body={safe_body!r}")
        # A caller can recover or retry immediately. Keep the publisher's explanation at receipt.
        logger.warning("%s", detail)
        if error.code == 404 and b"No data for zone" in body:
            raise IncompletePrices(detail) from error
        # Reading HTTPError consumes its stream. Give the caller a readable response.
        failure = urllib.error.HTTPError(error.url, error.code, error.reason, error.headers, BytesIO(safe_body))
        failure.add_note(detail)
        raise failure from error
    check_answered_as_asked(zone, day, payload)
    if any(row.zone != zone for row in payload.data):
        raise ValueError(f"Unexpected zone in {zone} price rows")
    return payload


def check_answered_as_asked(zone: str, day: MarketDay, payload: ElectricityMapsPriceResponse) -> None:
    """Raise unless the envelope names the zone and resolution the request asked for.

    The rows are checked later, as one table against the market day; this is what the envelope
    alone can answer, and what a default answer fails.
    """
    if payload.zone != zone:
        raise RuntimeError(f"price response says zone {payload.zone!r}, expected {zone!r}")
    asked = TEMPORAL_GRANULARITY[day.market_time_unit]
    answered = payload.temporalGranularity
    if answered != asked:
        raise RuntimeError(f"{zone} prices for {day.date} came {answered!r}, asked {asked!r}")


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
