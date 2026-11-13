"""Exercise the deployed edge function, including private-path rejection."""
import json
from pathlib import Path
import subprocess

import pytest

SOURCE = Path('coppersushi/infra/lambda/hostname.tf').read_text().split('code    = <<-JS\n')[1].split('\n  JS')[0]


@pytest.mark.parametrize('path,filename', [
    ('/', 'index.html'), ('/cnec/2026-11-10', 'index.html'),
    ('/embed/cnec/2026-11-10', 'embed.html'), ('/opf-2024', 'opf.html'),
    ('/embed/opf-2024/', 'opf-embed.html'), ('/assets/opf-app.js', 'assets/opf-app.js'),
])
def test_static_shell_routes(path, filename):
    event = json.dumps({'request': {'uri': path}})
    result = subprocess.check_output(['node', '-e', SOURCE + f'\nconsole.log(JSON.stringify(handler({event})));'], text=True)
    assert json.loads(result)['uri'] == f'/data/cnec/v1/ui/{filename}'


@pytest.mark.parametrize('path', ['/cache/v1/private', '/ui-rollback/release/index.html', '/_dash-update-component', '/missing', '/candidates/private'])
def test_unknown_routes_cannot_reach_private_s3_objects(path):
    event = json.dumps({'request': {'uri': path}})
    result = subprocess.check_output(['node', '-e', SOURCE + f'\nconsole.log(JSON.stringify(handler({event})));'], text=True)
    assert json.loads(result)['statusCode'] == 404
