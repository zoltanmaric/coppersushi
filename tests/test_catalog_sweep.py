"""Synthetic cache imports and backfill coverage."""
from coppersushi import REPO
FIXTURE = REPO / 'tests' / 'fixtures' / 'element-catalog'


def test_sweep_is_repeatable_and_keeps_conflicting_source_names(tmp_path):
    from coppersushi.data_sources.catalog_sweep import sweep
    root = FIXTURE.parent / 'catalog-sweep'
    result = sweep(root/'cache', root/'backfill', tmp_path, root/'config')
    assert result['fully_resolved_elements'] == 1
    assert result['endpoint_statuses']['conflict'] == 1
    from coppersushi.data_sources.element_catalog import snapshot
    pinned = snapshot(tmp_path)
    before = {name: (tmp_path/f'{name}.csv').read_bytes()
              for name in ('sites', 'site_names', 'elements', 'element_endpoints')}
    assert sweep(root/'cache', root/'backfill', tmp_path, root/'config') == result
    assert snapshot(tmp_path) != pinned
    assert all((pinned/f'{name}.csv').read_bytes() == content for name,content in before.items())
    assert before == {name: (tmp_path/f'{name}.csv').read_bytes() for name in before}


def test_backfill_includes_nonpresolved_physical_elements():
    import json
    from coppersushi.data_sources.catalog_backfill import endpoints
    path = FIXTURE.parent/'synthetic-jao'/'final-computation-hour.json'
    frame = endpoints(json.loads(path.read_text())['data'])
    line = frame[frame.eic.eq('94T-220-0-N203AR')].iloc[0]
    assert line.substation_from == 'Silverbeck 2'
    assert line.substation_to == 'Thornwick'


def test_backfill_advances_past_retained_hours_but_retries_transient_failures(tmp_path, monkeypatch):
    import gzip
    import json
    import pandas as pd
    from coppersushi.data_sources import catalog_backfill, jao
    annual=tmp_path/'cache/research/country-caps/annual-json'
    annual.mkdir(parents=True)
    with gzip.open(annual/'activeFbConstraints-synthetic.gz','wb') as stream:
        stream.write((FIXTURE.parent/'catalog-sweep/annual.json').read_bytes())
    output=tmp_path/'backfill'
    calls=[]
    def fail(*args,**kwargs):
        calls.append(args[1])
        raise OSError('transient outage')
    monkeypatch.setattr(jao,'_get',fail)
    monkeypatch.setattr(catalog_backfill.time,'sleep',lambda _:None)
    catalog_backfill.backfill(tmp_path/'cache',output,1)
    catalog_backfill.backfill(tmp_path/'cache',output,1)
    assert calls == [pd.Timestamp('2026-01-01',tz='UTC')]*2
    with gzip.open(output/'raw-20260101T00Z.json.gz','wt') as stream:
        json.dump([],stream)
    catalog_backfill.backfill(tmp_path/'cache',output,1)
    assert calls[-1] == pd.Timestamp('2026-01-02',tz='UTC')


def test_verified_polygon_adds_a_site_absent_from_old_bus_cache(tmp_path):
    import shutil
    from coppersushi.data_sources.catalog_sweep import sweep
    from coppersushi.data_sources.element_catalog import load
    root = FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source = tmp_path/'input'
    shutil.copyfile(root/'supplement/osm-sites.csv',source/'config/osm-sites.csv')
    shutil.copyfile(root/'supplement/osm-way-424242.json',source/'backfill/osm-way-424242.json')
    sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    with load(tmp_path/'output') as db:
        row = db.execute("SELECT longitude,latitude FROM sites WHERE display_name='New station'").fetchone()
        assert tuple(row) == (5.1,47.1)


def test_missing_polygon_node_is_rejected_instead_of_using_partial_geometry(tmp_path):
    import shutil
    import json
    import pytest
    from coppersushi.data_sources.catalog_sweep import sweep
    root = FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source = tmp_path/'input'
    shutil.copyfile(root/'supplement/osm-sites.csv',source/'config/osm-sites.csv')
    document=json.loads((root/'supplement/osm-way-424242.json').read_text())
    document['elements'].pop(0)
    (source/'backfill/osm-way-424242.json').write_text(json.dumps(document))
    with pytest.raises(ValueError,match='complete closed'):
        sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')


def test_substation_site_relation_uses_complete_member_boundaries(tmp_path):
    import shutil
    from coppersushi.data_sources.catalog_sweep import sweep
    from coppersushi.data_sources.element_catalog import load
    root = FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source=tmp_path/'input'
    shutil.copyfile(root/'supplement/relation-sites.csv',source/'config/osm-sites.csv')
    shutil.copyfile(root/'supplement/osm-relation-424242.json',source/'backfill/osm-relation-424242.json')
    sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    with load(tmp_path/'output') as db:
        row=db.execute("SELECT * FROM sites WHERE display_name='New station'").fetchone()
        assert (row['longitude'],row['latitude']) == (5.1,47.1)
        assert 'openstreetmap.org/relation/424242' in row['evidence']


def test_assessment_resolves_missing_sites_without_fabricating_publication(tmp_path):
    import csv
    import shutil
    from coppersushi.data_sources.catalog_sweep import sweep
    from coppersushi.data_sources.element_catalog import load, mapped_elements
    root = FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source=tmp_path/'input'
    import gzip
    annual=source/'cache/research/country-caps/annual-json'
    annual.mkdir(parents=True)
    with gzip.open(annual/'activeFbConstraints-synthetic.gz','wb') as stream:
        stream.write((root/'annual.json').read_bytes())
    first=sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    with load(tmp_path/'output') as db:
        missing=dict(db.execute("SELECT e.* FROM elements e JOIN element_endpoints p USING(element_id) WHERE p.status='missing' LIMIT 1").fetchone())
    with (source/'config/element-assessments.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['tso','eic','name','site_a','site_b','direct_orientation','assignment_evidence','orientation_evidence'])
        writer.writeheader()
        writer.writerow(dict(tso=missing['tso'],eic=missing['eic'],name=missing['name'],site_a='Westhaven',site_b='Eastfield',direct_orientation='b_to_a',assignment_evidence='synthetic hypothesis',orientation_evidence='synthetic direction'))
    result=sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    assert result['fully_resolved_elements']==first['fully_resolved_elements']+1
    with load(tmp_path/'output') as db:
        endpoints=db.execute('SELECT * FROM element_endpoints WHERE element_id=?',(missing['element_id'],)).fetchall()
        assert all(r['assignment_basis']=='inferred' and r['published_name'] is None for r in endpoints)
    line=mapped_elements(tmp_path/'output').set_index('name').loc[missing['name']]
    assert (line.x0,line.x1)==(4.,3.)


def test_assessment_cannot_overwrite_a_resolved_published_pair(tmp_path):
    import csv
    import shutil
    import pytest
    from coppersushi.data_sources.catalog_sweep import sweep
    from coppersushi.data_sources.element_catalog import load
    root=FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source=tmp_path/'input'
    sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    with load(tmp_path/'output') as db:
        row=dict(db.execute("SELECT * FROM elements WHERE name='Westhaven-Eastfield'").fetchone())
    with (source/'config/element-assessments.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['tso','eic','name','site_a','site_b','direct_orientation','assignment_evidence','orientation_evidence'])
        writer.writeheader()
        writer.writerow(dict(tso=row['tso'],eic=row['eic'],name=row['name'],site_a='Eastfield',site_b='Westhaven',direct_orientation='a_to_b',assignment_evidence='contradictory synthetic guess',orientation_evidence='synthetic'))
    with pytest.raises(ValueError,match='contradicts a resolved terminal'):
        sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')


def test_orientation_assessment_applies_without_replacing_resolved_sites():
    from coppersushi.data_sources.catalog_sweep import ElementAssessment, apply_assessments
    import pytest
    sites = {'s1': {'site_id': 's1', 'display_name': 'Alpha'},
             's2': {'site_id': 's2', 'display_name': 'Beta'}}
    element = dict(element_id='e', eic='E', tso='T', name='Line', element_type='Line',
                   direct_orientation='unknown', orientation_basis='unknown', orientation_evidence='missing')
    endpoints = {('e', 'a'): dict(site_id='s1', status='resolved', evidence='source A'),
                 ('e', 'b'): dict(site_id='s2', status='resolved', evidence='source B')}
    assessment = ElementAssessment(tso='T', eic='E', name='Line', site_a='Alpha', site_b='Beta',
        direct_orientation='b_to_a', assignment_evidence='site guess', orientation_evidence='direction guess')
    apply_assessments({('E', 'T', 'Line'): assessment}, sites, [element], endpoints, {'e': 'source'})
    assert element['direct_orientation'] == 'b_to_a'
    assert element['orientation_basis'] == 'inferred'
    assert endpoints['e', 'a']['evidence'] == 'source A'
    element.update(direct_orientation='a_to_b', orientation_basis='published')
    with pytest.raises(ValueError, match='contradicts published orientation'):
        apply_assessments({('E', 'T', 'Line'): assessment}, sites, [element], endpoints, {'e': 'source'})


def test_audit_credits_the_endpoint_evidence_actually_used(tmp_path):
    import csv
    import shutil
    from coppersushi.data_sources.catalog_sweep import sweep
    root=FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source=tmp_path/'input'
    config=source/'config/element-assessments.csv'
    with config.open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['tso','eic','name','site_a','site_b','direct_orientation','assignment_evidence','orientation_evidence'])
        writer.writeheader()
        writer.writerow(dict(tso='TEST',eic='99T-SYNTHETIC',name='Westhaven-Eastfield',site_a='Westhaven',site_b='Eastfield',direct_orientation='a_to_b',assignment_evidence='unused guess',orientation_evidence='unused guess'))
    sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    with (tmp_path/'output/audit.csv').open() as stream:
        row=next(row for row in csv.DictReader(stream) if row['eic']=='99T-SYNTHETIC')
    assert 'unused guess' not in row['endpoint_evidence']
    assert 'name lookup' in row['endpoint_evidence']


def test_assessment_preserves_evidence_for_the_already_resolved_terminal(tmp_path):
    import csv
    import shutil
    from coppersushi.data_sources.catalog_sweep import sweep
    from coppersushi.data_sources.element_catalog import load
    root=FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source=tmp_path/'input'
    (source/'backfill/ends-conflict.csv').unlink()
    with (source/'config/element-assessments.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['tso','eic','name','site_a','site_b','direct_orientation','assignment_evidence','orientation_evidence'])
        writer.writeheader()
        writer.writerow(dict(tso='TEST',eic='99T-UNKNOWN',name='Westhaven-Unknown',site_a='Westhaven',site_b='Eastfield',direct_orientation='a_to_b',assignment_evidence='reviewed guess',orientation_evidence='direction guess'))
    sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    with load(tmp_path/'output') as db:
        rows=db.execute("SELECT p.* FROM element_endpoints p JOIN elements e USING(element_id) WHERE e.eic='99T-UNKNOWN' ORDER BY p.terminal").fetchall()
        assert 'name lookup' in rows[0]['evidence']
        assert 'reviewed guess' not in rows[0]['evidence']
        assert 'reviewed guess' in rows[1]['evidence']


def test_audit_counts_unknown_orientation_as_unmapped(tmp_path):
    import csv
    import gzip
    import shutil
    from coppersushi.data_sources.catalog_sweep import sweep
    root=FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root,tmp_path/'input')
    source=tmp_path/'input'
    annual=source/'cache/research/country-caps/annual-json'
    annual.mkdir(parents=True)
    with gzip.open(annual/'activeFbConstraints-synthetic.gz','wb') as stream:
        stream.write((root/'annual.json').read_bytes())
    with (source/'config/element-assessments.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['tso','eic','name','site_a','site_b','direct_orientation','assignment_evidence','orientation_evidence'])
        writer.writeheader()
        writer.writerow(dict(tso='TEST',eic='99T-ABSENT',name='Missing pair',site_a='Westhaven',site_b='Eastfield',direct_orientation='unknown',assignment_evidence='reviewed guess',orientation_evidence='unknown direction'))
    summary=sweep(source/'cache',source/'backfill',tmp_path/'output',source/'config')
    with (tmp_path/'output/audit.csv').open() as stream:
        row=next(row for row in csv.DictReader(stream) if row['eic']=='99T-ABSENT')
    assert row['status'] == 'orientation_unknown'
    assert summary['unresolved_active_appearances'] == 2
    assert summary['fully_resolved_elements'] == 1


def test_reviewed_mapping_bootstraps_without_annual_or_domain_observation(tmp_path):
    import shutil
    from coppersushi.data_sources.catalog_sweep import sweep
    from coppersushi.data_sources.element_catalog import load
    root = FIXTURE.parent/'catalog-sweep'
    shutil.copytree(root, tmp_path/'input')
    source = tmp_path/'input'
    shutil.copyfile(root/'config/reviewed-mappings.csv', source/'config/element-assessments.csv')
    sweep(source/'cache', source/'backfill', tmp_path/'output', source/'config')
    with load(tmp_path/'output') as db:
        row = db.execute("SELECT * FROM elements WHERE eic='99T-REVIEWED'").fetchone()
        assert row['orientation_basis'] == 'inferred'
        ends = db.execute('SELECT * FROM element_endpoints WHERE element_id=?', (row['element_id'],)).fetchall()
        assert len(ends) == 2
        assert all(end['assignment_basis'] == 'inferred' and end['published_name'] is None for end in ends)
