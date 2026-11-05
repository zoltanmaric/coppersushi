"""Retain targeted JAO domain responses for physical identities absent from the cache.

Imports all physical domain rows, not just presolved rows. Requests are serial and
paced below the shared JAO limit. A failed/empty response never replaces a success.
"""
import argparse
import csv
from collections import defaultdict
import gzip
import json
import logging
from pathlib import Path
import time
import urllib.error
import urllib.request

import pandas as pd

from coppersushi import REPO, cnecs
from coppersushi.data_sources import jao
from coppersushi.data_sources.catalog_sweep import stamp


def endpoints(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=cnecs.END_COLUMNS)
    frame = cnecs._physical(cnecs._frame(rows))
    return frame.assign(tso=cnecs.normalise_tso(frame.tso))[cnecs.END_COLUMNS].drop_duplicates()


def backfill(cache_root: Path, output: Path, max_requests: int) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    # Reprocessing retained responses also repairs exports made by a presolved-only importer.
    for path in sorted(output.glob('raw-*.json.gz')):
        with gzip.open(path, 'rt') as stream:
            frame = endpoints(json.load(stream))
        if not frame.empty:
            frame.to_csv(output/path.name.replace('raw-', 'ends-').replace('.json.gz', '.csv'), index=False)
    known = set()
    for path in [*sorted((cache_root/'jao').rglob('element-ends.csv')), *sorted(output.glob('ends-*.csv'))]:
        frame = pd.read_csv(path, keep_default_na=False).reindex(columns=cnecs.END_COLUMNS, fill_value='')
        for row in frame.to_dict('records'):
            if row['substation_from'] and row['substation_to']:
                known.add((row['eic'], row['tso'], row['name']))
    observations = {}
    for path in sorted((cache_root/'research/country-caps/annual-json').glob('activeFbConstraints*.gz')):
        with gzip.open(path, 'rt') as stream:
            for row in json.load(stream)['data']:
                if row.get('cnecEic') and row['cnecEic'] != 'NA':
                    observations[(stamp(row['dateTimeUtc']),row['id'])] = row
    hours: dict[pd.Timestamp, set[tuple[str,str,str]]] = defaultdict(set)
    needed: dict[tuple[str,str,str], int] = defaultdict(int)
    for row in observations.values():
        key = (row['cnecEic'],row['tso'].upper(),row['cnecName'].strip())
        needed[key] += 1
        hours[pd.to_datetime(row['dateTimeUtc'], utc=True).floor('h')].add(key)
    missing = set(needed)-known
    history_path = output/'attempt-history.json'
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    tried_hours = {pd.to_datetime(stamp(item['hour']), utc=True) for item in history if item['status']=='success'}
    summary_path = output/'backfill-summary.json'
    if summary_path.exists():
        tried_hours.update(pd.to_datetime(stamp(item['hour']), utc=True) for item in
                           json.loads(summary_path.read_text()).get('attempts', []) if item['status']=='success')
    for raw in output.glob('raw-*.json.gz'):
        tag = raw.name.removeprefix('raw-').removesuffix('.json.gz')
        fmt = '%Y%m%dT%HZ' if len(tag)==12 else '%Y%m%dT%H%MZ'
        tried_hours.add(pd.to_datetime(tag, format=fmt, utc=True))
    attempts: list[dict] = []
    attempted: set[tuple[str,str,str]] = set()
    while missing and len(attempts)<max_requests:
        candidates = {hour: keys & missing - attempted for hour,keys in hours.items() if hour not in tried_hours}
        if not candidates: break
        hour = max(candidates, key=lambda h: sum(needed[k] for k in candidates[h]))
        targets = candidates[hour]
        if not targets: break
        attempted.update(targets)
        tried_hours.add(hour)
        tag = hour.strftime('%Y%m%dT%HZ')
        started = time.monotonic()
        result = dict(hour=hour.isoformat(), targeted_identities=len(targets))
        try:
            raw = output/f'raw-{tag}.json.gz'
            if raw.exists():
                with gzip.open(raw, 'rt') as stream: rows=json.load(stream)
            else:
                rows = jao._get('finalComputation',hour,hour+pd.Timedelta(hours=1),timeout=90)
                if rows:
                    with gzip.open(raw, 'wt') as stream: json.dump(rows,stream)
            frame = endpoints(rows)
            if not frame.empty:
                frame.to_csv(output/f'ends-{tag}.csv',index=False)
                for item in frame.fillna('').to_dict('records'):
                    if item['substation_from'] and item['substation_to']:
                        known.add((item['eic'],item['tso'],item['name']))
            result['status'] = 'success' if rows else 'empty'
        except (OSError, ValueError, KeyError) as error:
            result['status'] = 'failed'
            result['error'] = str(error)
            if isinstance(error, urllib.error.HTTPError) and error.code==429:
                result['retry_after'] = error.headers.get('Retry-After', '60')
                attempts.append(result)
                history.append(result)
                history_path.write_text(json.dumps(history,indent=2)+'\n')
                break
        attempts.append(result)
        history.append(result)
        history_path.write_text(json.dumps(history,indent=2)+'\n')
        missing=set(needed)-known
        summary=dict(identities=len(needed), missing=len(missing), attempts=attempts)
        (output/'backfill-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(f'{len(attempts)} requests; {len(missing)} missing identities',flush=True)
        time.sleep(max(0,1.5-(time.monotonic()-started)))
    summary=dict(identities=len(needed), missing=len(set(needed)-known), attempts=attempts)
    (output/'backfill-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def fetch_site_evidence(output: Path) -> None:
    """Retain primary OSM tags for the explicitly curated supplemental way IDs."""
    output.mkdir(parents=True,exist_ok=True)
    with (REPO/'config/element-catalog/osm-sites.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            way=int(row['osm_way'])
            path=output/f'osm-way-{way}.json'
            if path.exists(): continue
            with urllib.request.urlopen(f'https://api.openstreetmap.org/api/0.6/way/{way}.json',timeout=20) as response:
                document=json.load(response)
            item=document['elements'][0]
            if item['id']!=way or item['type']!='way' or item.get('tags',{}).get('power')!='substation':
                raise ValueError(f'OSM way/{way} is not the expected substation')
            path.write_text(json.dumps(document,indent=2)+'\n')


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-requests',type=int,required=True)
    parser.add_argument('--fetch-osm',action='store_true')
    args=parser.parse_args()
    if args.max_requests<0:parser.error('--max-requests must be nonnegative')
    if args.fetch_osm:fetch_site_evidence(args.output)
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(backfill(args.cache_root,args.output,args.max_requests),indent=2))


if __name__=='__main__':main()
