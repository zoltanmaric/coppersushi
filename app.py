import logging
from pathlib import Path

import pandas as pd

import scripts.plot_power_flow as ppf
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, ctx
import dash_bootstrap_components as dbc

from pipeline import flows, grid
from pipeline.sources import networks, osm, pypsa_eur

app = Dash(__name__, title='Copper Sushi 🍣', external_stylesheets=[dbc.themes.DARKLY])

server = app.server

NETWORK_LOADERS = {
    'v1': lambda: networks.load(Path('networks/elec_s_all_ec_lv1.01_2H.nc')),
    'osm': lambda: flows.zero_placeholder(grid.build_network(osm.load_tables(osm.download()))),
    'opf-2013': lambda: networks.load(pypsa_eur.solved_network('2013-07-17')),
}
# Unsanctioned solves are viewable at /candidates/<file stem>
NETWORK_LOADERS.update({
    f'candidates/{path.stem}': (lambda path=path: networks.load(path))
    for path in sorted(pypsa_eur.CANDIDATES_DIR.glob('*.nc'))
})
_cache: dict[str, tuple[go.Figure, pd.Index]] = {}


def figure_for(network_key: str) -> tuple[go.Figure, pd.Index]:
    if network_key not in _cache:
        n = NETWORK_LOADERS[network_key]()
        fig = ppf.colored_network_figure(n, 'net_power')
        fig.update_layout(
            mapbox=dict(center=go.layout.mapbox.Center(lat=53, lon=9), zoom=3.9, pitch=60)
        )
        _cache[network_key] = (fig, n.snapshots)
    return _cache[network_key]


def network_key_from_path(pathname: str) -> str:
    key = (pathname or '').strip('/')
    return key if key in NETWORK_LOADERS else 'v1'


app.layout = html.Div([
    dcc.Location(id='url'),
    html.Div(
        [
            dcc.Link('2013 model (v1)', href='/', style={'marginRight': '1em'}),
            dcc.Link('2025 OSM grid', href='/osm', style={'marginRight': '1em'}),
            dcc.Link('2013 OPF on the 2025 grid', href='/opf-2013'),
        ],
        style={'padding': '0.4em 1em'}
    ),
    dcc.Graph(
        id='map',
        style={'height': '90vh'},
        figure=dict(layout=dict(autosize=True)),
        config=dict(responsive=True, displayModeBar=False, scrollZoom=True)
    ),
    html.Div(
        dcc.Slider(
            0, 1, step=1, value=0,
            id='snapshot-slider'
        )
    )
])


@app.callback(
    Output('map', 'figure'),
    Output('snapshot-slider', 'max'),
    Output('snapshot-slider', 'marks'),
    Output('snapshot-slider', 'value'),
    Input('url', 'pathname'),
    Input('snapshot-slider', 'value'))
def update_figure(pathname: str, snapshot_index: int):
    fig, snapshots = figure_for(network_key_from_path(pathname))
    if ctx.triggered_id != 'snapshot-slider' or snapshot_index >= len(snapshots):
        snapshot_index = min(6, len(snapshots) - 1)  # Midday by default
    marks = {
        idx: dict(label=str(snapshot.time()), style=dict(writingMode='vertical-rl'))
        for idx, snapshot in enumerate(snapshots)
    }
    return ppf.show_snapshot(fig, snapshot_index), len(snapshots) - 1, marks, snapshot_index


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True)
