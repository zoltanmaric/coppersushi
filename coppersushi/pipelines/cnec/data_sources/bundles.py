"""Prepare and atomically publish versioned browser data; raw caches remain private."""
import argparse
from collections.abc import Callable
import pandas as pd
from pandera.typing import DataFrame
from coppersushi.pipelines.data_model.jao import ActiveConstraints
from coppersushi.pipelines.data_model.cnec_price_map import MappedCnecElements
import gzip
import logging
from time import monotonic
import os
from pathlib import Path

from coppersushi import PRODUCT
from coppersushi.pipelines.cnec import bundle as cnec_bundle
from coppersushi.pipelines.cnec.bundle import Day
from coppersushi.pipelines.cnec.models import DayBundle
from coppersushi.pipelines.data_model.market import ZonalPrices
from coppersushi.pipelines.data_sources import cache
from coppersushi.pipelines.cnec.data_sources import cnec_attribution
from coppersushi.pipelines.cnec.data_sources import electricity_maps
from coppersushi.pipelines.grid.data_sources import element_catalog
from coppersushi.pipelines.cnec.data_sources import jao
from coppersushi.pipelines.grid.data_sources import zone_shapes
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.cnec.readiness import PublicationNotReady
from coppersushi.pipelines.cnec.readiness import PublicationReceipt
from coppersushi.pipelines.cnec.readiness import require_received


def prepare(day: MarketDay, refresh: bool = False, *, allow_partial_attribution: bool = False) -> DayBundle:
    """Construct domain data without importing or invoking the web application's renderer."""
    key = day.date.isoformat()
    receipts = jao._get('monitoring', day.start_time_utc, day.end_time_utc,
                        base_url='https://publicationtool.jao.eu/core/api/system')
    require_received(day, [PublicationReceipt.model_validate(row) for row in receipts])
    context = cnec_attribution.load_day(day, refresh=refresh)
    if not context.drop(columns=["polish_alt"] if allow_partial_attribution else []).notna().all().all():
        raise PublicationNotReady(f'Attribution feeds are incomplete for {day.date}')
    active = jao.load_active_day(key, refresh=refresh)
    prices = electricity_maps.load_day(key, refresh=refresh)
    inputs = Day(day, zone_shapes.load(), active.constraints, active.ptdfs,
                 ZonalPrices.validate(prices), context)
    directory = Path(os.environ.get('COPPERSUSHI_ELEMENT_CATALOG', str(PRODUCT / 'data/element-catalog')))
    mapped, pending = element_catalog.resolution_inputs(directory)
    return cnec_bundle.build(inputs, resolve_day_geometry(day, active.constraints, mapped, pending))


def resolve_day_geometry(
    day: MarketDay, constraints: DataFrame[ActiveConstraints],
    mapped: DataFrame[MappedCnecElements], pending: set[tuple], *,
    resolve: Callable[[pd.Timestamp, DataFrame[ActiveConstraints], DataFrame[MappedCnecElements], set[tuple]], DataFrame[MappedCnecElements]] = element_catalog.resolve_loaded,
    clock: Callable[[], float] = monotonic,
) -> dict[int, DataFrame[MappedCnecElements]]:
    """Resolve each UTC hour once; retain available locations when discovery runs late."""
    times = day.market_time_units()
    geometry: dict[int, DataFrame[MappedCnecElements]] = {}
    # This limits starts, not in-flight I/O, parsing or cache operations.
    deadline = clock() + 60
    for hour in times.floor('h').unique():
        if clock() >= deadline:
            logging.getLogger(__name__).warning('Geometry discovery budget exhausted for %s; using available locations', day.date)
            break
        indices = [i for i, timestamp in enumerate(times) if timestamp.floor('h') == hour]
        required = constraints[constraints.interval.isin(times[indices])]
        mapped = resolve(hour, required, mapped, pending)
        for i in indices:
            geometry[i] = mapped
    return {i: geometry.get(i, mapped) for i in range(len(times))}


def is_published(day: MarketDay, bucket: str) -> bool:
    """Completed publications stay static; explicit refresh can publish a correction."""
    from botocore.exceptions import ClientError
    try:
        cache._client().head_object(Bucket=bucket, Key=f'data/cnec/v2/{day.date}/manifest.json')
    except ClientError as error:
        if error.response['Error']['Code'] in {'NoSuchKey', '404', 'NotFound'}:
            return False
        raise
    return True


def publish(bundle: DayBundle, bucket: str, *, allow_partial_attribution: bool = False) -> str:
    """Write every immutable object before replacing the small day manifest."""
    generation, files = cnec_bundle.publication_files(bundle, allow_partial_attribution=allow_partial_attribution)
    client = cache._client()
    for key, content in files:
        lifetime = 'public,max-age=60' if key.endswith('/manifest.json') else 'public,max-age=31536000,immutable'
        client.put_object(Bucket=bucket,Key=key,Body=gzip.compress(content.encode(),mtime=0),
                          ContentType='application/json',ContentEncoding='gzip',CacheControl=lifetime)
    return generation


def write_local(bundle: DayBundle, directory: Path, *, allow_partial_attribution: bool = False) -> str:
    """Serve the exact same publication format from a local development server."""
    generation, files = cnec_bundle.publication_files(bundle, allow_partial_attribution=allow_partial_attribution)
    for key, content in files:
        cache.atomic_text(directory / key,content)
    return generation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('day')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--bucket')
    target.add_argument('--directory',type=Path)
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--allow-partial-attribution', action='store_true',
                        help='Permit unavailable Polish cap attribution; all receipt checks still apply')
    args = parser.parse_args()
    day = MarketDay.on(args.day)
    bundle = prepare(day,refresh=args.refresh, allow_partial_attribution=args.allow_partial_attribution)
    print(publish(bundle,args.bucket, allow_partial_attribution=args.allow_partial_attribution) if args.bucket else write_local(bundle,args.directory, allow_partial_attribution=args.allow_partial_attribution))

if __name__ == '__main__':
    main()
