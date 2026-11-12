"""Catalog decisions and newly published identities share the runtime path."""
import shutil
import pandas as pd
from coppersushi import REPO
from coppersushi.pipelines.grid.data_sources import element_catalog
from coppersushi.pipelines.cnec.data_sources import jao
from coppersushi.pipelines.grid.data_sources import osm_locator

FIXTURE = REPO/'coppersushi/testdata/element-catalog'


def test_runtime_discovers_absent_and_missing_publications_without_replacing_reviewed_rows(monkeypatch):
    required = pd.read_csv(FIXTURE/'required.csv')
    seen = []
    def fetch(interval, missing):
        seen.extend(missing.name)
        return pd.read_csv(FIXTURE/'discovered-ends.csv')
    monkeypatch.setattr(jao, 'load_element_ends', fetch)
    monkeypatch.setattr(osm_locator, 'read_csvs', lambda: pd.read_csv(FIXTURE/'sites.csv').rename(
        columns={'display_name':'name','longitude':'x','latitude':'y'}))
    monkeypatch.setattr(osm_locator, 'load_aliases', lambda: {})
    monkeypatch.setattr(osm_locator, 'load_element_aliases', lambda: {})
    result = element_catalog.resolve(pd.Timestamp('2026-01-01',tz='UTC'),required,FIXTURE).set_index('name')
    assert seen == ['Westhaven-Unknown', 'New publication']
    assert len(result) == 3 and result.match_status.eq('matched').all()
    assert result.loc['Westhaven-Eastfield'].bus_source == 'element-catalog'
    assert (result.loc['New publication'].x0,result.loc['New publication'].x1) == (4.,3.)


def test_runtime_does_not_bypass_a_recorded_unresolved_site(tmp_path, monkeypatch):
    shutil.copytree(FIXTURE,tmp_path,dirs_exist_ok=True)
    shutil.copyfile(FIXTURE/'unresolved-endpoints.csv',tmp_path/'element_endpoints.csv')
    required = pd.read_csv(FIXTURE/'required.csv').iloc[:2]
    def forbidden(*args):
        raise AssertionError('reviewed decisions must not trigger a fetch')
    monkeypatch.setattr(jao,'load_element_ends',forbidden)
    result=element_catalog.resolve(pd.Timestamp('2026-01-01',tz='UTC'),required,tmp_path).set_index('name')
    assert result.loc['Westhaven-Unknown'].match_status == 'no_substation'


def test_locator_failure_keeps_catalog_geometry(monkeypatch):
    required = pd.read_csv(FIXTURE/'required.csv')
    monkeypatch.setattr(jao, 'load_element_ends', lambda *_: pd.read_csv(FIXTURE/'discovered-ends.csv'))
    def unavailable():
        raise OSError('locator unavailable')
    monkeypatch.setattr(osm_locator, 'read_csvs', unavailable)
    result = element_catalog.resolve(pd.Timestamp('2026-01-01',tz='UTC'),required,FIXTURE).set_index('name')
    assert result.loc['Westhaven-Eastfield'].match_status == 'matched'
    assert result.loc['Westhaven-Unknown'].match_status == 'no_substation'
