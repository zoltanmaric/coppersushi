"""Build a frozen study from the investigated baseline and immutable prepared extension.

Inputs and output stay outside Git. All binding map intervals are fetched and reconciled
before output is written; a missing source, revision or count mismatch fails the build.
"""
import argparse
import csv
import gzip
import hashlib
import json
import time as clock
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, time, UTC
from pathlib import Path
from urllib.request import urlopen
from pydantic import BaseModel, AwareDatetime, FiniteFloat, field_validator

from coppersushi.pipelines.cnec.attribution import POSITION_TOLERANCE_MW
from coppersushi.pipelines.cnec.investigation import BindingInterval, Coverage, ImportBreakdown, Investigation, SourceArtifact, StudyManifest
from coppersushi.pipelines.cnec.models import DayManifest, DayMetadata, MarketInterval
from coppersushi.pipelines.market_day import MarketDay, MARKET_TZ

BASE='https://coppersushi.121gigawatts.org/data/cnec/v3'

class Observation(BaseModel):
    """Validated baseline row; extra neighbouring-price research columns are unused."""
    interval: AwareDatetime
    import_limit: FiniteFloat
    export_limit: FiniteFloat
    polish_position: FiniteFloat
    polish_alt: FiniteFloat | None
    PL: FiniteFloat
    binding_known: bool
    binding_export: bool
    procured_mw: FiniteFloat
    required_mw: FiniteFloat
    procured_published: AwareDatetime
    required_published: AwareDatetime

    @field_validator('polish_alt', mode='before')
    @classmethod
    def missing_alternative(cls,value):
        return None if value=='' else value


def cached_json(path: Path, url: str):
    if not path.exists():
        for attempt in range(4):
            try:
                with urlopen(url, timeout=45) as response:
                    body=response.read()
                break
            except HTTPError as error:
                if error.code not in (429,500,502,503,504) or attempt==3:raise
                clock.sleep(2**attempt)
            except (URLError,OSError):
                if attempt==3:raise
                clock.sleep(2**attempt)
        if body[:2]==b'\x1f\x8b':body=gzip.decompress(body)
        json.loads(body)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(body)
        path.with_suffix('.retrieval.json').write_text(json.dumps({'url':url,'retrieved_at':datetime.now(UTC).isoformat(),
                                                                 'sha256':hashlib.sha256(body).hexdigest()}))
    return json.loads(path.read_text())


def eligible(day: date, required: float, purchased: float, required_at: datetime, purchased_at: datetime):
    cutoff=datetime.combine(day-timedelta(days=1),time(10,30),MARKET_TZ).astimezone(UTC)
    if min(required,purchased)<0 or required_at>=cutoff or purchased_at>=cutoff:
        raise ValueError(f'Invalid reserve evidence for {day}')


def downward_products(records, fields, day):
    """Keep the latest eligible publication per UTC hour, independently per endpoint."""
    from coppersushi.pipelines.cnec.reserves import ReserveRecord
    cutoff = datetime.combine(day - timedelta(days=1), time(10, 30), MARKET_TZ)
    versions = {}
    for row in records:
        if row['business_date'] != str(day):
            raise ValueError('Wrong PSE delivery day')
        record = ReserveRecord(end=datetime.fromisoformat(row['dtime_utc']).replace(tzinfo=UTC),
                               published=datetime.fromisoformat(row['publication_ts_utc']).replace(tzinfo=UTC),
                               products=tuple(row[f] for f in fields))
        if record.published < cutoff:
            versions.setdefault(record.end, {}).setdefault(record.published, set()).add(record.products)
    result = {}
    for end, by_publication in versions.items():
        latest = by_publication[max(by_publication)]
        if len(latest) != 1:
            raise ValueError(f'Ambiguous downward reserve observation at {end}')
        result[end] = next(iter(latest))
    return result


def build(baseline: Path, extension: Path, directory: Path, end: date = date(2026, 11, 17)) -> Investigation:
    start = date(2026, 8, 14)
    frozen_end = date(2026, 11, 17)
    if end < frozen_end:
        raise ValueError('Study must include the original November 17 window')
    old=[Observation.model_validate(r) for r in csv.DictReader(baseline.open())]
    expected_old={t.to_pydatetime() for d in range(92) for t in MarketDay.on(start+timedelta(days=d)).market_time_units()}
    if len(old)!=len(expected_old) or {r.interval for r in old}!=expected_old:
        raise ValueError('Baseline must contain exactly the 8,836 distinct investigated MTUs')
    baseline_by_time={r.interval:r for r in old}
    binding_by_day:dict[date,list[tuple[int,Observation]]]={}
    import_times = []
    unknown_imports = 0
    for r in old:
        if abs(r.polish_position + r.import_limit) <= POSITION_TOLERANCE_MW:
            if r.polish_alt is None:
                unknown_imports += 1
            elif r.PL - r.polish_alt > 0.01:
                import_times.append(r.interval)
        day=r.interval.astimezone(MARKET_TZ).date()
        eligible(day,r.required_mw,r.procured_mw,r.required_published,r.procured_published)
        inferred=r.polish_alt is not None and abs(r.polish_position-r.export_limit)<=POSITION_TOLERANCE_MW and r.polish_alt-r.PL>0.01
        known=r.polish_alt is not None or r.export_limit-r.polish_position>POSITION_TOLERANCE_MW
        if not known or not r.binding_known or r.binding_export!=inferred or r.export_limit<0:
            raise ValueError(f'Unknown or inconsistent binding classification at {r.interval}')
        if inferred:
            index=list(MarketDay.on(day).market_time_units()).index(r.interval)
            binding_by_day.setdefault(day,[]).append((index,r))
    maps=directory/'data/cnec/v3'
    generations={}
    sources=[SourceArtifact(label='Investigated baseline: 14 August–13 November 2026',sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
                            retrieved_at=None,url=None)]
    rows=[]
    overlap=0
    def one_day(day:date):
        # Preserve the exact extension generations used by the investigated prototype.
        src=extension/str(day)
        if date(2026,11,13)<=day<=frozen_end:
            manifest=DayManifest.model_validate_json((src/'manifest.json').read_text())
        else:
            manifest=DayManifest.model_validate(cached_json(maps/str(day)/'manifest.json',f'{BASE}/{day}/manifest.json'))
        if manifest.day!=day:raise ValueError('Wrong manifest day')
        folder=maps/str(day)/manifest.generation
        folder.mkdir(parents=True,exist_ok=True)
        def part(name):
            target=folder/f'{name}.json'
            if date(2026,11,13)<=day<=frozen_end and not target.exists():
                target.write_bytes((src/f'{name}.json').read_bytes())
            return cached_json(target,f'{BASE}/{day}/{manifest.generation}/{name}.json')
        meta=DayMetadata.model_validate(part('metadata'))
        times=MarketDay.on(day).market_time_units()
        if meta.day!=day or len(meta.labels)!=len(times):raise ValueError(f'Invalid calendar: {day}')
        wanted=list(range(len(times))) if day>=date(2026,11,13) else [i for i,_ in binding_by_day.get(day,[])]
        import_extension = []
        selected=[]; compared=0; extension_count=0
        for i in wanted:
            x=MarketInterval.model_validate(part(i))
            if x.index!=i or x.label!=meta.labels[i]:raise ValueError(f'Wrong interval identity {day}/{i}')
            if any('attribution' in note.lower() for note in x.notes):raise ValueError(f'Incomplete attribution {day}/{i}')
            caps=[c for c in x.caps if c.direction=='export' and c.shadow_price>0.01]
            if len(caps)>1:raise ValueError('Ambiguous export caps')
            reserves=x.polish_upward_reserves
            if reserves is None or reserves.required.status!='available' or reserves.purchased.status!='available':
                raise ValueError(f'Missing reserve evidence {day}/{i}')
            r,p=reserves.required,reserves.purchased
            eligible(day,r.mw,p.mw,r.published_at,p.published_at)
            if abs(sum(r.products)-r.mw)>1e-7 or abs(sum(p.products)-p.mw)>1e-7:raise ValueError('Reserve product sum mismatch')
            t=times[i].to_pydatetime()
            if t in baseline_by_time:
                old=baseline_by_time[t]
                if (bool(caps)!=old.binding_export or r.mw!=old.required_mw or p.mw!=old.procured_mw or
                    r.published_at!=old.required_published or p.published_at!=old.procured_published):
                    raise ValueError(f'Baseline/map evidence mismatch {day}/{i}')
                if caps and (abs(caps[0].shadow_price-(old.polish_alt-old.PL))>1e-6 or caps[0].capacity!=old.export_limit or x.prices['PL']!=old.PL):
                    raise ValueError(f'Baseline/map market mismatch {day}/{i}')
                compared+=day==date(2026,11,13)
            else:
                extension_count += 1
                if any(cap.direction == 'import' and cap.shadow_price > 0.01 for cap in x.caps):
                    import_extension.append(t)
            if caps:
                selected.append(BindingInterval(utc=t,date=day,index=i,shadow=caps[0].shadow_price,
                                                 required=r,procured=p,cap=caps[0].capacity,price=x.prices['PL']))
        (maps/str(day)/'manifest.json').write_text(manifest.model_dump_json())
        return day,manifest.generation,selected,compared,extension_count,import_extension
    days=[start+timedelta(days=i) for i in range((end-start).days+1)]
    extension_count=0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(one_day,d):d for d in days}
        for future in as_completed(futures):
            day,generation,selected,compared,count,imports=future.result()
            import_times.extend(imports)
            generations[str(day)]=generation;rows.extend(selected);overlap+=compared;extension_count+=count
            print(f'{len(generations)}/{len(days)} {day}: {len(selected)} binding map rows reconciled',flush=True)
    expected=sum(len(MarketDay.on(day).market_time_units()) for day in days)
    if overlap!=96 or extension_count!=expected-len(old):raise ValueError('Incomplete extension or overlap')
    for day in days:
        folder=maps/str(day)/generations[str(day)]
        for file in sorted(folder.glob('*.json')):
            if file.name.endswith('.retrieval.json'):continue
            sidecar=file.with_suffix('.retrieval.json')
            origin=extension/str(day)/sidecar.name
            evidence=json.loads(sidecar.read_text()) if sidecar.exists() else json.loads(origin.read_text()) if origin.exists() else None
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            if evidence and evidence['sha256']!=digest:raise ValueError('Source digest mismatch')
            sources.append(SourceArtifact(label=f'{day}/{file.name}',sha256=digest,retrieved_at=evidence['retrieved_at'] if evidence else None,
                                          url=f'{BASE}/{day}/{generations[str(day)]}/{file.name}'))
    rows.sort(key=lambda r:r.utc)
    shortfall=sum(r.required.mw>r.procured.mw for r in rows)
    down_short = 0
    cache = directory / 'pse-reserve-inputs'
    cache.mkdir(exist_ok=True)
    import_days = sorted({t.astimezone(MARKET_TZ).date() for t in import_times})
    from scripts.polish_export_caps import pse
    for day in import_days:
        totals = []
        for endpoint, fields in [('wmb', ('fcrd', 'afrrd', 'frrd', 'rrd')),
                                 ('mbp-tp', ('fcr_d', 'afrr_d', 'mfrrd_d', 'rr_d'))]:
            records = pse(endpoint, str(day), cache)
            path = cache / f'{day}-{endpoint}.json'
            receipt = json.loads(path.with_suffix('.json.retrieval.json').read_text())
            if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['sha256']:
                raise ValueError('Downward reserve source digest mismatch')
            sources.append(SourceArtifact(label=f'{day} downward {endpoint}', sha256=receipt['sha256'],
                                          retrieved_at=receipt['completed_at'], url=receipt['urls'][0]))
            totals.append(downward_products(records, fields, day))
        for t in import_times:
            if t.astimezone(MARKET_TZ).date() != day:
                continue
            hour_end = t.replace(minute=0) + timedelta(hours=1)
            req, bought = (source[hour_end] for source in totals)
            if any(v is None for v in req) or any(v is None for v in bought[:3]) or req[3] != 0:
                raise ValueError(f'Incomplete downward three-product comparison at {t}')
            down_short += sum(req[:3]) > sum(bought[:3])
    imports = ImportBreakdown(shortfall=down_short, no_shortfall=len(import_times)-down_short, unconfirmed=unknown_imports)
    coverage=Coverage(imports=imports,expected=expected,observed=len(old)+extension_count,unknown=0,binding=len(rows),nonbinding=expected-len(rows),
                      shortfall_binding=shortfall,no_shortfall_binding=len(rows)-shortfall)
    frozen_rows=[row for row in rows if row.date<=frozen_end]
    if (len(frozen_rows),sum(row.required.mw>row.procured.mw for row in frozen_rows))!=(2359,197):raise ValueError('Study counts differ from the investigated window')
    return Investigation(start=start,end=end,coverage=coverage,rows=rows,generations=dict(sorted(generations.items())),sources=sources,overlap_verified=overlap)


def write_study(study: Investigation, directory: Path) -> str:
    folder=directory/'data/cnec/studies/polish-export-caps'
    folder.mkdir(parents=True,exist_ok=True)
    content=study.model_dump_json()
    generation=hashlib.sha256(content.encode()).hexdigest()[:24]
    from coppersushi.pipelines.data_sources.cache import atomic_text
    atomic_text(folder/f'{generation}.json',content)
    atomic_text(folder/'manifest.json',json.dumps({'version':1,'generation':generation}))
    return generation


def publish(directory: Path, bucket: str) -> None:
    """Validate the local artifact; upload immutable content before its manifest."""
    from coppersushi.pipelines.data_sources import cache
    folder=directory/'data/cnec/studies/polish-export-caps'
    pointer=StudyManifest.model_validate_json((folder/'manifest.json').read_text())
    content=(folder/f'{pointer.generation}.json').read_bytes()
    study=Investigation.model_validate_json(content)
    if hashlib.sha256(content).hexdigest()[:24]!=pointer.generation:
        raise ValueError('Study content hash does not match manifest')
    client=cache._client()
    # The map generations are existing public objects, not part of frontend publication.
    for day,generation in study.generations.items():
        client.head_object(Bucket=bucket,Key=f'data/cnec/v3/{day}/{generation}/metadata.json')
    prefix='data/cnec/studies/polish-export-caps'
    for name,body,lifetime in [(f'{pointer.generation}.json',content,'public,max-age=31536000,immutable'),
                                ('manifest.json',(folder/'manifest.json').read_bytes(),'public,max-age=60')]:
        client.put_object(Bucket=bucket,Key=f'{prefix}/{name}',Body=gzip.compress(body,mtime=0),ContentType='application/json',
                          ContentEncoding='gzip',CacheControl=lifetime)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    builder=commands.add_parser('build')
    builder.add_argument('--baseline',type=Path,required=True)
    builder.add_argument('--end',type=date.fromisoformat,default=date(2026,11,17))
    builder.add_argument('--extension',type=Path,required=True)
    builder.add_argument('--directory',type=Path,required=True)
    publisher=commands.add_parser('publish')
    publisher.add_argument('--directory',type=Path,required=True)
    publisher.add_argument('--bucket',required=True)
    args=parser.parse_args()
    if args.command=='publish':
        publish(args.directory,args.bucket)
    else:
        study=build(args.baseline,args.extension,args.directory,args.end)
        generation=write_study(study,args.directory)
        print(f'COMPLETE {generation}: {study.coverage.model_dump()}',flush=True)

if __name__=='__main__':main()
