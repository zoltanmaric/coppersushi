"""Local CNEC preview server; production serves the same shell and files from S3."""
from datetime import date
from pathlib import Path
from flask import Flask, Response, send_from_directory
from coppersushi.data_sources import credentials

from coppersushi.cnec_support import FIRST_DAY
from frontend.publish import render_shell
server = Flask(__name__, static_folder='assets', static_url_path='/assets')

@server.get('/')
def health() -> str:
    return 'Copper Sushi CNEC'

@server.get('/cnec')
@server.get('/cnec/')
@server.get('/cnec/<day>')
def index(day: str | None = None) -> str | Response:
    if day is not None:
        try:
            if date.fromisoformat(day) < FIRST_DAY:
                return Response(status=302, headers={'Location':'/cnec'})
        except ValueError:
            pass
    return render_shell(credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token')))

@server.get('/data/cnec/v2/<path:filename>')
def local_data(filename: str) -> Response:
    return send_from_directory(Path(__file__).parent / 'data/browser/data/cnec/v2',filename)
