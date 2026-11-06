"""One attempt to publish tomorrow's complete market day."""
from datetime import timedelta
from urllib.error import HTTPError, URLError

from pydantic import AwareDatetime, BaseModel, ConfigDict

from coppersushi.market import IncompletePrices
from coppersushi.data_sources import cnec_bundles, jao
from coppersushi.market_day import MARKET_TZ, MarketDay


class PublicationJob(BaseModel):
    """Scheduled instant pins the delivery day across delayed executions and retries."""
    model_config = ConfigDict(extra='forbid')
    started_at: AwareDatetime

    @property
    def day(self) -> MarketDay:
        return MarketDay.on(self.started_at.astimezone(MARKET_TZ).date() + timedelta(days=1))


class PublicationResult(BaseModel):
    """Readiness drives the workflow's wait loop; unexpected failures still raise."""
    ready: bool
    day: str


def attempt(job: PublicationJob, bucket: str) -> PublicationResult:
    day = job.day
    if cnec_bundles.is_published(day, bucket):
        return PublicationResult(ready=True, day=day.date.isoformat())
    try:
        # An earlier partial response must not freeze a still-arriving publication.
        bundle = cnec_bundles.prepare(day, refresh=True)
        cnec_bundles.publish(bundle, bucket)
    except HTTPError as error:
        if error.code != 429 and error.code < 500:
            raise
        return PublicationResult(ready=False, day=day.date.isoformat())
    except (cnec_bundles.PublicationNotReady, jao.RateLimited, IncompletePrices, URLError, TimeoutError):
        return PublicationResult(ready=False, day=day.date.isoformat())
    return PublicationResult(ready=True, day=day.date.isoformat())
