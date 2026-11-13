"""Static readiness fails before serving; preparation reuses downloaded inputs."""
import hashlib
import shutil

import pandas as pd
import pytest

from coppersushi import REPO
from coppersushi.pipelines.market_day import MarketDay
from coppersushi.pipelines.data_sources import runtime_data
from coppersushi.pipelines.grid.data_sources import element_catalog
from coppersushi.pipelines.cnec.data_sources import jao
from coppersushi.pipelines.grid.data_sources import osm_locator
from coppersushi.pipelines.grid.data_sources import zone_shapes

GRID = REPO / 'coppersushi/pipelines/grid/testdata'
CNEC = REPO / 'coppersushi/pipelines/cnec/testdata'
FIXTURES = REPO / 'coppersushi/pipelines/data_sources/testdata'


def test_missing_catalog_has_actionable_setup_command(tmp_path, monkeypatch):
    monkeypatch.setenv('COPPERSUSHI_ELEMENT_CATALOG', str(tmp_path/'absent'))
    monkeypatch.setattr(jao, 'read_element_ends', lambda: pd.read_csv(GRID / 'element-catalog/discovered-ends.csv'))
    monkeypatch.setattr(osm_locator, 'read_csvs', lambda: pd.read_csv(CNEC / 'cnec-price-map/located-substations.csv'))
    with pytest.raises(RuntimeError, match='pixi run --locked setup-app'):
        runtime_data.check()


def test_empty_required_table_is_not_ready(tmp_path, monkeypatch):
    shutil.copytree(GRID / 'element-catalog', tmp_path/'catalog')
    monkeypatch.setenv('COPPERSUSHI_ELEMENT_CATALOG', str(tmp_path/'catalog'))
    # An empty catalog is relationally valid, but cannot serve an application.
    for table in element_catalog.TABLES:
        path = tmp_path/'catalog'/f'{table}.csv'
        path.write_text(path.read_text().splitlines()[0]+'\n')
    monkeypatch.setattr(jao, 'read_element_ends', lambda: pd.read_csv(GRID / 'element-catalog/discovered-ends.csv'))
    monkeypatch.setattr(osm_locator, 'read_csvs', lambda: pd.read_csv(CNEC / 'cnec-price-map/located-substations.csv'))
    with pytest.raises(RuntimeError, match='table sites is empty'):
        runtime_data.check()


def test_preparation_compiles_fresh_checkout_and_reuses_downloads(tmp_path, monkeypatch):
    root = GRID / 'catalog-sweep'
    monkeypatch.setattr(osm_locator, 'EXPECTED_TEMPLATES', frozenset({'AT'}))
    monkeypatch.setattr(runtime_data, 'PRODUCT', tmp_path)
    monkeypatch.delenv('COPPERSUSHI_ELEMENT_CATALOG', raising=False)
    monkeypatch.setattr(osm_locator, 'CACHE_DIR', tmp_path/'data/osm-locator')
    monkeypatch.setattr(jao, 'JAO_DIR', tmp_path/'data/jao')
    monkeypatch.setattr(zone_shapes, 'BUNDLE', tmp_path/'data/zones.geojson')
    calls = []

    def fetch_locator():
        calls.append('locator')
        shutil.copytree(root/'cache/osm-locator', osm_locator.CACHE_DIR, dirs_exist_ok=True)
    monkeypatch.setattr(osm_locator, 'fetch', fetch_locator)
    original_read = osm_locator.read_csvs
    monkeypatch.setattr(osm_locator, 'read_csvs', lambda directory=None: original_read(directory or osm_locator.CACHE_DIR))

    buses = root/'cache/osm-prebuilt-v0.7/buses.csv'
    monkeypatch.setattr(runtime_data, 'BUSES_SHA256', hashlib.sha256(buses.read_bytes()).hexdigest())
    def download(*args, **kwargs):
        calls.append('buses')
        return buses.open('rb')
    monkeypatch.setattr(runtime_data.urllib.request, 'urlopen', download)

    from coppersushi.pipelines.cnec.test_jao import written
    def fetch_domain(day):
        calls.append('domain')
        written(jao.day_dir(day))
    monkeypatch.setattr(jao, 'fetch_day', fetch_domain)
    original_seed = jao.seed_element_ends
    def seed(days):
        calls.append('seed')
        original_seed(days)
    monkeypatch.setattr(jao, 'seed_element_ends', seed)
    monkeypatch.setattr(runtime_data.catalog_backfill, 'fetch_site_evidence', lambda path, **kwargs: path.mkdir(parents=True, exist_ok=True))
    original_sweep = runtime_data.catalog_sweep.sweep
    def compile_catalog(cache, backfill, output):
        calls.append('compile')
        return original_sweep(cache, backfill, output, root/'config')
    monkeypatch.setattr(runtime_data.catalog_sweep, 'sweep', compile_catalog)
    def outlines():
        calls.append('outlines')
        shutil.copyfile(FIXTURES / 'runtime-data/zones.geojson', zone_shapes.BUNDLE)
    monkeypatch.setattr(zone_shapes, 'build', outlines)
    monkeypatch.setattr(zone_shapes, 'load', lambda: zone_shapes.read(zone_shapes.BUNDLE))
    monkeypatch.setattr(runtime_data.networks, 'solved', lambda day: buses)
    runtime_data.prepare(MarketDay.on('2026-01-01'))
    assert calls == ['locator', 'buses', 'domain', 'seed', 'compile', 'outlines']
    with element_catalog.load(tmp_path/'data/element-catalog') as db:
        assert db.execute('SELECT count(*) FROM elements').fetchone()[0] > 0
    calls.clear()
    runtime_data.prepare(MarketDay.on('2026-01-01'))
    assert calls == ['compile']
    runtime_data.check()

    # Partial setup is repaired, rather than accepted because one file exists.
    (jao.day_dir('2026-01-01')/'element-ends.csv').unlink()
    (jao.JAO_DIR/'element-ends.csv').unlink()
    zone_shapes.BUNDLE.write_text('{}')
    calls.clear()
    runtime_data.prepare(MarketDay.on('2026-01-01'))
    assert calls == ['domain', 'seed', 'compile', 'outlines']

    shutil.copyfile(FIXTURES / 'runtime-data/missing-hour.csv', jao.day_dir('2026-01-01')/'elements.csv')
    calls.clear()
    runtime_data.prepare(MarketDay.on('2026-01-01'))
    assert calls == ['domain', 'compile']


def test_truncated_catalog_reports_setup_command(tmp_path, monkeypatch):
    shutil.copytree(GRID / 'element-catalog', tmp_path/'catalog')
    shutil.copyfile(FIXTURES / 'runtime-data/truncated.csv', tmp_path/'catalog/site_names.csv')
    monkeypatch.setenv('COPPERSUSHI_ELEMENT_CATALOG', str(tmp_path/'catalog'))
    monkeypatch.setattr(jao, 'read_element_ends', lambda: pd.read_csv(GRID / 'element-catalog/discovered-ends.csv'))
    monkeypatch.setattr(osm_locator, 'read_csvs', lambda: pd.read_csv(CNEC / 'cnec-price-map/located-substations.csv'))
    with pytest.raises(RuntimeError, match='pixi run --locked setup-app'):
        runtime_data.check()
