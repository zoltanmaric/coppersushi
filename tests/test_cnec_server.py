"""The standalone shell preserves routing without initializing the analysis stack."""
import subprocess
import sys
from cnec_server import server

def test_shell_import_does_not_initialize_dash_or_pandas():
    subprocess.run([sys.executable, '-c',
        "import sys, cnec_server; assert not {'dash','pandas','plotly'} & sys.modules.keys()"], check=True)

def test_dates_before_publication_history_redirect_without_credentials():
    response = server.test_client().get('/cnec/2025-11-04')
    assert response.status_code == 302
    assert response.headers['Location'] == '/cnec'

def test_unprepared_local_manifest_is_an_explicit_miss():
    response = server.test_client().get('/data/cnec/v1/2026-11-03/manifest.json')
    assert response.status_code == 404

def test_opf_does_not_auto_execute_the_standalone_frontend():
    import app
    page = app.server.test_client().get('/opf-2024').get_data(as_text=True)
    assert 'cnec-app.js' not in page
    assert 'plotly-mapbox-3.7.0.min.js' not in page
