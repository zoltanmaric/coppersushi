"""Prepare and atomically publish versioned browser data; raw caches remain private."""
import argparse
from collections.abc import Callable
from datetime import UTC, datetime
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
from coppersushi.pipelines.cnec.models import DayBundle, DayManifest
from coppersushi.pipelines.data_model.market import ZonalPrices
from coppersushi.pipelines.data_sources import cache
from coppersushi.pipelines.cnec.data_sources import archive_prices
from coppersushi.pipelines.cnec.data_sources import cnec_attribution
from coppersushi.pipelines.cnec.data_sources import electricity_maps
from coppersushi.pipelines.grid.data_sources import element_catalog
from coppersushi.pipelines.jao.data_sources import publication as jao
from coppersushi.pipelines.grid.data_sources import zone_shapes
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.data_sources.s3 import put_once
from coppersushi.pipelines.cnec.readiness import PublicationNotReady
from coppersushi.pipelines.cnec.readiness import PublicationReceipt
from coppersushi.pipelines.cnec.readiness import require_received


def prepare(day: MarketDay, refresh: bool = False, *,
            allow_partial_attribution: bool = False, require_valid_rows: bool = False,
            archive_bucket: str | None = None, price_cutoff: datetime | None = None,
            legacy_prices: bool = False) -> DayBundle:
    """Construct domain data without importing or invoking the web application's renderer."""
    if legacy_prices and (archive_bucket or price_cutoff):
        raise ValueError("Legacy prices cannot be combined with an archive bucket or cutoff")
    key = day.date.isoformat()
    receipts = jao._get('monitoring', day.start_time_utc, day.end_time_utc,
                        base_url='https://publicationtool.jao.eu/core/api/system')
    require_received(day, [PublicationReceipt.model_validate(row) for row in receipts])
    context = cnec_attribution.load_day(day, refresh=refresh, require_valid_rows=require_valid_rows)
    if not context.drop(columns=["polish_alt"] if allow_partial_attribution else []).notna().all().all():
        raise PublicationNotReady(f'Attribution feeds are incomplete for {day.date}')
    active = jao.load_active_day(key, refresh=refresh)
    decision = None
    if legacy_prices:
        prices = ZonalPrices.validate(electricity_maps.load_retained_day(day))
    else:
        bucket = archive_bucket or os.environ.get("COPPERSUSHI_CACHE_BUCKET")
        if not bucket:
            raise ValueError("A market archive bucket is required")
        prices, decision = archive_prices.load_day(day, bucket, price_cutoff or datetime.now(tz=UTC))
    inputs = Day(day, zone_shapes.load(), active.constraints, active.ptdfs,
                 prices, context)
    directory = Path(os.environ.get('COPPERSUSHI_ELEMENT_CATALOG', str(PRODUCT / 'data/element-catalog')))
    mapped, pending = element_catalog.resolution_inputs(directory)
    bundle = cnec_bundle.build(inputs, resolve_day_geometry(day, active.constraints, mapped, pending))
    bundle.price_decision = decision
    from coppersushi.pipelines.cnec.data_sources import pse
    for interval, evidence in zip(bundle.intervals, pse.load(day), strict=True):
        interval.polish_upward_reserves = evidence
    bundle.awaiting_polish_price = (day.date >= cnec_attribution.POLISH_ALTERNATIVE_PUBLICATION_START
                                  and bool(context.polish_alt.isna().any()))
    return bundle


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


def _manifest_key(day: MarketDay) -> str:
    return f'data/cnec/v3/{day.date}/manifest.json'


def publication_state(day: MarketDay, bucket: str) -> tuple[str, str | None]:
    """Completed publications stay static; explicit refresh can publish a correction."""
    from botocore.exceptions import ClientError
    try:
        head = cache._client().head_object(Bucket=bucket, Key=_manifest_key(day))
    except ClientError as error:
        if error.response['Error']['Code'] in {'NoSuchKey', '404', 'NotFound'}:
            return "missing", None
        raise
    return head["Metadata"].get("attribution", "complete"), head["ETag"]


def is_published(day: MarketDay, bucket: str) -> bool:
    return publication_state(day, bucket)[0] != "missing"


def verify_manifest(day: MarketDay, bucket: str) -> None:
    """Verify the published pointer belongs to the requested delivery day."""
    response = cache._client().get_object(Bucket=bucket, Key=_manifest_key(day))
    with response['Body'] as stream:
        body = stream.read()
    if response.get('ContentEncoding') == 'gzip':
        body = gzip.decompress(body)
    manifest = DayManifest.model_validate_json(body)
    if manifest.day != day.date:
        raise ValueError(f'Expected a manifest for {day.date}; found {manifest.day}')


def publish(bundle: DayBundle, bucket: str, *, allow_partial_attribution: bool = False,
            manifest_options: dict | None = None, archive_bucket: str | None = None) -> str:
    """Write every immutable object before replacing the small day manifest."""
    generation, files = cnec_bundle.publication_files(bundle, allow_partial_attribution=allow_partial_attribution)
    client = cache._client()
    if bundle.price_decision is not None:
        key = f"market-data/decisions/cnec/{bundle.day}/{generation}.json"
        put_once(client, archive_bucket or bucket, key, bundle.price_decision.model_dump_json().encode())
    manifest_options = dict(manifest_options or {})
    if bundle.awaiting_polish_price:
        manifest_options["Metadata"] = {"attribution": "partial"}
    for key, content in files:
        lifetime = 'public,max-age=60' if key.endswith('/manifest.json') else 'public,max-age=31536000,immutable'
        client.put_object(Bucket=bucket,Key=key,Body=gzip.compress(content.encode(),mtime=0),
                          ContentType='application/json',ContentEncoding='gzip',CacheControl=lifetime,
                          **(manifest_options if key.endswith('/manifest.json') else {}))
    return generation


def write_local(bundle: DayBundle, directory: Path, *, allow_partial_attribution: bool = False) -> str:
    """Serve the exact same publication format from a local development server."""
    generation, files = cnec_bundle.publication_files(bundle, allow_partial_attribution=allow_partial_attribution)
    if bundle.price_decision is not None:
        served = directory.resolve()
        if served == served.parent:
            raise ValueError("Use a preview directory with a separate parent for private decision evidence")
        private = served.with_name(f"{served.name}-price-decisions")
        cache.atomic_text(private / f"{bundle.day}-{generation}.json", bundle.price_decision.model_dump_json())
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
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--archive-bucket', help='Market archive; defaults to the cache or publish bucket')
    source.add_argument('--legacy-prices', action='store_true', help='Use only retained prices for a pre-archive delivery day')
    parser.add_argument('--price-cutoff', type=datetime.fromisoformat,
                        help='Replay archive eligibility at an aware instant')
    parser.add_argument('--allow-partial-attribution', action='store_true',
                        help='Permit unavailable Polish cap attribution; all receipt checks still apply')
    args = parser.parse_args()
    day = MarketDay.on(args.day)
    if args.legacy_prices and (args.price_cutoff or day.date >= datetime.now(tz=day.zone).date()):
        parser.error('--legacy-prices is for historical delivery days without an archive cutoff')
    if args.price_cutoff and args.price_cutoff.utcoffset() is None:
        parser.error('--price-cutoff must include a timezone')
    archive_bucket = None if args.legacy_prices else (
        args.archive_bucket or os.environ.get("COPPERSUSHI_CACHE_BUCKET") or args.bucket)
    if not args.legacy_prices and not archive_bucket:
        parser.error("Set --archive-bucket or COPPERSUSHI_CACHE_BUCKET")
    bundle = prepare(day, refresh=args.refresh, allow_partial_attribution=args.allow_partial_attribution,
                     archive_bucket=archive_bucket, price_cutoff=args.price_cutoff,
                     legacy_prices=args.legacy_prices)
    if args.bucket:
        print(publish(bundle, args.bucket, allow_partial_attribution=args.allow_partial_attribution,
                      archive_bucket=archive_bucket))
    else:
        print(write_local(bundle, args.directory, allow_partial_attribution=args.allow_partial_attribution))

if __name__ == '__main__':
    main()
