"""Publication must consume the build output, never the source asset folder."""
from unittest.mock import Mock

from coppersushi import REPO
from frontend.packaging import publish


def test_publication_uses_built_assets_and_emits_configured_shells(tmp_path, monkeypatch):
    assets = tmp_path / 'frontend/dist/assets'
    assets.mkdir(parents=True)
    for path in (REPO / 'frontend/dist/assets').iterdir():
        if path.is_file():
            (assets / path.name).write_bytes(b'built artifact')
    source = tmp_path / 'frontend/assets'
    source.mkdir(parents=True)
    (source / 'unbuilt.txt').write_text('not part of this release')
    client = Mock()
    monkeypatch.setattr(publish, 'REPO', tmp_path)
    monkeypatch.setattr(publish.cache, '_client', lambda: client)
    monkeypatch.setattr(publish.credentials, 'token', lambda *_: 'test-public-token')
    publish.publish('bucket')
    keys = [call.kwargs['Key'] for call in client.put_object.call_args_list]
    assert not any(key.endswith('unbuilt.txt') for key in keys)
    assert keys[-4:] == [f'data/cnec/v1/ui/{name}' for name in ['index.html', 'embed.html', 'opf.html', 'opf-embed.html']]
    assert all('/assets/' in key for key in keys[:-4])
    for name in ['index.html', 'embed.html', 'opf.html', 'opf-embed.html']:
        assert 'test-public-token' in (tmp_path / 'frontend/dist' / name).read_text()


def test_candidate_styles_are_separate_from_built_browser_assets():
    import app
    client = app.server.test_client()
    assert client.get('/assets/cnec-app.js').status_code == 200
    assert client.get('/candidate-assets/opf.css').status_code == 200
