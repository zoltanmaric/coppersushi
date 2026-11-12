import pytest

from coppersushi.frontend.packaging import preview as app
from coppersushi import REPO


@pytest.fixture(autouse=True)
def synthetic_catalog(monkeypatch):
    monkeypatch.setenv('COPPERSUSHI_ELEMENT_CATALOG', str(REPO/'coppersushi/testdata/element-catalog'))












def test_page_shell_does_not_load_the_opf_runtime(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "test-public-token")
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-c', "import sys; from coppersushi.frontend.packaging import preview as app; assert 'pypsa' not in sys.modules; assert app.server.test_client().get('/').status_code == 200"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_unsupported_cnec_dates_redirect_to_undated_view(monkeypatch):
    monkeypatch.setenv("MAPBOX_TOKEN", "test-public-token")
    client = app.server.test_client()
    response = client.get('/cnec/2025-11-04')
    assert response.status_code == 302
    assert response.headers['Location'] == '/cnec'
    assert client.get('/cnec/2025-11-05').status_code == 200
