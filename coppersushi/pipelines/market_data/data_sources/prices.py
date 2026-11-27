"""Resolve eligible archive editions for a consumer and explain missing prices."""
from datetime import date, datetime
from typing import TYPE_CHECKING

from coppersushi.pipelines.market_data.data_sources.editions import read_editions
from coppersushi.pipelines.market_data.data_sources.responses import read_day_diagnostics
from coppersushi.pipelines.market_data.resolution import PriceResult, PriceUnavailable, SourcePolicy, resolve_editions

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def resolve_day(client: "S3Client", bucket: str, day: date, zones: tuple[str, ...],
                cutoff: datetime, policy: SourcePolicy) -> list[PriceResult]:
    """Resolve all native intervals from the archive and attach observed failures to missing quarters."""
    tables = read_editions(client, bucket, day, cutoff, publishers=policy.publishers)
    results = resolve_editions(day, zones, cutoff, policy, tables)
    if not any(isinstance(result, PriceUnavailable) for result in results):
        return results
    attempts = read_day_diagnostics(client, bucket, day, cutoff)
    for i, result in enumerate(results):
        if isinstance(result, PriceUnavailable):
            relevant = [record for record in attempts if record.publisher in policy.direct
                        and record.zone in (result.zone, *result.connected_zones)]
            failures = [f"{record.publisher}/{record.zone}: {record.diagnostic}"
                        for record in relevant]
            results[i] = result.model_copy(update={
                "attempt_ids": tuple(dict.fromkeys((*result.attempt_ids, *(r.attempt_id for r in relevant)))),
                "reason": "; ".join((result.reason, *failures)),
            })
    return results
