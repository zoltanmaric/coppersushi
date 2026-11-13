"""One attempt to publish tomorrow's complete market day."""
import logging
from urllib.error import HTTPError, URLError


from coppersushi.pipelines.cnec.prices import IncompletePrices
from coppersushi.pipelines.cnec.data_sources import jao
from coppersushi.pipelines.cnec.data_sources import bundles
from coppersushi.pipelines.cnec.readiness import PublicationNotReady
from coppersushi.pipelines.cnec.job import PublicationJob
from coppersushi.pipelines.cnec.job import PublicationResult


logger = logging.getLogger(__name__)


def attempt(job: PublicationJob, bucket: str) -> PublicationResult:
    day = job.day
    if bundles.is_published(day, bucket):
        return PublicationResult(ready=True, day=day.date.isoformat())
    try:
        # An earlier partial response must not freeze a still-arriving publication.
        bundle = bundles.prepare(day, refresh=True)
        bundles.publish(bundle, bucket)
    except HTTPError as error:
        if error.code != 429 and error.code < 500:
            raise
        logger.warning("Publication %s deferred: %s: %s", day.date, type(error).__name__, error)
        return PublicationResult(ready=False, day=day.date.isoformat())
    except (PublicationNotReady, jao.RateLimited, IncompletePrices, URLError, TimeoutError) as error:
        logger.warning("Publication %s deferred: %s: %s", day.date, type(error).__name__, error)
        return PublicationResult(ready=False, day=day.date.isoformat())
    return PublicationResult(ready=True, day=day.date.isoformat())
