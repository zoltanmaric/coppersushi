"""Prepare and atomically publish versioned browser data; raw caches remain private."""
import argparse
import gzip
import os
from pathlib import Path

from coppersushi import REPO
from coppersushi.publication import bundle as cnec_bundle
from coppersushi.publication.bundle import Day
from coppersushi.publication.models import DayBundle
from coppersushi.data_model.market import ZonalPrices
from coppersushi.data_sources import cache
from coppersushi.data_sources import cnec_attribution
from coppersushi.data_sources import electricity_maps
from coppersushi.grid_catalog.data_sources import element_catalog
from coppersushi.data_sources import jao
from coppersushi.grid_catalog.data_sources import zone_shapes
from coppersushi.market_day import MarketDay
from coppersushi.publication.readiness import PublicationNotReady, PublicationReceipt, require_received


def prepare(day: MarketDay, refresh: bool = False) -> DayBundle:
    """Construct domain data without importing or invoking the web application's renderer."""
    key = day.date.isoformat()
    receipts = jao._get('monitoring', day.start_time_utc, day.end_time_utc,
                        base_url='https://publicationtool.jao.eu/core/api/system')
    require_received(day, [PublicationReceipt.model_validate(row) for row in receipts])
    context = cnec_attribution.load_day(day, refresh=refresh)
    if not context.notna().all().all():
        raise PublicationNotReady(f'Attribution feeds are incomplete for {day.date}')
    active = jao.load_active_day(key, refresh=refresh)
    prices = electricity_maps.load_day(key, refresh=refresh)
    inputs = Day(day, zone_shapes.load(), active.constraints, active.ptdfs,
                 ZonalPrices.validate(prices), context)
    directory = Path(os.environ.get('COPPERSUSHI_ELEMENT_CATALOG', str(REPO / 'data/element-catalog')))
    mapped, pending = element_catalog.resolution_inputs(directory)
    times = day.market_time_units()
    geometry = {i: element_catalog.resolve_loaded(times[i], active.constraints[active.constraints.interval.eq(times[i])], mapped, pending)
                for i in range(len(times))}
    return cnec_bundle.build(inputs, geometry)


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


def publish(bundle: DayBundle, bucket: str) -> str:
    """Write every immutable object before replacing the small day manifest."""
    generation, files = cnec_bundle.publication_files(bundle)
    client = cache._client()
    for key, content in files:
        lifetime = 'public,max-age=60' if key.endswith('/manifest.json') else 'public,max-age=31536000,immutable'
        client.put_object(Bucket=bucket,Key=key,Body=gzip.compress(content.encode(),mtime=0),
                          ContentType='application/json',ContentEncoding='gzip',CacheControl=lifetime)
    return generation


def write_local(bundle: DayBundle, directory: Path) -> str:
    """Serve the exact same publication format from a local development server."""
    generation, files = cnec_bundle.publication_files(bundle)
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
    args = parser.parse_args()
    day = MarketDay.on(args.day)
    bundle = prepare(day,refresh=args.refresh)
    print(publish(bundle,args.bucket) if args.bucket else write_local(bundle,args.directory))

if __name__ == '__main__':
    main()
