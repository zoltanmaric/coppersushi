"""Lightweight CNEC web handler; OPF remains in the separate Dash application."""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Flask, Response, render_template_string, request, redirect, send_from_directory
from coppersushi.data_sources import credentials

from coppersushi.cnec_support import FIRST_DAY
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
    config = {'default_day': datetime.now(ZoneInfo('Europe/Brussels')).date().isoformat(),
              'min_day': FIRST_DAY.isoformat(),
              'token': credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token'))}
    return render_template_string('''<!doctype html><html lang="en"><head>
      <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Copper Sushi 🍣</title><link rel="icon" href="/assets/favicon.ico"><link rel="stylesheet" href="/assets/cnec-app.css">
      <style>body{margin:0;background:#222;color:#eee;font-family:Arial,sans-serif}nav{padding:10px 16px;display:flex;gap:24px}a{color:#00bc8c}.cnec-map-container{height:calc(100dvh - 40px)}</style>
      </head><body><nav><a href="/opf-2024">2024 OPF on the 2025 grid</a><a href="/cnec">Prices and binding CNECs</a></nav>
      <main id="cnec-root"></main><script id="cnec-config" type="application/json">{{config|tojson}}</script>
      <script src="/assets/plotly-mapbox-3.7.0.min.js"></script><script src="/assets/cnec-app.js"></script></body></html>''', config=config)

@server.get('/data/cnec/v2/<path:filename>')
def local_data(filename: str) -> Response:
    return send_from_directory(Path(__file__).parent / 'data/browser/data/cnec/v2',filename)
