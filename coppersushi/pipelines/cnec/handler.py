"""Native Lambda boundary for one scheduled publication attempt."""
import os
from typing import Any
from coppersushi.pipelines.cnec.job import PublicationJob
from coppersushi.pipelines.cnec.data_sources.scheduled import attempt


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    job = PublicationJob.model_validate(event)
    return attempt(job, os.environ['COPPERSUSHI_CACHE_BUCKET']).model_dump(mode='json')
