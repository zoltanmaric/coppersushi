"""Local static-view preview; production serves the same shells and files from S3."""
from coppersushi import REPO
from datetime import date
from gzip import decompress
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen
from flask import Blueprint, Flask, Response, current_app, request, send_from_directory
from coppersushi.pipelines.data_sources import credentials

from coppersushi.pipelines.cnec.support import FIRST_DAY
from coppersushi.frontend.packaging.shell import render_shell
routes = Blueprint('cnec', __name__)

@routes.get('/')
@routes.get('/embed/cnec')
@routes.get('/embed/cnec/')
@routes.get('/embed/cnec/<day>')
@routes.get('/cnec')
@routes.get('/cnec/')
@routes.get('/cnec/<day>')
def index(day: str | None = None) -> str | Response:
    embed = request.path.startswith('/embed/')
    if day is not None:
        try:
            if date.fromisoformat(day) < FIRST_DAY:
                return Response(status=302, headers={'Location':'/embed/cnec' if embed else '/cnec'})
        except ValueError:
            pass
    return render_shell(credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token')), embed=embed)

def production_file(path: str) -> Response:
    url = 'https://coppersushi.121gigawatts.org/data/' + quote(path, safe='/')
    # Full-day prefetch can encounter transient connection resets at the edge.
    for attempt in range(3):
        try:
            with urlopen(url, timeout=20) as response:
                body = response.read()
                if response.headers.get('Content-Encoding') == 'gzip':
                    body = decompress(body)
                return Response(body, content_type='application/json')
        except HTTPError as error:
            if error.code not in (502, 503, 504) or attempt == 2:
                return Response(status=error.code)
        except (URLError, OSError, HTTPException):
            if attempt == 2:
                return Response('Production data is unavailable', status=502)

    return Response('Production data is unavailable', status=502)

@routes.get('/data/cnec/v3/<path:filename>')
def local_data(filename: str) -> Response:
    if current_app.config.get('PRODUCTION_DATA', False):
        return production_file('cnec/v3/' + filename)
    return send_from_directory(REPO / 'coppersushi/data/browser/data/cnec/v3',filename)


opf_routes = Blueprint('opf_static', __name__)


@opf_routes.get('/opf-2024')
@opf_routes.get('/embed/opf-2024')
def opf_index() -> str:
    return render_shell(credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token')),
                        embed=request.path.startswith('/embed/'), view='opf')


@opf_routes.get('/data/opf/v2/opf-2024/<path:filename>')
def opf_data(filename: str) -> Response:
    directory = current_app.config.get('OPF_PREVIEW_DIRECTORY')
    if directory is not None:
        return send_from_directory(directory, filename)
    if current_app.config.get('PRODUCTION_DATA', False):
        return production_file('opf/v2/opf-2024/' + filename)
    return send_from_directory(REPO / 'coppersushi/data/browser/data/opf/v2/opf-2024', filename)


def create_app(*, production_data: bool) -> Flask:
    """Preview local frontend assets against disk files or public production data."""
    app = Flask(__name__, static_folder=str(REPO / 'coppersushi/frontend/dist/assets'), static_url_path='/assets')
    app.config['PRODUCTION_DATA'] = production_data
    app.register_blueprint(routes)
    app.register_blueprint(opf_routes)
    return app


server = create_app(production_data=False)

if __name__ == '__main__':
    create_app(production_data=True).run(host='127.0.0.1', port=8050)
