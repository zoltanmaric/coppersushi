"""Compile a private physical-element catalog and coverage audit from retained JAO caches.

No downloads occur here. Raw annual responses and targeted backfill responses remain
immutable inputs. Virtual hubs and nonphysical constraints are counted, never imported
as sites or physical elements. Re-run into the same directory to retain assigned site IDs.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, UTC
import csv
import gzip
import hashlib
import json
from pathlib import Path
import uuid

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class LocatorRecord(BaseModel):
    """A located substation accepted at the catalog import boundary."""
    name: str
    x: float
    y: float
    osm_id: int | None
    template: str
    osm_type: str | None = None


class SiteAssessment(BaseModel):
    """A reviewed physical location, including junctions absent from the locator."""
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    evidence: str = Field(min_length=1)


class ElementAssessment(BaseModel):
    """A reviewed hypothesis for one exact source publication, separate from observations."""
    model_config = ConfigDict(extra='forbid')
    tso: str = Field(min_length=1)
    eic: str = Field(min_length=1)
    name: str = Field(min_length=1)
    site_a: str = Field(min_length=1)
    site_b: str = Field(min_length=1)
    direct_orientation: Literal['a_to_b','b_to_a','unknown']
    assignment_evidence: str = Field(min_length=1)
    orientation_evidence: str = Field(min_length=1)


from coppersushi import REPO, cnec_geometry as geometry
from coppersushi.data_model.osm_locator import LocatedSubstations
from coppersushi.data_sources import element_catalog, osm_locator


def stamp(value: str) -> str:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f'Naive observation timestamp: {value}')
    return moment.astimezone(UTC).isoformat()


def identity(values: tuple[str, ...]) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(values, ensure_ascii=False)))


def write(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def apply_assessments(assessments: dict[tuple[str, str, str], ElementAssessment],
                      sites: dict[str, dict], elements: list[dict],
                      endpoints: dict[tuple[str, str], dict], source_evidence: dict[str, str]) -> None:
    """Fill unresolved terminals from reviewed hypotheses without replacing source facts."""
    site_ids = defaultdict(list)
    for site in sites.values():
        site_ids[site['display_name']].append(site['site_id'])
    publications = {(row['eic'], row['tso'], row['name']): row for row in elements}
    for key, assessment in assessments.items():
        if key not in publications:
            raise ValueError(f'Unobserved element assessment: {key}')
        element = publications[key]
        pair = [endpoints[element['element_id'], terminal] for terminal in ('a', 'b')]
        if any(endpoint['status']=='conflict' for endpoint in pair):
            raise ValueError(f'Assessment conflicts with published terminals: {key}')
        selected = []
        for target in (assessment.site_a, assessment.site_b):
            matches = site_ids[target]
            if len(matches)!=1:
                raise ValueError(f'Assessment requires one site for {target}: {key}')
            selected.append(matches[0])
        if any(endpoint['site_id'] is not None and endpoint['site_id']!=site_id
               for endpoint, site_id in zip(pair, selected)):
            raise ValueError(f'Assessment contradicts a resolved terminal: {key}')
        if not all(endpoint['status']=='resolved' for endpoint in pair):
            for endpoint, site_id in zip(pair, selected):
                if endpoint['status'] != 'resolved':
                    endpoint.update(site_id=site_id, status='resolved', assignment_basis='inferred',
                                    evidence=assessment.assignment_evidence+'; original observation: '
                                             +source_evidence[element['element_id']])
            element['element_type'] = element['element_type'] or 'Line'
        if (element['orientation_basis']=='published' and assessment.direct_orientation!='unknown'
                and element['direct_orientation']!=assessment.direct_orientation):
            raise ValueError(f'Assessment contradicts published orientation: {key}')
        if element['orientation_basis']=='unknown':
            element.update(direct_orientation=assessment.direct_orientation,
                orientation_basis='unknown' if assessment.direct_orientation=='unknown' else 'inferred',
                orientation_evidence=assessment.orientation_evidence)


def sweep(cache_root: Path, backfill: Path, output: Path,
          configuration: Path = REPO/'config/element-catalog') -> dict:
    output.mkdir(parents=True, exist_ok=True)
    locations = pd.DataFrame(osm_locator.read_csvs(cache_root / 'osm-locator'))
    supplements = pd.read_csv(configuration/'osm-sites.csv')
    buses = pd.read_csv(cache_root/'osm-prebuilt-v0.7/buses.csv')
    extra = []
    for supplement in supplements.to_dict('records'):
        osm_id = int(supplement['osm_id'])
        kind = supplement['osm_type']
        if kind not in ('way','relation'):
            raise ValueError(f"Unsupported OSM object type: {kind}")
        label = f'{kind}/{osm_id}'
        document = json.loads((backfill/f"osm-{kind}-{osm_id}.json").read_text())
        matches = [e for e in document['elements'] if e.get('type')==kind and e.get('id')==osm_id]
        if len(matches)!=1 or matches[0].get('tags',{}).get('power')!='substation':
            raise ValueError(f"OSM {label} is not the expected substation")
        matched = buses[buses.tags.eq(label)][['x','y']].drop_duplicates()
        if matched.empty:
            from shapely.geometry import Polygon
            from shapely.ops import unary_union
            nodes = {e['id']:(e['lon'],e['lat']) for e in document['elements'] if e.get('type')=='node'}
            ways = {e['id']:e for e in document['elements'] if e.get('type')=='way'}
            if kind=='way':
                boundaries = matches
            else:
                site=matches[0]
                members=site.get('members',[])
                if site.get('tags',{}).get('type')!='site' or not members or any(
                    m['type']!='way' or m.get('role','') not in ('','outer') or m['ref'] not in ways for m in members):
                    raise ValueError(f"OSM {label} requires complete substation site boundaries")
                boundaries=[ways[m['ref']] for m in members]
            polygons=[]
            for boundary in boundaries:
                refs = boundary.get('nodes',[])
                if len(refs)<4 or refs[0]!=refs[-1] or any(n not in nodes for n in refs):
                    raise ValueError(f"OSM {label} requires a complete closed substation polygon")
                polygon = Polygon([nodes[n] for n in refs])
                if not polygon.is_valid or polygon.is_empty:
                    raise ValueError(f"OSM {label} has invalid substation geometry")
                polygons.append(polygon)
            centroid = unary_union(polygons).centroid
            x,y = centroid.x,centroid.y
        else:
            if (matched.max()-matched.min()).gt(.01).any():
                raise ValueError(f"Expected one cached OSM location for {label}")
            x,y = float(matched.x.mean()),float(matched.y.mean())
        extra.append(dict(name=supplement['published_name'], x=x, y=y,
                          osm_id=osm_id, osm_type=kind, template='OSM'))
    locations = pd.concat([locations,pd.DataFrame(extra)],ignore_index=True)
    # Existing IDs survive coordinate corrections and changes in representative spelling.
    old_sites = {}
    old_names = defaultdict(list)
    if (output / 'sites.csv').exists():
        with element_catalog.load(output) as db:
            old_sites = {r['site_id']: dict(r) for r in db.execute('SELECT * FROM sites')}
            for r in db.execute("SELECT * FROM site_names WHERE source IN ('osm-locator','osm')"):
                old_names[r['published_name']].append(r['site_id'])
    sites: dict[str, dict] = {}
    names: set[tuple[str,str,str]] = set()
    point_sites: dict[geometry.Point,str] = {}
    anchors: dict[str,str] = {}
    for location in locations.sort_values(['template', 'name']).to_dict('records'):
        if pd.isna(location['osm_id']): location['osm_id'] = None
        if pd.isna(location.get('osm_type')): location['osm_type'] = None
        r = LocatorRecord.model_validate(location)
        anchor = f'osm-locator:{int(r.osm_id)}' if r.osm_id is not None else f'locator:{r.template}:{r.name}'
        if r.osm_type=='relation': anchor=f'osm-locator:relation:{r.osm_id}'
        prior = [s for s in old_names[r.name] if abs(old_sites[s]['longitude']-r.x)<.01 and abs(old_sites[s]['latitude']-r.y)<.01]
        site_id = anchors.get(anchor) or (prior[0] if len(prior)==1 else identity(('site', anchor)))
        anchors[anchor] = site_id
        if site_id in sites:
            s = sites[site_id]
            if abs(s['longitude']-r.x)>.01 or abs(s['latitude']-r.y)>.01:
                raise ValueError(f'Conflicting coordinates for {anchor}; review locator identity')
        else:
            sites[site_id] = dict(site_id=site_id, display_name=r.name, longitude=r.x, latitude=r.y,
                                 evidence=(f'https://www.openstreetmap.org/{r.osm_type}/{r.osm_id}; verified OSM site coordinates' if r.template=='OSM' else f'osm-locator@{osm_locator.COMMIT}; {anchor}; template={r.template}'))
        point_sites[(float(r.x), float(r.y))] = site_id
        names.add(('osm' if r.template=='OSM' else 'osm-locator', r.name, site_id))
    assessed_sites = configuration/'assessed-sites.csv'
    if assessed_sites.exists():
        with assessed_sites.open(newline='') as stream:
            for raw in csv.DictReader(stream):
                site_assessment = SiteAssessment.model_validate(raw)
                site_id = identity(('site','assessment',site_assessment.name))
                if any(r['display_name']==site_assessment.name for r in sites.values()):
                    raise ValueError(f'Duplicate assessed site: {site_assessment.name}')
                sites[site_id] = dict(site_id=site_id, display_name=site_assessment.name,
                    longitude=site_assessment.longitude, latitude=site_assessment.latitude, evidence=site_assessment.evidence)
                names.add(('assessment',site_assessment.name,site_id))
    assessments = {}
    assessment_path = configuration/'element-assessments.csv'
    if assessment_path.exists():
        with assessment_path.open(newline='') as stream:
            for raw in csv.DictReader(stream):
                parsed_assessment = ElementAssessment.model_validate(raw)
                key = (parsed_assessment.eic,parsed_assessment.tso,parsed_assessment.name)
                if key in assessments: raise ValueError(f'Duplicate element assessment: {key}')
                assessments[key] = parsed_assessment
    index = geometry.substation_index(LocatedSubstations.validate(locations))
    aliases = osm_locator.load_aliases()
    normalized = {geometry._folded(k):v for k,v in aliases.items()}
    scoped = osm_locator.load_element_aliases()
    for name, target in aliases.items():
        hit = geometry._candidates(target, index, {})
        if hit:
            for point in hit[1]:names.add(('jao',name,point_sites[point]))

    bindings = {}
    with (configuration/'endpoint-bindings.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            binding_key = (row['eic'], row['tso'], row['element_name'], row['published_name'])
            if binding_key in bindings or row['site_id'] not in sites or not row['evidence']:
                raise ValueError(f'Invalid or duplicate endpoint binding: {binding_key}')
            bindings[binding_key] = row

    files = sorted((cache_root/'jao').rglob('element-ends.csv')) + sorted(backfill.glob('ends-*.csv'))
    # Legacy domain tables recover names absent from older endpoint caches. Multi-TSO
    # aggregated rows cannot establish publisher orientation, so they are not imported.
    files += sorted((cache_root/'jao').glob('*/elements.csv'))
    observations = defaultdict(list); legacy = defaultdict(list); manifest = []
    inputs = [*sorted((cache_root/'osm-locator').glob('*.csv')),
              cache_root/'osm-prebuilt-v0.7/buses.csv',
              *sorted(configuration.glob('*.csv')), element_catalog.SCHEMA,
              osm_locator.ALIASES_FILE, osm_locator.ELEMENT_ALIASES_FILE,
              *sorted(backfill.glob('osm-*.json')),
              *sorted(backfill.glob('raw-*.json.gz'))]
    if (output/'sites.csv').exists():
        inputs += [element_catalog.snapshot(output)/f'{table}.csv' for table in element_catalog.TABLES]
    for path in inputs:
        if path.is_relative_to(cache_root): label = str(path.relative_to(cache_root))
        elif path.is_relative_to(output): label = 'previous/' + path.name
        elif path.is_relative_to(backfill): label = 'backfill/' + path.name
        else: label = 'config/' + path.name
        manifest.append(dict(file=label,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    for path in files:
        frame = pd.read_csv(path, keep_default_na=False)
        label = str(path.relative_to(cache_root)) if path.is_relative_to(cache_root) else f'backfill/{path.name}'
        manifest.append(dict(file=label, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for row in frame.to_dict('records'):
            if ',' in row.get('tso','') or ';' in row.get('tso','') or ' / ' in row.get('tso',''): continue
            if path.name == 'elements.csv':
                # Aggregated domain tables do not establish each publisher's orientation.
                row['substation_from'] = row['substation_to'] = ''
            row['evidence'] = label
            if row.get('name'):observations[(row['eic'],row['tso'],row['name'])].append(row)
            else:legacy[(row['eic'],row['tso'])].append(row)
    counts: Counter[tuple[str,str,str]] = Counter()
    constraints = {}; external = {}
    contingency_counts: Counter[str] = Counter()
    for path in sorted((cache_root/'research/country-caps/annual-json').glob('activeFbConstraints*.gz')):
        manifest.append(dict(file=str(path.relative_to(cache_root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for row in json.load(gzip.open(path))['data']:
            record_key = (stamp(row['dateTimeUtc']),row['id'])
            if not row.get('cnecEic') or row['cnecEic']=='NA':
                external[record_key]=row.get('cnecName','');continue
            constraints[record_key]=(row['cnecEic'],row['tso'].upper(),row['cnecName'].strip(),row.get('branchEic'))
    for path in sorted((cache_root/'jao').glob('*/active-constraints.csv')):
        manifest.append(dict(file=str(path.relative_to(cache_root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for row in pd.read_csv(path,keep_default_na=False).to_dict('records'):
            timestamp=stamp(row['interval'])
            constraints[(timestamp,int(row['source_id']))]=(row['eic'],row['tso'],row['name'],row.get('branch_eic'))
    for eic,tso,name,branch in constraints.values():
        counts[(eic,tso,name)]+=1
        if branch and branch!='NA':contingency_counts[branch]+=1
    # Reviewed project mappings are inputs even when the bootstrap day did not observe them.
    keys=set(observations)|set(counts)|set(assessments)
    elements: list[dict] = []
    endpoints: dict[tuple[str, str], dict] = {}
    source_evidence: dict[str, str] = {}
    for eic,tso,name in sorted(keys):
        if not eic or not tso or not name:continue
        key=(eic,tso,name);element_id=identity(('jao',*key))
        rows=observations.get(key) or legacy.get((eic,tso),[])
        types={r.get('element_type','') for r in rows}-{''}
        element: dict = dict(element_id=element_id,source='jao',tso=tso,eic=eic,name=name,
                       element_type=next(iter(types)) if len(types)==1 else None,
                       direct_orientation='unknown', orientation_basis='unknown',
                       orientation_evidence='No unambiguous published reference terminals')
        elements.append(element)
        values={side:{r.get(f'substation_{side}','') for r in rows}-{''} for side in ('from','to')}
        published={side:next(iter(v)) if len(v)==1 else None for side,v in values.items()}
        corrected={side:(scoped.get((eic,tso,name,n),n) if n is not None else None) for side,n in published.items()}
        placement=geometry._placement(corrected['from'],corrected['to'],index,normalized)
        evidence='; '.join(sorted({r['evidence'] for r in rows})) or 'No cached endpoint metadata'
        if all(published.values()):
            element.update(direct_orientation='a_to_b', orientation_basis='published', orientation_evidence=evidence)
        source_evidence[element_id] = evidence
        for side,number in [('from',0),('to',1)]:
            n=published[side];hit=geometry._candidates(corrected[side],index,normalized)
            site_id=None
            if len(values[side])>1:status='conflict'
            elif n is None:status='missing'
            elif placement['match_status']=='matched':
                site_id=point_sites[(placement[f'x{number}'],placement[f'y{number}'])];status='resolved'
            elif hit and len(hit[1])==1:site_id=point_sites[hit[1][0]];status='resolved'
            elif hit:status='ambiguous'
            else:status='unresolved'
            binding = bindings.get((eic,tso,name,n))
            if binding and len(values[side])==1:
                site_id=binding['site_id'];status='resolved'
            method='site binding: '+binding['evidence'] if binding else 'scoped correction' if corrected[side]!=n else ('name lookup / nearest pair' if status=='resolved' else status)
            terminal = 'a' if side=='from' else 'b'
            endpoints[element_id,terminal] = dict(element_id=element_id,terminal=terminal,published_name=n,site_id=site_id,status=status,
                                  assignment_basis='inferred' if status=='resolved' else 'unknown',
                                  evidence=f'{method}; {evidence}' + (f'; conflicting names={sorted(values[side])}' if status=='conflict' else ''))
            # Only unambiguous names become reusable aliases. Scoped/nearest-pair choices do not.
            if site_id and n is not None and not binding and hit and len(hit[1])==1 and corrected[side]==n:names.add(('jao',n,site_id))
    apply_assessments(assessments, sites, elements, endpoints, source_evidence)
    audit=[]
    for element in elements:
        element_id=element['element_id']
        key=(element['eic'],element['tso'],element['name'])
        statuses=[endpoints[element_id,terminal]['status'] for terminal in ('a','b')]
        evidence='; '.join(dict.fromkeys(endpoints[element_id,terminal]['evidence'] for terminal in ('a','b')))
        status = ('orientation_unknown' if element['direct_orientation']=='unknown' else 'resolved') if statuses==['resolved','resolved'] else '/'.join(statuses)
        audit.append(dict(element_id=element_id,eic=element['eic'],tso=element['tso'],name=element['name'],appearances=counts[key],
                          status=status,
                          orientation_basis=element['orientation_basis'],
                          endpoint_evidence=evidence))
    records={'sites':list(sites.values()),'site_names':[dict(source=s,published_name=n,site_id=i) for s,n,i in sorted(names)],
             'elements':elements,'element_endpoints':list(endpoints.values())}
    # Stage and validate before replacing the previously validated catalog.
    staging=output/'.generations'/uuid.uuid4().hex;staging.mkdir(parents=True)
    import sqlite3
    with sqlite3.connect(':memory:') as db:
        db.executescript(element_catalog.SCHEMA.read_text())
        for table,rows in records.items():
            columns=[r[1] for r in db.execute(f'PRAGMA table_info({table})')]
            write(staging/f'{table}.csv',columns,rows)
    with element_catalog.load(staging):pass
    write(staging/'audit.csv',list(audit[0]),sorted(audit,key=lambda r:-r['appearances']))
    write(staging/'contingencies.csv',['eic','appearances','has_monitored_record'],[
        dict(eic=k,appearances=v,has_monitored_record=k in {x[0] for x in keys}) for k,v in contingency_counts.most_common()])
    summary=dict(sites=len(sites),elements=len(elements),physical_constraint_observations=len(constraints),
                 excluded_nonphysical_observations=len(external),endpoint_statuses=dict(Counter(r['status'] for r in endpoints.values())),
                 fully_resolved_elements=sum(r['status']=='resolved' for r in audit),
                 reviewed_assessments=len(assessments),
                 inferred_orientation_elements=sum(r['orientation_basis']=='inferred' for r in elements),
                 unresolved_active_appearances=sum(int(r['appearances']) for r in audit if r['status']!='resolved'))
    (staging/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (staging/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # Readers pin current once; publishing changes only this one directory pointer.
    pointer = output/f'.current-{uuid.uuid4().hex}'
    pointer.symlink_to(staging.relative_to(output), target_is_directory=True)
    pointer.replace(output/'current')
    for path in staging.iterdir():
        link = output/f'.link-{uuid.uuid4().hex}'
        link.symlink_to(Path('current')/path.name)
        link.replace(output/path.name)
    return summary


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-root',type=Path,required=True)
    p.add_argument('--backfill',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();print(json.dumps(sweep(args.cache_root,args.backfill,args.output),indent=2))


if __name__=='__main__':main()
