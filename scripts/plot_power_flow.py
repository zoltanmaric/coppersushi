from collections.abc import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pypsa
from IPython.display import display


def sum_generators_t_attribute_by_bus(n: pypsa.Network, generators_t_attr: pd.Series, technology: str = None) -> pd.Series:
    attribute_by_generators = generators_t_attr.filter(like=technology) if technology else generators_t_attr

    # Rename generators columns to their corresponding bus names
    # This may result with multiple columns with the same name,
    # if multiple generators were matched on the same bus for the given technology
    attribute_by_buses = attribute_by_generators.rename(n.generators.bus, axis='columns').\
        rename_axis('Bus', axis='columns')

    # Group and sum by bus, in case there's multiple generators for a tech substring
    # (e.g. offwind and onwind for 'wind')
    attribute_by_buses_sum = attribute_by_buses.groupby(by=lambda bus_name: bus_name, axis='columns').sum()
    return attribute_by_buses_sum


def get_curtailed_power(n: pypsa.Network, technology: str = None) -> pd.Series:
    usage_factor_series = n.generators_t.p / (n.generators_t.p_max_pu * n.generators.p_nom) * 100
    rounded_usage_factor = usage_factor_series.round(decimals=2)
    curtailed_power_per_generator = 100 - rounded_usage_factor
    curtailed_power_per_bus = sum_generators_t_attribute_by_bus(
        n, generators_t_attr=curtailed_power_per_generator, technology=technology)
    return curtailed_power_per_bus


def get_line_edge(n, x_or_y) -> Callable[[pypsa.Network, str], list]:
    return lambda line: [n.buses.loc[line.bus0][x_or_y], n.buses.loc[line.bus1][x_or_y], None]


def create_traces(
        nodes_x: pd.Series,
        nodes_y: pd.Series,
        edges_x: pd.Series,
        edges_y: pd.Series,
        node_values: pd.Series,
        edge_values: pd.Series,
        cmax: float
) -> (go.Trace, go.Trace, go.Trace):
    loaded_filter = edge_values > 0.99

    loaded_lines_trace = go.Scattermapbox(
        lon=edges_x[loaded_filter].dropna().explode(), lat=edges_y[loaded_filter].dropna().explode(),
        # line=dict(width=4.0, color='#f52ad0'),  # pink
        line=dict(width=4.0, color='#a72af5'),  # violet
        hoverinfo='none',
        mode='lines',
        visible=False
    )

    easy_lines_trace = go.Scattermapbox(
        lon=edges_x[(~loaded_filter)].dropna().explode(), lat=edges_y[(~loaded_filter)].dropna().explode(),
        line=dict(width=0.5, color='gray'),
        hoverinfo='none',
        mode='lines',
        visible=False
    )

    node_trace = go.Scattermapbox(
        lon=nodes_x, lat=nodes_y,
        mode='markers',
        hoverinfo='text',
        visible=False,
        text=round(node_values).astype(str) + ' MW',
        marker=go.scattermapbox.Marker(
            showscale=True,
            # colorscale options https://plotly.com/python/builtin-colorscales/
            colorscale='tropic',
            reversescale=True,
            color=node_values,
            cmin=-cmax,
            cmax=cmax,
            size=10,
            colorbar=dict(
                thickness=15,
                title='Net Power Feed-In at Node [MW]',
                xanchor='left',
                titleside='right'
            )
        )
    )

    return node_trace, loaded_lines_trace, easy_lines_trace


def get_interquartile_range(df: pd.DataFrame) -> pd.DataFrame:
    q1 = np.quantile(df, 0.25)
    q3 = np.quantile(df, 0.75)
    iqr = q3 - q1

    min = q1 - 1.5 * iqr
    max = q3 + 1.5 * iqr

    return min, max


def colored_network_figure(n: pypsa.Network, what: str, technology: str = None) -> go.Figure:
    # Create Network Graph
    fig = go.Figure(layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20, l=5, r=5, t=40),
                        annotations=[],
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                    )

    steps = []
    snapshots = n.snapshots  # [0:1]
    if type(what) == pd.DataFrame:
        node_values = what
    elif what == 'net_power':
        node_values = n.buses_t.p
    elif what == 'load':
        node_values = n.loads_t.p_set
    elif what == 'generation':
        node_values = sum_generators_t_attribute_by_bus(n, n.generators_t.p, technology)
    elif what == 'curtailment':
        node_values = get_curtailed_power(n, technology)
    elif what == 'marginal_price':
        node_values = n.buses_t.marginal_price
    else:
        raise Exception(f'Unknown what: "{what}"')

    iqr_min, iqr_max = get_interquartile_range(node_values)
    cmax = max(abs(iqr_min), abs(iqr_max))

    edge_values = abs(n.lines_t.p0) / (n.lines.s_nom_opt * n.lines.s_max_pu)

    nodes_x = n.buses.x.filter(node_values.columns)
    nodes_y = n.buses.y.filter(node_values.columns)

    edges_x = n.lines.apply(get_line_edge(n, 'x'), axis='columns')
    edges_y = n.lines.apply(get_line_edge(n, 'y'), axis='columns')

    # Create and add slider
    for i, snapshot in enumerate(snapshots):
        # print('{name}: {value}'.format(value=snapshot, name='snapshot'))
        node_trace, loaded_lines_trace, easy_lines_trace = create_traces(
            nodes_x, nodes_y, edges_x, edges_y, node_values.loc[snapshot], edge_values.loc[snapshot], cmax)
        # Node annotation pop-ups only show if `node_trace` is added last
        fig.add_traces(data=[loaded_lines_trace, easy_lines_trace, node_trace])

        step = dict(
            label=str(snapshot),
            method="update",
            args=[{"visible": [False] * len(snapshots) * 3}],  # Each snapshot has 1 node and 2 line traces
        )
        step["args"][0]["visible"][i*3] = True  # Toggle i'th trace to "visible"
        step["args"][0]["visible"][i*3 + 1] = True  # Toggle i'th trace to "visible"
        step["args"][0]["visible"][i*3 + 2] = True  # Toggle i'th trace to "visible"
        steps.append(step)

    sliders = [dict(
        active=0,
        currentvalue={"prefix": "Snapshot: "},
        pad={"t": 50},
        steps=steps
    )]
    # Make first triple of traces (nodes & edges) visible
    fig.data[0].visible = True
    fig.data[1].visible = True
    fig.data[2].visible = True

    # Register and get a free access token at https://www.mapbox.com/
    mapbox_token = open(".secrets/.mapbox_token").read()

    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0},
                      # Available maps: https://plotly.com/python/mapbox-layers#base-maps-in-layoutmapboxstyle
                      mapbox_style="dark",
                      # Only required for mapbox styles
                      mapbox_accesstoken=mapbox_token,
                      sliders=sliders
                      )

    return fig


if __name__ == "__main__":
    n = pypsa.Network("results/networks/elec_s_all_ec_lv1.1_2H.nc")
    colored_network_figure(n, 'net_power')
