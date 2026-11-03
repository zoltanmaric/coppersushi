"""Optional adjacent-region inputs, fetched only for a selected interface and interval."""

import json

import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.cnec_attribution import AdjacentAttribution, AdjacentUnavailable
from coppersushi.data_model.market import DayAheadPrices

from coppersushi import cnec_attribution, market
from coppersushi.data_sources import cache, electricity_maps, jao
from coppersushi.market_day import MarketDay

EM_ZONES = {'DK1': 'DK-DK1', 'DK2': 'DK-DK2', 'NO2': 'NO-NO2', 'SE4': 'SE-SE4', 'LT': 'LT', 'BG': 'BG'}


def _prices(day: MarketDay, zone: str) -> DataFrame[DayAheadPrices]:
    path = electricity_maps.CACHE_DIR / f'adjacent-{zone}-{day.date.isoformat()}.csv'
    key = f"prices/adjacent/{zone}/{day.date.isoformat()}"
    if not path.exists():
        cache.restore(key, path.parent, (path.name,))
    if path.exists():
        prices = electricity_maps.read_day(path)
        market.check_complete(prices, day, (zone,))
        return prices
    fetched = electricity_maps.fetch_day(day.date.isoformat(), zones=(EM_ZONES[zone],)).assign(zone=zone).pipe(DayAheadPrices.validate)
    cache.atomic_text(path, fetched.to_csv(index=False))
    cache.publish(key, path.parent, (path.name,))
    return fetched


def load_interval(day: MarketDay, interval: pd.Timestamp, hub: str) -> DataFrame[AdjacentAttribution] | AdjacentUnavailable:
    """Load adjacent evidence; expected absence is explicit, while I/O and invalid data raise."""
    if hub not in cnec_attribution.INTERFACES:
        raise ValueError(f"Unknown virtual interface: {hub}")
    if hub in {'ALBE', 'ALDE'} or hub in cnec_attribution.LOSS_HUBS:
        return AdjacentUnavailable("Adjacent attribution is not supported for this interface.")
    _, other, _ = cnec_attribution.INTERFACES[hub]
    outer: float | None = 0.0
    if hub in cnec_attribution.NORDIC_HUBS:
        path = jao.JAO_DIR / 'nordic' / f'{interval.strftime("%Y%m%dT%H%MZ")}.json'
        key = f"jao/nordic/{path.stem}"
        if not path.exists():
            cache.restore(key, path.parent, (path.name,))
        rows = json.loads(path.read_text()) if path.exists() else jao._get(
            'fbDomainShadowPrice', interval, interval + pd.Timedelta(minutes=15),
            timeout=15, base_url='https://publicationtool.jao.eu/nordic/api/data')
        outer = cnec_attribution.nordic_outer_term(rows, hub, interval)
        if outer is None:
            return AdjacentUnavailable("Nordic attribution data is unavailable for this interval.")
        if not path.exists():
            cache.atomic_text(path, json.dumps(rows))
            cache.publish(key, path.parent, (path.name,))
    quotes = _prices(day, other)
    quote = quotes[quotes.interval.eq(interval)]
    if len(quote) != 1:
        raise ValueError(f"Expected one {other} price at {interval}, got {len(quote)}")
    return pd.DataFrame({'interval': [interval], 'hub': [hub], 'adjacent_term': [outer],
                         'adjacent_price': [float(quote.price.iloc[0])]}).pipe(AdjacentAttribution.validate)
