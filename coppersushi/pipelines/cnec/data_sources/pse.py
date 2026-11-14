"""Optional PSE reserve evidence fetched once per source and delivery day."""
from datetime import datetime, UTC
import logging
from urllib.parse import urlparse
import json
from urllib.request import urlopen
from urllib.error import URLError
from pydantic import BaseModel, Field
from coppersushi.pipelines.cnec.reserves import ReserveRecord, PolishReserves, align
from coppersushi.pipelines.market_day import MarketDay


class Page(BaseModel):
    """PSE's paginated response envelope."""
    value: list[dict]
    next_link: str | None = Field(default=None, alias='nextLink')


def fetch(day: MarketDay, endpoint: str, fields: tuple[str, str, str, str]) -> list[ReserveRecord] | None:
    url: str | None = f'https://api.raporty.pse.pl/api/{endpoint}?$filter=business_date%20eq%20%27{day.date}%27&$first=1000'
    records: list[ReserveRecord] = []
    seen: set[str] = set()
    try:
        while url:
            if url in seen or urlparse(url).scheme != 'https' or urlparse(url).netloc != 'api.raporty.pse.pl':
                raise ValueError('Invalid PSE pagination')
            seen.add(url)
            with urlopen(url, timeout=20) as response:
                page = Page.model_validate(json.load(response))
            for row in page.value:
                def instant(key: str) -> datetime:
                    value = datetime.fromisoformat(row[key].replace('Z', '+00:00'))
                    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
                records.append(ReserveRecord.model_validate(dict(end=instant('dtime_utc'), published=instant('publication_ts_utc'),
                                             products=[row.get(f) for f in fields])))
            url = page.next_link
        logging.getLogger(__name__).info('Retrieved PSE %s for %s at %s', endpoint, day.date, datetime.now(UTC).isoformat())
        return records
    except (URLError, OSError, ValueError, KeyError, TypeError):
        logging.getLogger(__name__).exception('PSE %s unavailable for %s', endpoint, day.date)
        return None


def load(day: MarketDay) -> list[PolishReserves]:
    return align(day, fetch(day, 'wmb', ('fcrg', 'afrrg', 'frrg', 'rrg')),
                 fetch(day, 'mbp-tp', ('fcr_g', 'afrr_g', 'mfrrd_g', 'rr_g')))
