"""Local CNEC preview server; production serves the same shell and files from S3."""
from datetime import date
from pathlib import Path
from flask import Blueprint, Flask, Response, request, send_from_directory
from coppersushi.data_sources import credentials

from coppersushi.cnec_support import FIRST_DAY
from frontend.publish import render_shell
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

@routes.get('/data/cnec/v2/<path:filename>')
def local_data(filename: str) -> Response:
    return send_from_directory(Path(__file__).parent / 'data/browser/data/cnec/v2',filename)


server = Flask(__name__, static_folder='assets', static_url_path='/assets')
server.register_blueprint(routes)
