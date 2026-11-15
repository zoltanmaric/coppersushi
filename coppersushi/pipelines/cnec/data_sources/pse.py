"""Optional PSE reserve evidence fetched once per source and delivery day."""
from datetime import datetime, UTC
import logging
from urllib.parse import urlparse
import json
from urllib.request import urlopen
from urllib.error import URLError
from pydantic import BaseModel, Field, field_validator
from coppersushi.pipelines.cnec.reserves import ReserveRecord, PolishReserves, align
from coppersushi.pipelines.market_day import MarketDay


class SourceRow(BaseModel):
    """UTC timestamp fields validated before source normalization."""
    model_config = {'extra': 'allow'}
    dtime_utc: datetime
    publication_ts_utc: datetime

    @field_validator('dtime_utc', 'publication_ts_utc', mode='before')
    @classmethod
    def timestamp(cls, value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError('PSE timestamps must be strings')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


class Page(BaseModel):
    """PSE's paginated response envelope."""
    value: list[SourceRow]
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
                records.append(ReserveRecord.model_validate(dict(end=row.dtime_utc, published=row.publication_ts_utc,
                                             products=[(row.model_extra or {}).get(f) for f in fields])))
            url = page.next_link
        logging.getLogger(__name__).info('Retrieved PSE %s for %s at %s', endpoint, day.date, datetime.now(tz=UTC).isoformat())
        return records
    except (URLError, OSError, ValueError, KeyError, TypeError):
        logging.getLogger(__name__).exception('PSE %s unavailable for %s', endpoint, day.date)
        return None


def load(day: MarketDay) -> list[PolishReserves]:
    return align(day, fetch(day, 'wmb', ('fcrg', 'afrrg', 'frrg', 'rrg')),
                 fetch(day, 'mbp-tp', ('fcr_g', 'afrr_g', 'mfrrd_g', 'rr_g')))
