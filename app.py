from datetime import date
from flask import redirect, request
from werkzeug.wrappers import Response
import logging
from functools import partial
import os
from pathlib import Path

import pandas as pd

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, Patch, ctx, no_update
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

from coppersushi import map_style, power_flow
from coppersushi.data_sources import opf_bundle, credentials, mapbox_styles, networks
from coppersushi.market_day import MARKET_TZ, MarketDay

# Every page's controls live in one tree that the router swaps, so a callback whose
# components belong to the other page is simply not fired.
app = Dash(
    __name__,
    title='Copper Sushi 🍣',
    assets_ignore=r'(cnec-(app|view)\.(js|css)|plotly-mapbox-.*\.js)',
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
)

server = app.server
# Local full-app navigation shares the standalone shell; production routes CNEC separately.
from cnec_server import index as standalone_cnec, local_data as standalone_data
server.add_url_rule('/cnec', 'standalone_cnec', standalone_cnec)
server.add_url_rule('/cnec/', 'standalone_cnec_slash', standalone_cnec)
server.add_url_rule('/cnec/<day>', 'standalone_cnec_day', standalone_cnec)
server.add_url_rule('/data/cnec/v2/<path:filename>', 'standalone_data', standalone_data)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


NETWORK_LOADERS = {
    'opf-2024': lambda: networks.load(networks.solved('2024-08-29')),
}
# Unsanctioned solves are viewable at /candidates/<file stem>
NETWORK_LOADERS.update({
    f'candidates/{path.stem}': partial(networks.load, path)
    for path in sorted(networks.CANDIDATES_DIR.glob('*.nc'))
})
ROOT_VIEW = os.environ.get('ROOT_VIEW', 'embed')
if ROOT_VIEW not in {'embed', 'full'}:
    raise ValueError('ROOT_VIEW must be embed or full')

from coppersushi.cnec_support import FIRST_DAY as CNEC_FIRST_DAY
CNEC_ROUTE = 'cnec'  # /cnec, or /cnec/<delivery day> to open on one day
_cache: dict[str, tuple[go.Figure, pd.Index]] = {}
_basemap: dict[str, dict] = {}


def mapbox_token() -> str:
    """From the environment (deploys) or the gitignored secrets file (README: Mapbox token)."""
    return credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token'))


def basemap() -> dict:
    """Mapbox's dark style without its labels, fetched once per process."""
    if 'dark' not in _basemap:
        _basemap['dark'] = map_style.without_labels(mapbox_styles.fetch(mapbox_token()))
    return _basemap['dark']


def figure_for(network_key: str) -> tuple[go.Figure, pd.Index]:
    if network_key not in _cache:
        n = NETWORK_LOADERS[network_key]()
        fig = power_flow.colored_network_figure(n, 'net_power', mapbox_token())
        fig.update_layout(
            mapbox=map_style.OPF_CAMERA
        )
        _cache[network_key] = (fig, n.snapshots)
    return _cache[network_key]


def network_key_from_path(pathname: str) -> str | None:
    key = (pathname or '').strip('/')
    if key in {'', 'embed/opf-2024'}:
        return 'opf-2024'
    return key if key in NETWORK_LOADERS else None


def is_embed_path(pathname: str, root_view: str = ROOT_VIEW) -> bool:
    key = (pathname or '').strip('/')
    return key == 'embed/opf-2024' or (not key and root_view == 'embed')


def navigation() -> html.Nav:
    return html.Nav([
        html.A('2024 OPF on the 2025 grid', href='/opf-2024'),
        html.A('Prices and binding CNECs', href=f'/{CNEC_ROUTE}'),
    ], className='app-navigation')


def cnec_day_from_path(pathname: str) -> str | None:
    """The delivery day a `/cnec/<day>` path opens on, or None when it names no day."""
    parts = (pathname or '').strip('/').split('/')
    return parts[1] if len(parts) > 1 and parts[0] == CNEC_ROUTE else None



def unsupported_cnec_path(pathname: str) -> bool:
    day = cnec_day_from_path(pathname)
    try:
        return day is not None and date.fromisoformat(day) < CNEC_FIRST_DAY
    except ValueError:
        return False


@server.before_request
def redirect_unsupported_cnec_day() -> Response | None:
    if request.method == 'GET' and unsupported_cnec_path(request.path):
        return redirect('/cnec')
    return None

def is_cnec_path(pathname: str) -> bool:
    return (pathname or '').strip('/').split('/')[0] == CNEC_ROUTE


def network_layout(token: str | None = None) -> html.Div:
    return html.Div([
        html.Div(id='opf-time', className='opf-time'),
        dbc.Alert(id='status', color='danger', is_open=False, style={'margin': '0 1em'}),
        dcc.Loading(
            dcc.Graph(
                id='map',
                style={'height': '100%'},
                figure=dict(
                    data=[dict(type='scattermapbox', lon=[None], lat=[None], hoverinfo='skip')],
                    layout=dict(
                        autosize=True, uirevision=True, showlegend=False, hovermode='closest',
                        mapbox=dict(style=map_style.MAP_STYLE, accesstoken=token, **map_style.OPF_CAMERA),
                        margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='#111',
                    ),
                ),
                config=dict(responsive=True, displayModeBar=False, scrollZoom=True)
            ),
            custom_spinner=html.Div('Loading network…', className='opf-loading', role='status'),
            delay_show=300,
            parent_style={'flex': '1', 'minHeight': '0', 'position': 'relative',
                          'display': 'flex', 'flexDirection': 'column'},
            overlay_style={'visibility': 'visible'},
        ),
        html.Div(
            dcc.Slider(
                0, 1, step=1, value=0,
                id='snapshot-slider', allow_direct_input=False
            ),
            className='opf-slider',
        )
    ], className='opf-view')


app.layout = html.Div([
    dcc.Location(id='url', refresh='callback-nav'),
    dcc.Store(id='active-page'),
    html.Div(id='page'),
])


def show_page(pathname: str, root_view: str = ROOT_VIEW) -> html.Div:
    if unsupported_cnec_path(pathname):
        return html.Div(dcc.Location(id='cnec-redirect', href='/cnec', refresh=True))
    if is_cnec_path(pathname):
        return html.Div(dcc.Location(href=pathname, refresh=True))
    if network_key_from_path(pathname) is None:
        return html.Div([html.H1('Page not found'), html.A('2024 OPF', href='/opf-2024')])
    return html.Div([
        *([] if is_embed_path(pathname, root_view) else [navigation()]),
        network_layout(mapbox_token()),
    ], className='app-page')


@app.callback(Output('page', 'children'), Output('active-page', 'data'),
              Input('url', 'pathname'), State('active-page', 'data'))
def route_page(pathname: str, active_page: str | None) -> tuple:
    """Dash owns page-kind transitions; React owns dates within the mounted CNEC page."""
    kind = 'cnec' if is_cnec_path(pathname) and not unsupported_cnec_path(pathname) else 'other'
    if kind == active_page == 'cnec':
        return no_update, no_update
    return show_page(pathname), kind



def render(pathname: str, snapshot_index: int, slider_moved: bool) -> tuple:
    """Figure, slider state and status banner for one view; a failed load becomes the banner."""
    network_key = network_key_from_path(pathname)
    if network_key is None:
        raise PreventUpdate
    try:
        snapshots: pd.Index | None = opf_bundle.snapshots() if network_key == 'opf-2024' else None
        if snapshots is None:
            fig, snapshots = figure_for(network_key)
            state = opf_snapshot_state(snapshots, snapshot_index, slider_moved)
            selected = power_flow.show_snapshot(fig, state[2])
        else:
            state = opf_snapshot_state(snapshots, snapshot_index, slider_moved)
            selected = opf_bundle.load(state[2], mapbox_token())
    except Exception as e:  # noqa: BLE001 — every loader failure must reach the page
        logging.exception('Loading %s failed', network_key)
        return no_update, no_update, no_update, no_update, no_update, f'Could not load {network_key}: {e}', True
    maximum, marks, snapshot_index, label = state
    # The page owns the layout; loading an hour only replaces network traces.
    update = Patch()
    update['data'] = selected.to_plotly_json()['data']
    return update, maximum, marks, snapshot_index, label, '', False


def opf_snapshot_state(snapshots: pd.Index, snapshot_index: int, slider_moved: bool) -> tuple:
    """Pure local-time labels and selection, shared by normal and embedded OPF views."""
    # PyPSA stores naive snapshots as UTC; display the operating day's named zone.
    local = pd.DatetimeIndex(snapshots)
    local = local.tz_localize('UTC') if local.tz is None else local
    local = local.tz_convert(MARKET_TZ)
    if not slider_moved or not 0 <= snapshot_index < len(snapshots):
        snapshot_index = min(enumerate(local), key=lambda item: abs(item[1].hour - 12))[0]
    marks = {
        idx: dict(label=snapshot.strftime('%H:%M')
                  if snapshot.hour % 4 == 0 or idx == len(local) - 1 else ' ')
        for idx, snapshot in enumerate(local)
    }
    label = local[snapshot_index].strftime('%d %b %Y · %H:%M %Z')
    return len(snapshots) - 1, marks, snapshot_index, label



@app.callback(
    Output('map', 'figure'),
    Output('snapshot-slider', 'max'),
    Output('snapshot-slider', 'marks'),
    Output('snapshot-slider', 'value'),
    Output('opf-time', 'children'),
    Output('status', 'children'),
    Output('status', 'is_open'),
    Input('url', 'pathname'),
    Input('snapshot-slider', 'value'))
def update_figure(pathname: str, snapshot_index: int) -> tuple:
    return render(pathname, snapshot_index, ctx.triggered_id == 'snapshot-slider')


# Only the scheduled producer deployment exposes this non-HTTP-event handler.
if os.environ.get('COPPERSUSHI_BUNDLE_PRODUCER') == 'true':
    @server.post('/events')
    def prepare_published_days() -> tuple[dict[str, list[str]], int]:
        from datetime import datetime, timedelta
        from coppersushi.market_day import MARKET_TZ
        from coppersushi.data_sources import cnec_bundles
        today = datetime.now(MARKET_TZ).date()
        bucket = os.environ['COPPERSUSHI_CACHE_BUCKET']
        results = []
        for offset in (0, 1):
            day = MarketDay.on(today + timedelta(days=offset))
            try:
                if cnec_bundles.is_published(day, bucket):
                    results.append(str(day.date) + ':already-published')
                    continue
                generation = cnec_bundles.publish(cnec_bundles.prepare(day, refresh=True), bucket)
                results.append(str(day.date) + ':' + generation)
            except Exception:
                logging.getLogger(__name__).exception('Day publication not ready: %s', day.date)
        return {'published': results}, 200 if results else 503


if __name__ == '__main__':
    from coppersushi.data_sources.runtime_data import check
    check()
    app.run(debug=True)
