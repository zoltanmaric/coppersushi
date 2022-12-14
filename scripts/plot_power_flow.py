from typing import Tuple, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import pyproj
import pypsa

from scripts.network_snapshot import NetworkSnapshot

# For each snapshot, a figure has 4 traces
# (the nodes, the loaded lines, the non-loaded lines,
# and the power flow direction arrows)
NUM_TRACES_PER_SNAPSHOT = 4

pio.templates.default = "plotly_dark"


def sum_generators_t_attribute_by_bus(n: pypsa.Network, generators_t_attr: pd.DataFrame, technology: str = None) -> pd.Series:
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


def get_curtailed_power(n: pypsa.Network, tech_regex: str = None) -> pd.Series:
    usage_factor_series = n.generators_t.p / (n.generators_t.p_max_pu * n.generators.p_nom) * 100
    rounded_usage_factor = usage_factor_series.round(decimals=2)
    curtailed_power_per_generator = 100 - rounded_usage_factor
    curtailed_power_per_bus = sum_generators_t_attribute_by_bus(
        n, generators_t_attr=curtailed_power_per_generator, tech_regex=tech_regex)
    return curtailed_power_per_bus


def get_bus_coordinates(n: pypsa.Network, bus_name: str) -> pd.DataFrame:
    return n.buses.loc[n.branches()[bus_name]][['x', 'y']] \
            .set_index(n.branches().index) \
            .rename(dict(x=bus_name+'_x', y=bus_name+'_y'), axis='columns')


# Mercator projection, as used by MapBox: https://docs.mapbox.com/mapbox-gl-js/example/projections/
epsg3857 = pyproj.Proj('epsg:3857')


def get_branch_midpoint(branch_info: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Project lat/lon of branch buses to x/y coordinates,
    calculate mid-point between them,
    project mid-point back to lat/lon coordinates."""

    x0, y0 = epsg3857(longitude=branch_info.bus0_x, latitude=branch_info.bus0_y)
    x1, y1 = epsg3857(longitude=branch_info.bus1_x, latitude=branch_info.bus1_y)
    mid_x = (x0 + x1) / 2
    mid_y = (y0 + y1) / 2
    mid_lon, mid_lat = epsg3857(longitude=mid_x, latitude=mid_y, inverse=True)

    return mid_lon, mid_lat


geodesic = pyproj.Geod(ellps='WGS84')


def get_branch_direction(branch_info: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Branch power flow direction angle (clockwise from North)"""
    [direction, inverse_direction, _] = \
        geodesic.inv(branch_info.bus0_x, branch_info.bus0_y, branch_info.bus1_x, branch_info.bus1_y)
    return direction, inverse_direction


def get_branch_info(n: pypsa.Network) -> pd.DataFrame:
    """Builds a DataFrame with edge & middle point coordinates, power flow direction angles for each line."""
    bus0_coordinates = get_bus_coordinates(n, 'bus0')
    bus1_coordinates = get_bus_coordinates(n, 'bus1')
    branch_info = pd.concat([bus0_coordinates, bus1_coordinates], axis='columns')

    branch_info['mid_x'], branch_info['mid_y'] = get_branch_midpoint(branch_info)

    # Lines have apparent power (s) set
    branch_info['p_max'] = n.branches().s_max_pu * n.branches().s_nom_opt
    # Links have real power (p) set
    branch_info.p_max.fillna(n.branches().p_max_pu * n.branches().p_nom_opt, inplace=True)

    branch_info['direction'], branch_info['inverse_direction'] = get_branch_direction(branch_info)

    return branch_info


def to_branches_by_component_and_name(
        branches: pd.DataFrame, snapshot: pd.Timestamp, component: str, quantity: str) -> pd.DataFrame:
    """Indexes the given series by component (Link or Line) and branch name"""
    df = branches[quantity].loc[snapshot].rename(quantity).rename_axis('name').to_frame()
    df['component'] = component
    return df.set_index('component', append=True).reorder_levels(['component', 'name'])


def get_branch_info_for_snapshot(n: pypsa.Network, branch_info: pd.DataFrame, snapshot: pd.Timestamp) -> pd.DataFrame:
    lines_t_p0 = to_branches_by_component_and_name(n.lines_t, snapshot, 'Line', 'p0')
    links_t_p0 = to_branches_by_component_and_name(n.links_t, snapshot, 'Link', 'p0')
    branch_info_t = branch_info.join(pd.concat([lines_t_p0, links_t_p0]))

    branch_info_t['branch_loading'] = abs(branch_info_t.p0) / branch_info_t.p_max * 100
    branch_info_t['arrow_angle'] = branch_info_t.apply(
        lambda row: row.direction if row.p0 >= 0 else row.inverse_direction, axis='columns'
    )

    return branch_info_t


def get_node_info_for_snapshot(n: pypsa.Network, snapshot: pd.Timestamp) -> pd.DataFrame:
    ns = NetworkSnapshot(n, snapshot)
    tooltips_htmls = get_tooltip_htmls(ns)
    return pd.concat([ns.buses, tooltips_htmls], axis='columns')


def get_branch_edge(line_info: pd.DataFrame, x_or_y: str) -> pd.Series:
    return line_info.apply(lambda row: [row['bus0_' + x_or_y], row['bus1_' + x_or_y], None], axis='columns')


def generators_to_html(rows: 'pd.Series[str]') -> str:
    return '<b>Generation:</b><br>' + '\n<b>+</b> '.join(rows) + '--<br>'


def get_tooltip_htmls(ns: NetworkSnapshot) -> 'pd.Series[str]':
    p = round(ns.generators.p, 2).astype(str)
    p_max = round(ns.generators.p_max, 2).astype(str)
    technologies = ns.generators.index.get_level_values(1)
    flat_generator_htmls = '<b>' + technologies + '</b>: ' + p + '/' + p_max + ' MW<br>'
    generator_htmls = flat_generator_htmls.groupby('Bus').aggregate(generators_to_html).rename('generator')

    p_load = round(ns.loads.p_load, 2).astype(str)
    load_htmls = ('<b>- Load</b>: ' + p_load + ' MW<br>===<br>').rename('load')

    net_p = round(ns.buses.p, 2).astype(str)
    net_power_htmls = ('<b>= Net power: ' + net_p + ' MW</b>').rename('net_p')

    htmls = pd.concat([generator_htmls, load_htmls, net_power_htmls], axis='columns').fillna('')

    return (htmls.generator + htmls.load + htmls.net_p).rename('html')


def create_traces(
        node_info_t: pd.DataFrame,
        branch_info_t: pd.DataFrame,
        cmax: float
) -> (go.Trace, go.Trace, go.Trace, go.Trace):
    loaded_filter = branch_info_t.branch_loading > 99
    edges_x = get_branch_edge(branch_info_t, 'x')
    edges_y = get_branch_edge(branch_info_t, 'y')

    loaded_branches_trace = go.Scattermapbox(
        lon=edges_x[loaded_filter].dropna().explode(), lat=edges_y[loaded_filter].dropna().explode(),
        # line=dict(width=4.0, color='#f52ad0'),  # pink
        line=dict(width=4.0, color='#a72af5'),  # violet
        hoverinfo='none',
        mode='lines',
        visible=False
    )

    easy_branches_trace = go.Scattermapbox(
        lon=edges_x[(~loaded_filter)].dropna().explode(), lat=edges_y[(~loaded_filter)].dropna().explode(),
        line=dict(width=0.5, color='gray'),
        hoverinfo='none',
        mode='lines',
        visible=False
    )

    branch_direction_trace = go.Scattermapbox(
        lon=branch_info_t.mid_x, lat=branch_info_t.mid_y,
        mode='markers',
        hoverinfo='text',
        visible=False,
        text='<b>Flow:</b> ' + abs(branch_info_t.p0).astype(int).astype(str) + '/' + branch_info_t.p_max.astype(int).astype(str) + ' MW',
        marker=go.scattermapbox.Marker(
            size=7,
            # List of available markers:
            # https://community.plotly.com/t/how-to-add-a-custom-symbol-image-inside-map/6641/2
            symbol='triangle',
            angle=branch_info_t.arrow_angle
        )
    )

    node_max_size = 11
    node_trace = go.Scattermapbox(
        lon=node_info_t.x, lat=node_info_t.y,
        mode='markers',
        hoverinfo='text',
        visible=False,
        text=node_info_t.html,
        marker=go.scattermapbox.Marker(
            showscale=True,
            # colorscale options https://plotly.com/python/builtin-colorscales/
            colorscale='tropic',
            reversescale=True,
            color=node_info_t.p,
            cmin=-cmax,
            cmax=cmax,
            size=node_info_t.p.abs(),
            sizemin=2.5,
            sizemode='area',
            sizeref=node_info_t.p.abs().max() / node_max_size ** 2,
            colorbar=go.scattermapbox.marker.ColorBar(
                thickness=15,
                title='Net Power Feed-In at Node [MW]',
                orientation='h',
                # Place colorbar at 0.02 times the height of the figure *below* the figure
                # (negative value means below)
                y=-0.02,
                # The y-value is counted from the top of the colorbar
                yanchor='top',
                # Put the title of the colorbar *above* the colorbar
                # (default is on the side)
                titleside='top'
            )
        )
    )

    return node_trace, loaded_branches_trace, easy_branches_trace, branch_direction_trace


def get_interquartile_range(df: pd.DataFrame) -> pd.DataFrame:
    q1 = np.quantile(df, 0.25)
    q3 = np.quantile(df, 0.75)
    iqr = q3 - q1

    min = q1 - 1.5 * iqr
    max = q3 + 1.5 * iqr

    return min, max


def show_snapshot(fig: go.Figure, snapshot_index: int) -> go.Figure:
    active_trace_id_start = snapshot_index * NUM_TRACES_PER_SNAPSHOT
    active_trace_id_end = active_trace_id_start + NUM_TRACES_PER_SNAPSHOT
    for trace_id in range(len(fig.data)):
        if trace_id in range(active_trace_id_start, active_trace_id_end):
            fig.update_traces(dict(visible=True), selector=trace_id)
        else:
            fig.update_traces(dict(visible=False), selector=trace_id)

    return fig


def colored_network_figure(n: pypsa.Network, what: str, technology: str = None) -> go.Figure:
    # Create Network Graph
    fig = go.Figure(layout=go.Layout(
        showlegend=False,
        hovermode='closest',
        margin=dict(b=20, l=5, r=5, t=40),
        annotations=[],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        # This persists users' zoom between callbacks
        uirevision=True
    ))

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

    branch_info = get_branch_info(n)

    # Create and add traces
    for i, snapshot in enumerate(snapshots):
        node_info_t = get_node_info_for_snapshot(n, snapshot)
        branch_info_t = get_branch_info_for_snapshot(n, branch_info, snapshot)

        node_trace, loaded_branches_trace, easy_branches_trace, branch_direction_trace = create_traces(
            node_info_t,
            branch_info_t,
            cmax
        )
        # Node annotation pop-ups only show if `node_trace` is added last
        fig.add_traces(data=[loaded_branches_trace, easy_branches_trace, branch_direction_trace, node_trace])

    # Make first set of traces (nodes & edges) visible
    fig = show_snapshot(fig, snapshot_index=0)

    # Register and get a free access token at https://www.mapbox.com/
    # and paste it into a file at the path below
    mapbox_token = open(".secrets/.mapbox_token").read()

    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0},
                      # Available maps: https://plotly.com/python/mapbox-layers#base-maps-in-layoutmapboxstyle
                      mapbox_style="dark",
                      # Only required for mapbox styles
                      mapbox_accesstoken=mapbox_token
                      )
    fig.update_geos(projection_type='mercator')

    return fig


if __name__ == "__main__":
    n = pypsa.Network("results/networks/elec_s_all_ec_lv1.1_2H.nc")
    colored_network_figure(n, 'net_power')
