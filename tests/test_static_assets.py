"""Check exported resources against Dash's own HTTP routes, including lazy chunks."""
import importlib
from html.parser import HTMLParser

from dash import Dash, dcc, html

static_assets = importlib.import_module('infra.lambda.static_assets')


def test_export_contains_fingerprinted_scripts_lazy_chunks_and_assets(tmp_path):
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'site.css').write_text('body { color: teal; }')
    app = Dash(__name__, assets_folder=str(assets))
    app.layout = html.Div(dcc.Graph())
    output = tmp_path / 'export'
    static_assets.export(app, output)
    client = app.server.test_client()
    html_response = client.get('/').data.decode()

    class Scripts(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == 'script':
                src = dict(attrs).get('src', '')
                if src.startswith('/_dash-component-suites/'):
                    assert (output / src.lstrip('/')).read_bytes() == client.get(src).data

    Scripts().feed(html_response)
    assert (output / 'assets/site.css').read_text() == 'body { color: teal; }'
    lazy = output / '_dash-component-suites/dash/dcc/async-graph.js'
    assert lazy.read_bytes() == client.get('/_dash-component-suites/dash/dcc/async-graph.js').data
    assert (output / '_dash-component-suites/plotly/package_data/plotly.min.js').is_file()
    assert not list(output.rglob('*.py'))
