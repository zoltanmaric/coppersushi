"""Audit historical delivery days before optionally publishing eligible generations."""
import argparse
from datetime import UTC, date, datetime, timedelta
import os
from pathlib import Path
from typing import Literal

from pandera.typing import DataFrame
from pydantic import BaseModel

from coppersushi.pipelines.data_sources import cache
from coppersushi.pipelines.cnec.data_sources import archive_prices
from coppersushi.pipelines.cnec.data_sources import cnec_attribution
from coppersushi.pipelines.cnec.data_sources import electricity_maps
from coppersushi.pipelines.data_model.market import ZonalPrices
from coppersushi.pipelines.jao.data_sources import publication as jao
from coppersushi.pipelines.market_day import MARKET_TZ
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.market_data.resolution import PriceUnavailable
from coppersushi.pipelines.cnec import bundle
from coppersushi.pipelines.cnec.data_sources import bundles
from coppersushi.pipelines.cnec.readiness import PublicationReceipt
from coppersushi.pipelines.cnec.readiness import require_received


class Coverage(BaseModel):
    """Source evidence and publication outcome for one historical delivery day."""
    day: date
    receipts: list[PublicationReceipt] = []
    active_rows: int | None = None
    ptdf_rows: int | None = None
    expected_intervals: int
    missing_alternatives: int | None = None
    unavailable_intervals: int | None = None
    status: Literal['blocked', 'eligible', 'existing', 'published'] = 'blocked'
    errors: list[str] = []
    bucket: str | None = None
    archive_bucket: str | None = None
    price_cutoff: datetime | None = None
    price_cutoff_mode: Literal['latest', 'explicit'] | None = None
    price_gaps: list[PriceUnavailable] = []


def audit(day: MarketDay, *, archive_bucket: str | None, price_cutoff: datetime | None) -> Coverage:
    """Inspect each source independently; a nonempty response never replaces a receipt."""
    result = Coverage(day=day.date, expected_intervals=len(day.market_time_units()))
    try:
        rows = jao._get('monitoring', day.start_time_utc, day.end_time_utc,
                        base_url='https://publicationtool.jao.eu/core/api/system')
        result.receipts = [PublicationReceipt.model_validate(row) for row in rows]
        require_received(day, result.receipts)
    except Exception as error:
        result.errors.append(f'receipts: {type(error).__name__}: {error}')
    active = context = None
    prices: DataFrame[ZonalPrices] | None = None
    try:
        active = jao.load_active_day(str(day.date))
        result.active_rows = len(active.constraints)
        result.ptdf_rows = len(active.ptdfs)
    except Exception as error:
        result.errors.append(f'constraints: {type(error).__name__}: {error}')
    try:
        context = cnec_attribution.load_day(day)
        result.missing_alternatives = int(context.polish_alt.isna().sum())
        if (context.interval.tolist() != list(day.market_time_units()) or
                not context.drop(columns=['polish_alt']).notna().all().all()):
            raise ValueError('Required attribution intervals are incomplete')
    except Exception as error:
        result.errors.append(f'attribution: {type(error).__name__}: {error}')
    try:
        if archive_bucket is None:
            prices = ZonalPrices.validate(electricity_maps.load_day(str(day.date)))
        else:
            assert price_cutoff is not None
            prices, _ = archive_prices.load_day(day, archive_bucket, price_cutoff)
    except archive_prices.RegionalPricesUnavailable as error:
        result.price_gaps = error.missing
        result.errors.append(f'prices: {error}')
    except Exception as error:
        result.errors.append(f'prices: {type(error).__name__}: {error}')
    if active is not None and context is not None and prices is not None:
        try:
            from coppersushi.pipelines.cnec import interval as cnec_market
            result.unavailable_intervals = sum(bool(cnec_market.snapshot(
                active.constraints, prices, timestamp, context).notes)
                for timestamp in day.market_time_units())
        except Exception as error:
            result.errors.append(f'intervals: {type(error).__name__}: {error}')
    if not result.errors:
        result.status = 'eligible'
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('start', type=date.fromisoformat)
    parser.add_argument('end', type=date.fromisoformat)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--bucket', help='Publish eligible days; omitted means audit only')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--archive-bucket', help='Market archive; defaults to the cache or publish bucket')
    source.add_argument('--legacy-prices', action='store_true', help='Use the historical direct price cache before archive collection')
    parser.add_argument('--price-cutoff', type=datetime.fromisoformat, help='Replay one aware archive cutoff for the requested days')
    parser.add_argument('--jao-requests-per-minute', type=int, choices=(90, 180), default=90,
                        help='Shared request budget; 180 is an explicit throttle/backoff trial')
    args = parser.parse_args()
    if args.start > args.end or args.end >= datetime.now(tz=MARKET_TZ).date():
        parser.error('Require an ordered range ending before today')
    if args.price_cutoff and (args.legacy_prices or args.price_cutoff.utcoffset() is None):
        parser.error('--price-cutoff requires the archive and a timezone')
    archive_bucket = None if args.legacy_prices else (
        args.archive_bucket or os.environ.get('COPPERSUSHI_CACHE_BUCKET') or args.bucket)
    if not (archive_bucket or args.legacy_prices):
        parser.error('Set --archive-bucket or COPPERSUSHI_CACHE_BUCKET, or select --legacy-prices')
    cutoff_mode: Literal['latest', 'explicit'] | None = None
    if archive_bucket:
        cutoff_mode = 'explicit' if args.price_cutoff is not None else 'latest'
    accepted_statuses = {'existing', 'published'} if args.bucket else {'eligible'}
    jao._pacer = jao.RequestPacer(requests_per_minute=args.jao_requests_per_minute, retry_attempts=3)
    done: set[date] = set()
    if args.report.exists():
        for line in args.report.read_text().splitlines():
            previous = Coverage.model_validate_json(line)
            if (previous.status in accepted_statuses
                    and previous.bucket == args.bucket
                    and previous.archive_bucket == archive_bucket
                    and previous.price_cutoff_mode == cutoff_mode
                    and (args.price_cutoff is None or previous.price_cutoff == args.price_cutoff)
                    and (not args.bucket or bundles.is_published(MarketDay.on(previous.day), args.bucket))):
                done.add(previous.day)
            else:
                done.discard(previous.day)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    current = args.start
    blocked = False
    while current <= args.end:
        if current not in done:
            day = MarketDay.on(current)
            price_cutoff = (args.price_cutoff or datetime.now(tz=UTC)) if archive_bucket else None
            result = audit(day, archive_bucket=archive_bucket, price_cutoff=price_cutoff)
            result.bucket = args.bucket
            result.archive_bucket = archive_bucket
            result.price_cutoff = price_cutoff
            result.price_cutoff_mode = cutoff_mode
            if args.bucket and result.status == 'eligible':
                try:
                    if bundles.is_published(day, args.bucket):
                        result.status = 'existing'
                    else:
                        prepared = bundles.prepare(day, allow_partial_attribution=True,
                                                   archive_bucket=archive_bucket, price_cutoff=price_cutoff,
                                                   legacy_prices=args.legacy_prices)
                        bundle.validate_publication(prepared, allow_partial_attribution=True)
                        bundles.publish(prepared, args.bucket, allow_partial_attribution=True,
                                        archive_bucket=archive_bucket)
                        result.status = 'published'
                except Exception as error:
                    result.status = 'blocked'
                    result.errors.append(f'publication: {type(error).__name__}: {error}')
            previous_text = args.report.read_text() if args.report.exists() else ''
            cache.atomic_text(args.report, previous_text + result.model_dump_json() + '\n')
            print(f'{current}: {result.status}; {"; ".join(result.errors)}', flush=True)
            blocked |= result.status == 'blocked'
        current += timedelta(days=1)
    raise SystemExit(1 if blocked else 0)


if __name__ == '__main__':
    main()
