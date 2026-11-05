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
