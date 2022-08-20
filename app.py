import pandas as pd
import scripts.plot_power_flow as ppf
import plotly.graph_objects as go
import pypsa
from dash import Dash, dcc, html, Input, Output

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = Dash(__name__, external_stylesheets=external_stylesheets)

server = app.server

df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminderDataFiveYear.csv')

app.layout = html.Div([
    dcc.Graph(
        id='graph-with-slider',
        style={'height': '90vh'},
        figure=dict(layout=dict(autosize=True)),
        config=dict(responsive=True)
    ),
    html.Div(
        dcc.Slider(
            df['year'].min(),
            df['year'].max(),
            step=None,
            value=df['year'].min(),
            marks={str(year): str(year) for year in df['year'].unique()},
            id='year-slider'
        ),
        hidden=True
    )
])

n = pypsa.Network('networks/elec_s_all_ec_lv1.01_2H.nc')
fig = ppf.colored_network_figure(n, 'net_power')
fig.update_layout(
    mapbox=dict(center=go.layout.mapbox.Center(lat=55, lon=12), zoom=3.3)
)


@app.callback(
    Output('graph-with-slider', 'figure'),
    Input('year-slider', 'value'))
def update_figure(selected_year):
    # filtered_df = df[df.year == selected_year]

    # fig = px.scatter(filtered_df, x="gdpPercap", y="lifeExp",
    #                  size="pop", color="continent", hover_name="country",
    #                  log_x=True, size_max=55)
    #
    # fig.update_layout(transition_duration=500)

    return fig


if __name__ == '__main__':
    app.run_server(debug=True)
