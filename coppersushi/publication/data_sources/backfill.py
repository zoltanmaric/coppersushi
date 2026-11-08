"""Audit historical delivery days before optionally publishing eligible generations."""
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from coppersushi.data_sources import cache, cnec_attribution, electricity_maps, jao
from coppersushi.market_day import MARKET_TZ, MarketDay
from coppersushi.publication import bundle
from coppersushi.publication.data_sources import bundles
from coppersushi.publication.readiness import PublicationReceipt, require_received


class Coverage(BaseModel):
    """Source evidence and publication outcome for one historical delivery day."""
    day: date
    receipts: list[PublicationReceipt] = []
    active_rows: int | None = None
    ptdf_rows: int | None = None
    expected_intervals: int
    missing_alternatives: int | None = None
    unavailable_intervals: int | None = None
    status: Literal['blocked', 'eligible', 'published'] = 'blocked'
    errors: list[str] = []
    bucket: str | None = None


def audit(day: MarketDay) -> Coverage:
    """Inspect each source independently; a nonempty response never replaces a receipt."""
    result = Coverage(day=day.date, expected_intervals=len(day.market_time_units()))
    try:
        rows = jao._get('monitoring', day.start_time_utc, day.end_time_utc,
                        base_url='https://publicationtool.jao.eu/core/api/system')
        result.receipts = [PublicationReceipt.model_validate(row) for row in rows]
        require_received(day, result.receipts)
    except Exception as error:
        result.errors.append(f'receipts: {type(error).__name__}: {error}')
    active = context = prices = None
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
        prices = electricity_maps.load_day(str(day.date))
    except Exception as error:
        result.errors.append(f'prices: {type(error).__name__}: {error}')
    if active is not None and context is not None and prices is not None:
        try:
            from coppersushi import cnec_market
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
    args = parser.parse_args()
    if args.start > args.end or args.end >= datetime.now(tz=MARKET_TZ).date():
        parser.error('Require an ordered range ending before today')
    done: set[date] = set()
    if args.report.exists():
        for line in args.report.read_text().splitlines():
            previous = Coverage.model_validate_json(line)
            if (previous.status == ('published' if args.bucket else 'eligible')
                    and previous.bucket == args.bucket):
                done.add(previous.day)
            else:
                done.discard(previous.day)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    current = args.start
    blocked = False
    while current <= args.end:
        if current not in done:
            day = MarketDay.on(current)
            result = audit(day)
            result.bucket = args.bucket
            if args.bucket and result.status == 'eligible':
                try:
                    if not bundles.is_published(day, args.bucket):
                        prepared = bundles.prepare(day, allow_partial_attribution=True)
                        bundle.validate_publication(prepared, allow_partial_attribution=True)
                        bundles.publish(prepared, args.bucket, allow_partial_attribution=True)
                    result.status = 'published'
                except Exception as error:
                    result.status = 'blocked'
                    result.errors.append(f'publication: {type(error).__name__}: {error}')
            previous = args.report.read_text() if args.report.exists() else ''
            cache.atomic_text(args.report, previous + result.model_dump_json() + '\n')
            print(f'{current}: {result.status}; {"; ".join(result.errors)}', flush=True)
            blocked |= result.status == 'blocked'
        current += timedelta(days=1)
    raise SystemExit(1 if blocked else 0)


if __name__ == '__main__':
    main()
