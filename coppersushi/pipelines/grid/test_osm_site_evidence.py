"""OSM evidence is reused only when complete; downloads replace caches atomically."""
import io
import shutil

import pytest

from coppersushi import REPO
from coppersushi.pipelines.grid.data_sources import catalog_backfill

SUPPLEMENT = (REPO / 'coppersushi/pipelines/grid/testdata/catalog-sweep/supplement')


@pytest.fixture
def evidence_cache(tmp_path, monkeypatch):
    config = tmp_path/'config/element-catalog'
    config.mkdir(parents=True)
    shutil.copyfile(SUPPLEMENT/'osm-sites.csv', config/'osm-sites.csv')
    monkeypatch.setattr(catalog_backfill, 'PRODUCT', tmp_path)
    output = tmp_path/'evidence'
    output.mkdir()
    return output


@pytest.mark.parametrize('invalid', ['truncated.json', 'incomplete-osm.json'])
def test_invalid_cached_evidence_is_fetched_again(evidence_cache, monkeypatch, invalid):
    path = evidence_cache/'osm-way-424242.json'
    shutil.copyfile((REPO / 'coppersushi/pipelines/data_sources/testdata/runtime-data')/invalid, path)
    calls = []
    valid = (SUPPLEMENT/'osm-way-424242.json').read_bytes()
    def download(*args, **kwargs):
        calls.append(args[0])
        return io.BytesIO(valid)
    monkeypatch.setattr(catalog_backfill.urllib.request, 'urlopen', download)
    catalog_backfill.fetch_site_evidence(evidence_cache)
    assert len(calls) == 1
    from coppersushi.pipelines.grid.data_sources.catalog_sweep import substation_centroid
    import json
    assert substation_centroid(json.loads(path.read_text()), 'way', 424242).x == 5.1
    catalog_backfill.fetch_site_evidence(evidence_cache)
    assert len(calls) == 1


def test_refresh_fetches_valid_evidence(evidence_cache, monkeypatch):
    path = evidence_cache/'osm-way-424242.json'
    shutil.copyfile(SUPPLEMENT/'osm-way-424242.json', path)
    calls = []
    def download(*args, **kwargs):
        calls.append(args[0])
        return (SUPPLEMENT/'osm-way-424242.json').open('rb')
    monkeypatch.setattr(catalog_backfill.urllib.request, 'urlopen', download)
    catalog_backfill.fetch_site_evidence(evidence_cache, refresh=True)
    assert len(calls) == 1


def test_invalid_download_cannot_replace_valid_evidence(evidence_cache, monkeypatch):
    path = evidence_cache/'osm-way-424242.json'
    shutil.copyfile(SUPPLEMENT/'osm-way-424242.json', path)
    before = path.read_bytes()
    monkeypatch.setattr(catalog_backfill.urllib.request, 'urlopen',
                        lambda *args, **kwargs: ((REPO / 'coppersushi/pipelines/data_sources/testdata/runtime-data/incomplete-osm.json')).open('rb'))
    with pytest.raises(ValueError, match='complete closed'):
        catalog_backfill.fetch_site_evidence(evidence_cache, refresh=True)
    assert path.read_bytes() == before
