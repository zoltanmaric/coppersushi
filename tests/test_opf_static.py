import gzip
import json
from unittest.mock import Mock

import pytest

from coppersushi.opf.data_sources.publication import publish
from frontend.publish import render_shell


def bundle(directory):
    directory.mkdir()
    (directory / 'snapshots.json').write_text(json.dumps(['2024-08-29T10:00:00+00:00']))
    (directory / '0.json.gz').write_bytes(gzip.compress(json.dumps({'data': [], 'layout': {'mapbox': {}}}).encode()))


def test_hours_are_immutable_and_published_before_manifest(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    bundle(source)
    client = Mock()
    monkeypatch.setattr('coppersushi.opf.data_sources.publication.cache._client', lambda: client)
    publish(source, bucket='test', output=None)
    calls = [c.kwargs for c in client.put_object.call_args_list]
    manifest = json.loads(gzip.decompress(calls[-1]['Body']))
    assert calls[0]['Key'].endswith(f"{manifest['generation']}/0.json")
    assert calls[-1]['Key'].endswith('/manifest.json')
    assert calls[0]['ContentEncoding'] == 'gzip'
    assert 'immutable' in calls[0]['CacheControl']


def test_invalid_hour_cannot_publish_a_manifest(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    bundle(source)
    (source / '0.json.gz').write_bytes(gzip.compress(b'{"data": []}'))
    client = Mock()
    monkeypatch.setattr('coppersushi.opf.data_sources.publication.cache._client', lambda: client)
    with pytest.raises(ValueError, match='Invalid OPF figure'):
        publish(source, bucket='test', output=None)
    client.put_object.assert_not_called()


def test_standalone_opf_routes_need_no_dash(monkeypatch):
    from cnec_server import server
    monkeypatch.setenv('MAPBOX_TOKEN', 'test-token')
    for path, embed in [('/opf-2024', False), ('/embed/opf-2024', True)]:
        page = server.test_client().get(path).get_data(as_text=True)
        assert page == render_shell('test-token', embed=embed, view='opf')
        assert '/assets/opf-app.js' in page
        assert '_dash' not in page
