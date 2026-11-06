"""One attempt to publish tomorrow's complete market day."""
from urllib.error import HTTPError, URLError


from coppersushi.market import IncompletePrices
from coppersushi.data_sources import jao
from coppersushi.publication.data_sources import bundles
from coppersushi.publication.readiness import PublicationNotReady
from coppersushi.publication.job import PublicationJob, PublicationResult



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
        return PublicationResult(ready=False, day=day.date.isoformat())
    except (PublicationNotReady, jao.RateLimited, IncompletePrices, URLError, TimeoutError):
        return PublicationResult(ready=False, day=day.date.isoformat())
    return PublicationResult(ready=True, day=day.date.isoformat())
