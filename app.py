import pandas as pd

import scripts.plot_power_flow as ppf
import plotly.graph_objects as go
import pypsa
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc

app = Dash(__name__, title='Copper Sushi 🍣', external_stylesheets=[dbc.themes.DARKLY])

server = app.server

n = pypsa.Network('networks/elec_s_all_ec_lv1.01_2H.nc')
fig = ppf.colored_network_figure(n, 'net_power')
fig.update_layout(
    mapbox=dict(center=go.layout.mapbox.Center(lat=53, lon=9), zoom=3.9, pitch=60)
)

app.layout = html.Div([
    dcc.Graph(
        id='map',
        style={'height': '90vh'},
        figure=dict(layout=dict(autosize=True)),
        config=dict(responsive=True, displayModeBar=False)
    ),
    html.Div(
        dcc.Slider(
            0,
            len(n.snapshots) - 1,
            step=1,
            value=0,
            marks={
                idx: dict(
                    label=str(snapshot.time()),
                    style=dict(writingMode='vertical-rl')
                ) for idx, snapshot in enumerate(n.snapshots)
            },
            id='snapshot-slider'
        )
    )
])


@app.callback(
    Output('map', 'figure'),
    Input('snapshot-slider', 'value'))
def update_figure(selected_snapshot_index: int) -> go.Figure:
    figure = ppf.show_snapshot(fig, selected_snapshot_index)
    return figure


if __name__ == '__main__':
    app.run_server(debug=True)
