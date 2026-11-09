"""The standalone shell preserves routing without initializing the analysis stack."""
import subprocess
import sys
import pytest
from cnec_server import server

def test_shell_import_does_not_initialize_dash_or_pandas():
    subprocess.run([sys.executable, '-c',
        "import sys, cnec_server; assert not {'dash','pandas','plotly'} & sys.modules.keys()"], check=True)

def test_dates_before_publication_history_redirect_without_credentials():
    response = server.test_client().get('/cnec/2025-11-04')
    assert response.status_code == 302
    assert response.headers['Location'] == '/cnec'

def test_unprepared_local_manifest_is_an_explicit_miss():
    response = server.test_client().get('/data/cnec/v2/2099-01-01/manifest.json')
    assert response.status_code == 404

def test_opf_does_not_auto_execute_the_standalone_frontend():
    import app
    page = app.server.test_client().get('/opf-2024').get_data(as_text=True)
    assert 'cnec-app.js' not in page
    assert 'plotly-mapbox-3.7.0.min.js' not in page

def test_static_shell_needs_no_server_and_safely_embeds_configuration():
    import json
    from frontend.publish import render_shell
    token = '</script><script>unsafe</script>'
    html = render_shell(token)
    assert token not in html
    config = html.split('type="application/json">', 1)[1].split('</script>', 1)[0]
    assert json.loads(config) == {'min_day': '2025-11-05', 'token': token}
    subprocess.run([sys.executable, '-c',
        "import sys; from frontend.publish import render_shell; render_shell('test'); "
        "assert not {'flask','dash','pandas','plotly'} & sys.modules.keys()"], check=True)


@pytest.mark.parametrize('path,embed', [
    ('/', False), ('/cnec', False), ('/cnec/2025-11-05', False),
    ('/embed/cnec', True), ('/embed/cnec/2025-11-05', True),
])
def test_home_and_embed_share_the_shell_with_explicit_header_mode(path, embed, monkeypatch):
    monkeypatch.setenv('MAPBOX_TOKEN', 'test-public-token')
    import app
    for app_server in (server, app.server):
        response = app_server.test_client().get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert f'data-embed="{str(embed).lower()}"' in html
        assert '/assets/cnec-app.js' in html
        navigation = html.split('<nav>', 1)[1].split('</nav>', 1)[0]
        assert navigation.index('Critical Elements') < navigation.index('Power Flow')


def test_unsupported_embed_date_stays_in_the_embed():
    response = server.test_client().get('/embed/cnec/2025-11-04')
    assert response.status_code == 302
    assert response.headers['Location'] == '/embed/cnec'
