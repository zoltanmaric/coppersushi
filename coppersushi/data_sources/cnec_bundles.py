"""Prepare and atomically publish versioned browser data; raw caches remain private."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path

from coppersushi import REPO, cnec_bundle
from coppersushi.cnec_bundle import Day
from coppersushi.data_model.cnec_bundle import DayBundle
from coppersushi.data_model.market import ZonalPrices
from coppersushi.data_sources import cache, cnec_attribution, electricity_maps, element_catalog, jao, zone_shapes
from coppersushi.market_day import MarketDay


def prepare(day: MarketDay, indices: list[int] | None = None, refresh: bool = False) -> DayBundle:
    """Construct domain data without importing or invoking the web application's renderer."""
    key = day.date.isoformat()
    active = jao.load_active_day(key, refresh=refresh)
    prices = electricity_maps.load_day(key, refresh=refresh)
    inputs = Day(day, zone_shapes.load(), active.constraints, active.ptdfs,
                 ZonalPrices.validate(prices), cnec_attribution.load_day(day, refresh=refresh))
    directory = Path(os.environ.get('COPPERSUSHI_ELEMENT_CATALOG', str(REPO / 'data/element-catalog')))
    mapped, pending = element_catalog.resolution_inputs(directory)
    times = day.market_time_units()
    requested = list(range(len(times))) if indices is None else indices
    if any(i < 0 or i >= len(times) for i in requested):
        raise ValueError('Interval is outside the selected market day')
    geometry = {i: element_catalog.resolve_loaded(times[i], active.constraints[active.constraints.interval.eq(times[i])], mapped, pending)
                for i in requested}
    return cnec_bundle.build(inputs, geometry)


def publish(bundle: DayBundle, bucket: str) -> str:
    """Write every immutable object before replacing the small day manifest."""
    if [i.index for i in bundle.intervals] != list(range(len(bundle.labels))):
        raise ValueError('Only complete days may be published')
    payload = bundle.model_dump_json().encode()
    generation = hashlib.sha256(payload).hexdigest()[:24]
    prefix = f'data/cnec/v1/{bundle.day}/{generation}'
    client = cache._client()

    def put(key: str, body: bytes, lifetime: str) -> None:
        client.put_object(Bucket=bucket, Key=key, Body=gzip.compress(body, mtime=0),
                          ContentType='application/json', ContentEncoding='gzip', CacheControl=lifetime)

    immutable = 'public,max-age=31536000,immutable'
    put(f'{prefix}/day.json', payload, immutable)
    for interval in bundle.intervals:
        used = {r.geometry for r in interval.constraints if r.geometry is not None}
        partial = bundle.model_copy(update={'intervals': [interval],
                                            'elements': {k: v for k, v in bundle.elements.items() if k in used}})
        put(f'{prefix}/{interval.index}.json', partial.model_dump_json().encode(), immutable)
    manifest = json.dumps({'version': 1, 'day': str(bundle.day), 'generation': generation}).encode()
    put(f'data/cnec/v1/{bundle.day}/manifest.json', manifest, 'public,max-age=60')
    return generation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('day')
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    day = MarketDay.on(args.day)
    print(publish(prepare(day, refresh=args.refresh), args.bucket))

if __name__ == '__main__':
    main()
