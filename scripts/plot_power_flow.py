import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pyproj
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


def get_bus_coordinates(n: pypsa.Network, bus_name: str) -> pd.DataFrame:
    return n.buses.loc[n.lines[bus_name]][['x', 'y']] \
            .set_index(n.lines.index) \
            .rename(dict(x=bus_name+'_x', y=bus_name+'_y'), axis='columns')


def get_line_direction(line_info: pd.DataFrame) -> float:
    """Line power flow direction angle (clockwise from North)"""

    # Mercator projection, as used by MapBox: https://docs.mapbox.com/mapbox-gl-js/example/projections/
    geodesic = pyproj.Geod(ellps='WGS84')
    directions = line_info.apply(
        lambda row: pd.Series(
            list(geodesic.inv(row.bus0_x, row.bus0_y, row.bus1_x, row.bus1_y))[0:2],
            index=['direction', 'inverse_direction']
        ),
        axis='columns'
    )

    return directions


def get_line_info(n: pypsa.Network) -> pd.DataFrame:
    """Builds a DataFrame with edge & middle point coordinates, power flow direction angles for each line."""
    bus0_coordinates = get_bus_coordinates(n, 'bus0')
    bus1_coordinates = get_bus_coordinates(n, 'bus1')
    line_info = pd.concat([bus0_coordinates, bus1_coordinates], axis='columns')

    line_info['mid_x'] = (line_info.bus1_x + line_info.bus0_x) / 2
    line_info['mid_y'] = (line_info.bus1_y + line_info.bus0_y) / 2

    line_info[['direction', 'inverse_direction']] = get_line_direction(line_info)

    return line_info


def get_line_edge(line_info: pd.DataFrame, x_or_y: str) -> pd.Series:
    return line_info.apply(lambda row: [row['bus0_' + x_or_y], row['bus1_' + x_or_y], None], axis='columns')


def create_traces(
        nodes_x: pd.Series,
        nodes_y: pd.Series,
        node_values: pd.Series,
        line_info: pd.DataFrame,
        edge_values: pd.Series,
        cmax: float
) -> (go.Trace, go.Trace, go.Trace):
    loaded_filter = abs(edge_values) > 0.99
    edges_x = get_line_edge(line_info, 'x')
    edges_y = get_line_edge(line_info, 'y')

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

    # Edge values will be positive if power is flowing from bus0 to bus1
    edge_info = pd.concat([line_info, edge_values.rename('edge_value')], axis='columns')
    edge_info['arrow_angle'] = edge_info.apply(
        lambda row: row.direction if row.edge_value >= 0 else row.inverse_direction, axis='columns'
    )

    line_direction_trace = go.Scattermapbox(
        lon=line_info.mid_x, lat=line_info.mid_y,
        mode='markers',
        hoverinfo='text',
        visible=False,
        text=abs(edge_info.edge_value),
        marker=go.scattermapbox.Marker(
            size=7,
            # List of available markers:
            # https://community.plotly.com/t/how-to-add-a-custom-symbol-image-inside-map/6641/2
            symbol='triangle',
            angle=edge_info.arrow_angle
        )
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

    return node_trace, loaded_lines_trace, easy_lines_trace, line_direction_trace


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

    edge_values = n.lines_t.p0 / (n.lines.s_nom_opt * n.lines.s_max_pu)

    nodes_x = n.buses.x.filter(node_values.columns)
    nodes_y = n.buses.y.filter(node_values.columns)

    line_info = get_line_info(n)

    print('{name}:'.format(value=line_info.head(), name='line_info.head()'))
    display(line_info.head())

    num_traces = 4

    # Create and add slider
    for i, snapshot in enumerate(snapshots):
        node_trace, loaded_lines_trace, easy_lines_trace, line_direction_trace = create_traces(
            nodes_x,
            nodes_y,
            node_values.loc[snapshot],
            line_info,
            edge_values.loc[snapshot],
            cmax
        )
        # Node annotation pop-ups only show if `node_trace` is added last
        fig.add_traces(data=[loaded_lines_trace, easy_lines_trace, line_direction_trace, node_trace])

        step = dict(
            label=str(snapshot),
            method="update",
            args=[{"visible": [False] * len(snapshots) * num_traces}],
        )

        for trace_idx in range(num_traces):
            step["args"][0]["visible"][i * num_traces + trace_idx] = True  # Toggle i'th snapshot to "visible"

        steps.append(step)

    sliders = [dict(
        active=0,
        currentvalue={"prefix": "Snapshot: "},
        pad={"t": 50},
        steps=steps
    )]
    # Make first set of traces (nodes & edges) visible
    for trace_idx in range(num_traces):
        fig.data[trace_idx].visible = True

    # Register and get a free access token at https://www.mapbox.com/
    # and paste it into a file at the path below
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
