"""Lightweight CNEC web handler; OPF remains in the separate Dash application."""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Flask, Response, render_template_string, request, redirect
from coppersushi.data_sources import credentials

FIRST_DAY = '2025-11-05'
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
            if date.fromisoformat(day) < date.fromisoformat(FIRST_DAY):
                return redirect('/cnec')
        except ValueError:
            pass
    config = {'default_day': datetime.now(ZoneInfo('Europe/Brussels')).date().isoformat(),
              'min_day': FIRST_DAY,
              'token': credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token'))}
    return render_template_string('''<!doctype html><html lang="en"><head>
      <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Copper Sushi 🍣</title><link rel="stylesheet" href="/assets/cnec-app.css">
      <style>body{margin:0;background:#222;color:#eee;font-family:Arial,sans-serif}nav{padding:10px 16px;display:flex;gap:24px}a{color:#00bc8c}.cnec-map-container{height:calc(100dvh - 40px)}</style>
      </head><body><nav><a href="/opf-2024">2024 OPF on the 2025 grid</a><a href="/cnec">Prices and binding CNECs</a></nav>
      <main id="cnec-root"></main><script id="cnec-config" type="application/json">{{config|tojson}}</script>
      <script src="/assets/plotly-mapbox-3.7.0.min.js"></script><script src="/assets/cnec-app.js"></script></body></html>''', config=config)

@server.get('/data/cnec/v1/<day>/manifest.json')
def unpublished(day: str) -> Response:
    # Production intercepts this prefix at CloudFront's private S3 origin.
    return Response(status=404)

@server.get('/api/cnec/bundle/<day>')
def bundle(day: str) -> Response | tuple[Response, int]:
    # Preparation dependencies load only for dates absent from published S3 data.
    from coppersushi.data_sources import cnec_bundles
    from coppersushi.market_day import MarketDay
    try:
        if date.fromisoformat(day) < date.fromisoformat(FIRST_DAY):
            raise ValueError('Delivery day precedes supported publication history')
        delivery = MarketDay.on(day)
        value = request.args.get('interval')
        indices = None if value is None else [int(value)]
        if indices is not None and any(i < 0 or i >= len(delivery.market_time_units()) for i in indices):
            raise ValueError('Interval is outside the selected market day')
    except ValueError as error:
        return Response(json.dumps({'error': str(error)}), status=400, mimetype='application/json')
    try:
        result = cnec_bundles.prepare(delivery, indices)
    except Exception as error:
        server.logger.exception('Day preparation failed: %s', day)
        return Response(json.dumps({'error': str(error)}), status=503, mimetype='application/json')
    return Response(result.model_dump_json(), mimetype='application/json', headers={'Cache-Control': 'no-store'})
