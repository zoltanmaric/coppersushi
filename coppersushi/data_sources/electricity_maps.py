"""Electricity Maps' published European day-ahead prices, cached outside git.

The v4 ``price-day-ahead/actual`` route accepts a UTC half-open window and one
zone per request. Authentication comes from ``ELECTRICITY_MAPS_API_KEY`` or the
gitignored ``.secrets/.electricity_maps_api_key``. Neither responses nor derived
prices are distributable repository fixtures; cached CSVs live under ignored
``data/electricity-maps/``.
"""

import json
import logging
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd
from pandera.typing import DataFrame

from coppersushi import REPO, market
from coppersushi.data_model.market import DayAheadPrices
from coppersushi.market_day import MarketDay

logger = logging.getLogger(__name__)

BASE_URL = "https://api.electricitymap.org/v4/price-day-ahead/actual"
CACHE_DIR = REPO / "data" / "electricity-maps"
TOKEN_FILE = REPO / ".secrets" / ".electricity_maps_api_key"
TIMEOUT_SECONDS = 60


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


def _get(zone: str, day: MarketDay, token: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "zone": zone,
            "start": _stamp(day.start_time_utc),
            "end": _stamp(day.end_time_utc),
        }
    )
    logger.info("electricity maps: GET published prices for %s on %s", zone, day.date)
    request = urllib.request.Request(f"{BASE_URL}?{query}", headers={"auth-token": token})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def fetch_day(
    day: str,
    zones: tuple[str, ...] = market.CORE_ZONES,
    token: str | None = None,
) -> DataFrame[DayAheadPrices]:
    """Fetch published prices for one Core market day at the source's own resolution."""
    market_day = MarketDay.on(day)
    credential = token or api_token()
    prices = market.day_ahead_prices([_get(zone, market_day, credential) for zone in zones])
    expected = set(zones)
    present = set(prices.zone)
    if present != expected:
        raise RuntimeError(f"price zones {sorted(present)}, expected {sorted(expected)}")
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
    """Read the local cache, fetching it on first use or when explicitly refreshed."""
    path = day_path(day)
    if refresh or not path.is_file():
        write_day(day, fetch_day(day))
    return read_day(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["fetch", day]:
            write_day(day, fetch_day(day))
        case _:
            sys.exit(f"usage: python -m {__spec__.name} fetch <day>")
