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

from concurrent.futures import ThreadPoolExecutor
import logging
import sys
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from pandera.typing import DataFrame

from coppersushi.pipelines.cnec import prices as market
from coppersushi.pipelines.cnec import spread_prices
from coppersushi.pipelines.jao.data_sources import publication as jao
from coppersushi.pipelines.data_sources import cache
from coppersushi.pipelines.data_sources import auction_prices
from coppersushi.pipelines.data_model.market import DayAheadPrices
from coppersushi.pipelines.data_model.market import ElectricityMapsPriceResponse
from coppersushi.pipelines.market_day import MarketDay

logger = logging.getLogger(__name__)

CACHE_DIR = cache.DATA_DIR / "electricity-maps"


def fetch_day(
    day: str,
    zones: tuple[str, ...] = market.CORE_ZONES,
    token: str | None = None,
) -> DataFrame[DayAheadPrices]:
    """Fetch one Core market day's published prices, one per zone and market time unit."""
    market_day = MarketDay.on(day)
    credential = token or auction_prices.api_token()

    def fetch_zone(zone: str) -> ElectricityMapsPriceResponse | None:
        try:
            return auction_prices.fetch_zone(zone, market_day, credential)
        except market.IncompletePrices:
            return None

    with ThreadPoolExecutor(max_workers=12) as pool:
        payloads = list(pool.map(fetch_zone, zones))
    prices = market.day_ahead_prices([payload for payload in payloads if payload is not None])
    try:
        market.check_complete(prices, market_day, zones)
    except market.IncompletePrices:
        if prices.empty:
            raise
        rows = jao._get("priceSpread", market_day.start_time_utc, market_day.end_time_utc)
        prices = spread_prices.recover(prices, market_day.market_time_units(), zones,
                                      spread_prices.parse_spreads(rows, zones))
        market.check_complete(prices, market_day, zones)
    return prices


def day_path(day: str) -> Path:
    return CACHE_DIR / f"{day}.csv"


def write_day(day: str, prices: DataFrame[DayAheadPrices]) -> Path:
    """Cache normalized prices locally; ``data/`` is gitignored."""
    path = day_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache.atomic_text(path, prices.to_csv(index=False))
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
    key = f"prices/core/{day}"
    if not refresh and not path.is_file():
        cache.restore(key, path.parent, (path.name,))
    if not refresh and path.is_file():
        try:
            prices = read_day(path)
            market.check_complete(prices, MarketDay.on(day), market.CORE_ZONES)
            return prices
        except (pa.errors.SchemaError, ValueError) as stale:
            logger.info("electricity maps: cached %s is fetched again: %s", day, stale)
    write_day(day, fetch_day(day))
    cache.publish(key, path.parent, (path.name,))
    return read_day(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    match sys.argv[1:]:
        case ["fetch", day]:
            write_day(day, fetch_day(day))
        case _:
            sys.exit(f"usage: python -m {__spec__.name} fetch <day>")
