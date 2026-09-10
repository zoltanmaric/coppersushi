"""Electricity Maps' published European day-ahead prices, cached outside git.

The v4 ``price-day-ahead/actual`` route takes one zone, a UTC half-open window and the
resolution to answer at. The resolution is asked for explicitly, as the day's market time
unit. Left unasked, the route answers hourly, and for a quarter-hourly day an hourly value is
the mean of four cleared prices and equal to none of them; the map at app.electricitymaps.com
shows the quarter-hours.

Authentication comes from ``ELECTRICITY_MAPS_API_KEY`` or the gitignored
``.secrets/.electricity_maps_api_key``. Neither responses nor derived prices are distributable
repository fixtures; cached CSVs live under ignored ``data/electricity-maps/``.
"""

import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
import pandera as pa
from pandera.typing import DataFrame

from coppersushi import REPO, market
from coppersushi.data_model.market import DayAheadPrices
from coppersushi.market_day import MarketDay

logger = logging.getLogger(__name__)

BASE_URL = "https://api.electricitymap.org/v4/price-day-ahead/actual"
CACHE_DIR = REPO / "data" / "electricity-maps"
TOKEN_FILE = REPO / ".secrets" / ".electricity_maps_api_key"
TIMEOUT_SECONDS = 60
# The route's names for the market time units `MarketDay.market_time_unit` can name.
TEMPORAL_GRANULARITY = {"h": "hourly", "15min": "15_minutes"}


def api_token() -> str:
    """The API credential, never included in a URL or log message."""
    token = os.environ.get("ELECTRICITY_MAPS_API_KEY")
    if token:
        return token
    try:
        return TOKEN_FILE.read_text().strip()
    except FileNotFoundError as error:
        raise RuntimeError(
            "set ELECTRICITY_MAPS_API_KEY or create .secrets/.electricity_maps_api_key"
        ) from error


def _stamp(moment) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def query(zone: str, day: MarketDay) -> dict[str, str]:
    """The route's parameters: one zone, the day's UTC window, and its market time unit."""
    return {
        "zone": zone,
        "start": _stamp(day.start_time_utc),
        "end": _stamp(day.end_time_utc),
        "temporalGranularity": TEMPORAL_GRANULARITY[day.market_time_unit],
    }


def _get(zone: str, day: MarketDay, token: str) -> dict:
    logger.info("electricity maps: GET published prices for %s on %s", zone, day.date)
    url = f"{BASE_URL}?{urllib.parse.urlencode(query(zone, day))}"
    request = urllib.request.Request(url, headers={"auth-token": token})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def check_answered_as_asked(zone: str, day: MarketDay, payload: dict) -> None:
    """Raise unless the envelope names the zone and resolution the request asked for.

    The rows are checked later, as one table against the market day; this is what the envelope
    alone can answer, and what a default answer fails.
    """
    if payload.get("zone") != zone:
        raise RuntimeError(f"price response says zone {payload.get('zone')!r}, expected {zone!r}")
    asked = TEMPORAL_GRANULARITY[day.market_time_unit]
    answered = payload.get("temporalGranularity")
    if answered != asked:
        raise RuntimeError(f"{zone} prices for {day.date} came {answered!r}, asked {asked!r}")


def fetch_day(
    day: str,
    zones: tuple[str, ...] = market.CORE_ZONES,
    token: str | None = None,
) -> DataFrame[DayAheadPrices]:
    """Fetch one Core market day's published prices, one per zone and market time unit."""
    market_day = MarketDay.on(day)
    credential = token or api_token()
    payloads = []
    for zone in zones:
        payload = _get(zone, market_day, credential)
        check_answered_as_asked(zone, market_day, payload)
        payloads.append(payload)
    prices = market.day_ahead_prices(payloads)
    market.check_complete(prices, market_day, zones)
    return prices


def day_path(day: str) -> Path:
    return CACHE_DIR / f"{day}.csv"


def write_day(day: str, prices: DataFrame[DayAheadPrices]) -> Path:
    """Cache normalized prices locally; ``data/`` is gitignored."""
    path = day_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(path, index=False)
    logger.info("electricity maps: wrote %s", path)
    return path


def read_day(path: Path) -> DataFrame[DayAheadPrices]:
    frame = pd.read_csv(path)
    frame = frame.assign(
        interval=pd.to_datetime(frame.interval, utc=True, format="ISO8601"),
        updated_at=pd.to_datetime(frame.updated_at, utc=True, format="ISO8601"),
    )
    return frame.pipe(DayAheadPrices.validate)


def load_day(day: str, refresh: bool = False) -> DataFrame[DayAheadPrices]:
    """The Core day's prices from the cache, fetched on first use, on request, or when stale.

    A cached day is always every Core zone. A cache that fails the day's invariants — the
    hourly default an older adapter wrote for a quarter-hourly day, a row lost or doubled —
    is fetched once more. A failure after that is the service's and propagates.
    """
    path = day_path(day)
    if not refresh and path.is_file():
        try:
            prices = read_day(path)
            market.check_complete(prices, MarketDay.on(day), market.CORE_ZONES)
            return prices
        except (pa.errors.SchemaError, ValueError) as stale:
            logger.info("electricity maps: cached %s is fetched again: %s", day, stale)
    write_day(day, fetch_day(day))
    return read_day(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["fetch", day]:
            write_day(day, fetch_day(day))
        case _:
            sys.exit(f"usage: python -m {__spec__.name} fetch <day>")
