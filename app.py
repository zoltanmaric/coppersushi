import logging
from functools import partial
from pathlib import Path

import pandas as pd

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, Patch, ctx, no_update
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from flask import Flask
from cnec_server import routes as cnec_routes, opf_routes

from coppersushi import map_style
from coppersushi.opf import power_flow
from coppersushi.data_sources import credentials
from coppersushi.opf.data_sources import networks
from coppersushi.market_day import MARKET_TZ

# Register static map routes before Dash’s fallback routes.
server = Flask(__name__, static_folder='frontend/dist/assets', static_url_path='/assets')
server.register_blueprint(cnec_routes)
server.register_blueprint(opf_routes)

app = Dash(
    __name__,
    server=False,
    title='Copper Sushi 🍣',
    assets_folder='frontend/assets',
    assets_url_path='candidate-assets',
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
)

app.init_app(server)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


NETWORK_LOADERS = {}
# Unsanctioned solves are viewable at /candidates/<file stem>
NETWORK_LOADERS.update({
    f'candidates/{path.stem}': partial(networks.load, path)
    for path in sorted(networks.CANDIDATES_DIR.glob('*.nc'))
})
_cache: dict[str, tuple[go.Figure, pd.Index]] = {}


def mapbox_token() -> str:
    """From the environment (deploys) or the gitignored secrets file (README: Mapbox token)."""
    return credentials.token('MAPBOX_TOKEN', Path('.secrets/.mapbox_token'))


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
    return key if key in NETWORK_LOADERS else None


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
    html.Div(id='page'),
], className='app-root')


def show_page(pathname: str) -> html.Div:
    if network_key_from_path(pathname) is None:
        return html.Div([html.H1('Page not found'), html.A('2024 OPF', href='/opf-2024')])
    return html.Div([
        network_layout(mapbox_token()),
    ], className='app-page')


@app.callback(Output('page', 'children'), Input('url', 'pathname'))
def route_page(pathname: str) -> html.Div:
    return show_page(pathname)


def render(pathname: str, snapshot_index: int, slider_moved: bool) -> tuple:
    """Figure, slider state and status banner for one view; a failed load becomes the banner."""
    network_key = network_key_from_path(pathname)
    if network_key is None:
        raise PreventUpdate
    try:
        fig, snapshots = figure_for(network_key)
        state = opf_snapshot_state(snapshots, snapshot_index, slider_moved)
        selected = power_flow.show_snapshot(fig, state[2])
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


if __name__ == '__main__':
    from coppersushi.data_sources.runtime_data import check
    check()
    app.run(debug=True)
