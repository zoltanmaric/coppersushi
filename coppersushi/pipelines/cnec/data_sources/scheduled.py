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
    state, etag = bundles.publication_state(day, bucket)
    if state == "complete":
        return PublicationResult(ready=True, day=day.date.isoformat())
    try:
        # An earlier partial response must not freeze a still-arriving publication.
        initial = state == "missing"
        bundle = bundles.prepare(day, refresh=True, allow_partial_attribution=initial,
                                 require_valid_rows=True)
        options = {"IfNoneMatch": "*"} if initial else {"IfMatch": etag}
        bundles.publish(bundle, bucket, allow_partial_attribution=initial, manifest_options=options)
        return PublicationResult(ready=True, day=day.date.isoformat(), awaiting_attribution=bundle.awaiting_polish_price)
    except HTTPError as error:
        if error.code != 429 and error.code < 500:
            raise
        logger.warning("Publication %s deferred: %s: %s", day.date, type(error).__name__, error)
        return PublicationResult(ready=False, day=day.date.isoformat(), awaiting_attribution=state == "partial")
    except (PublicationNotReady, jao.RateLimited, IncompletePrices, URLError, TimeoutError) as error:
        logger.warning("Publication %s deferred: %s: %s", day.date, type(error).__name__, error)
        return PublicationResult(ready=False, day=day.date.isoformat(), awaiting_attribution=state == "partial")
