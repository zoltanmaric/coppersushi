"""Optional adjacent-region inputs, fetched only for a selected interface and interval."""

import json
import logging
import tempfile
from pathlib import Path

import pandas as pd

from coppersushi import cnec_attribution, market
from coppersushi.data_sources import electricity_maps, jao
from coppersushi.market_day import MarketDay

logger = logging.getLogger(__name__)
EM_ZONES = {'DK1': 'DK-DK1', 'DK2': 'DK-DK2', 'NO2': 'NO-NO2', 'SE4': 'SE-SE4', 'LT': 'LT', 'BG': 'BG'}


def _save(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode='w', delete=False) as file:
        temporary = Path(file.name)
        file.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _prices(day: str, zone: str) -> pd.DataFrame:
    path = electricity_maps.CACHE_DIR / f'adjacent-{zone}-{day}.csv'
    if path.exists():
        try:
            prices = electricity_maps.read_day(path)
            market.check_complete(prices, MarketDay.on(day), (zone,))
            return prices
        except Exception:
            logger.exception('Ignoring unusable adjacent price cache for %s %s', zone, day)
    fetched = electricity_maps.fetch_day(day, zones=(EM_ZONES[zone],)).assign(zone=zone)
    _save(path, fetched.to_csv(index=False))
    return fetched


def load_interval(day: str, interval: pd.Timestamp, hub: str) -> pd.DataFrame | None:
    """An optional failure suppresses attribution, never the selected constraint or page."""
    if hub not in cnec_attribution.INTERFACES or hub in {'ALBE', 'ALDE'} or hub in cnec_attribution.LOSS_HUBS:
        return None
    _, other, _ = cnec_attribution.INTERFACES[hub]
    try:
        outer = 0.0
        if hub in cnec_attribution.NORDIC_HUBS:
            path = jao.JAO_DIR / 'nordic' / f'{interval.strftime("%Y%m%dT%H%MZ")}.json'
            try:
                rows = json.loads(path.read_text()) if path.exists() else None
            except (OSError, ValueError):
                logger.exception('Ignoring unusable Nordic cache for %s', interval)
                rows = None
            outer = cnec_attribution.nordic_outer_term(rows or [], hub, interval)
            if outer is None:
                rows = jao._get('fbDomainShadowPrice', interval, interval + pd.Timedelta(minutes=15),
                                timeout=15, base_url='https://publicationtool.jao.eu/nordic/api/data')
                outer = cnec_attribution.nordic_outer_term(rows, hub, interval)
                if outer is None:
                    return None
                _save(path, json.dumps(rows))
        quotes = _prices(day, other)
        quote = quotes[quotes.interval.eq(interval)]
        if len(quote) != 1:
            return None
        return pd.DataFrame({'interval': [interval], 'hub': [hub], 'adjacent_term': [outer],
                             'adjacent_price': [float(quote.price.iloc[0])]})
    except Exception:
        logger.exception('Adjacent attribution unavailable for %s at %s', hub, interval)
        return None
