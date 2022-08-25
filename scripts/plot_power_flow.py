import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import pyproj
import pypsa
import jsons

from scripts.network_snapshot import NetworkSnapshot

# For each snapshot, a figure has 4 traces
# (the nodes, the loaded lines, the non-loaded lines,
# and the power flow direction arrows)
from scripts.node_info import NodeInfo

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


def map_carrier(row: pd.Series) -> str:
    grouping = {
        'nuclear': 'nuclear',
        'geothermal': 'geothermal',
        'biomass': 'biomass',
        'coal': 'fossil',
        'CCGT': 'fossil',
        'oil': 'fossil',
        'lignite': 'fossil',
        'hydro': 'hydro',
        'offwind-ac': 'wind',
        'offwind-dc': 'wind',
        'onwind': 'wind',
        'solar': 'solar',
        'PHS': 'hydro',
        'ror': 'hydro'
    }

    return grouping[row.carrier]


def get_node_info(n: pypsa.Network) -> pd.DataFrame:
    """Builds a DataFrame with static node info (e.g. max generation per technology, etc.)"""

    node_info = n.buses[['x', 'y', 'country']].copy()
    generators_p_max = n.generators.p_nom_opt * n.generators.p_max_pu
    generators_weighted_marginal_cost = n.generators.marginal_cost * generators_p_max
    node_info['p_max_wind'] = n.generators.groupby(by=map_carrier)

    node_info['mid_x'] = (node_info.bus1_x + node_info.bus0_x) / 2
    node_info['mid_y'] = (node_info.bus1_y + node_info.bus0_y) / 2

    node_info['s_max'] = n.lines.s_max_pu * n.lines.s_nom_opt

    node_info[['direction', 'inverse_direction']] = get_line_direction(node_info)

    return node_info


def get_line_info(n: pypsa.Network) -> pd.DataFrame:
    """Builds a DataFrame with edge & middle point coordinates, power flow direction angles for each line."""
    bus0_coordinates = get_bus_coordinates(n, 'bus0')
    bus1_coordinates = get_bus_coordinates(n, 'bus1')
    line_info = pd.concat([bus0_coordinates, bus1_coordinates], axis='columns')

    line_info['mid_x'] = (line_info.bus1_x + line_info.bus0_x) / 2
    line_info['mid_y'] = (line_info.bus1_y + line_info.bus0_y) / 2

    line_info['s_max'] = n.lines.s_max_pu * n.lines.s_nom_opt

    line_info[['direction', 'inverse_direction']] = get_line_direction(line_info)

    return line_info


def get_line_info_for_snapshot(n: pypsa.Network, line_info: pd.DataFrame, snapshot: str) -> pd.DataFrame:
    line_info_t = pd.concat([line_info, n.lines_t.p0.loc[snapshot].rename('p0')], axis='columns')
    line_info_t['line_loading'] = abs(line_info_t.p0) / line_info_t.s_max * 100
    line_info_t['arrow_angle'] = line_info_t.apply(
        lambda row: row.direction if row.p0 >= 0 else row.inverse_direction, axis='columns'
    )

    return line_info_t


def get_line_edge(line_info: pd.DataFrame, x_or_y: str) -> pd.Series:
    return line_info.apply(lambda row: [row['bus0_' + x_or_y], row['bus1_' + x_or_y], None], axis='columns')


def generators_to_html(group: pd.core.groupby.DataFrameGroupBy) -> 'pd.Series[str]':
    rows = group.apply(lambda row: f'<b>{row.name[1]}</b>: {row.p:.2f} MW<br>', axis='columns')
    generators_html = '<b>Generation:</b><br>' + '\n<b>+</b> '.join(rows)

    return generators_html


def combine_htmls(row: 'pd.Series[str]') -> str:
    if pd.isna(row.generator) and pd.isna(row.load):
        return row.net_p
    else:
        return f"""{row.generator}
--<br>
{row.load}
===<br>
<b>= {row.net_p}</b>
"""


def get_tooltip_htmls(ns: NetworkSnapshot) -> 'pd.Series[str]':
    generator_htmls = ns.generators.groupby('Bus').apply(generators_to_html).rename('generator')
    load_htmls = ns.loads.apply(lambda row: f'<b>- Load</b>: {row.p_load:.2f} MW<br>', axis='columns').rename('load')
    net_power_htmls = ns.buses.apply(lambda row: f'Net power: {row.p:.2f} MW', axis='columns').rename('net_p')
    htmls = pd.concat([generator_htmls, load_htmls, net_power_htmls], axis='columns').apply(combine_htmls, axis='columns')
    return htmls


def create_traces(
        ns: NetworkSnapshot,
        line_info_t: pd.DataFrame,
        cmax: float
) -> (go.Trace, go.Trace, go.Trace, go.Trace):
    loaded_filter = line_info_t.line_loading > 99
    edges_x = get_line_edge(line_info_t, 'x')
    edges_y = get_line_edge(line_info_t, 'y')

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

    line_direction_trace = go.Scattermapbox(
        lon=line_info_t.mid_x, lat=line_info_t.mid_y,
        mode='markers',
        hoverinfo='text',
        visible=False,
        text='<b>Flow:</b> ' + abs(line_info_t.p0).astype(int).astype(str) + '/' + line_info_t.s_max.astype(int).astype(str) + ' MW',
        marker=go.scattermapbox.Marker(
            size=7,
            # List of available markers:
            # https://community.plotly.com/t/how-to-add-a-custom-symbol-image-inside-map/6641/2
            symbol='triangle',
            angle=line_info_t.arrow_angle
        )
    )

    node_powers = ns.buses.apply(lambda bus: bus.p, axis='columns')
    node_sizes = node_powers.abs()
    node_max_size = 11
    tooltips_htmls = get_tooltip_htmls(ns)
    node_trace = go.Scattermapbox(
        lon=ns.buses.apply(lambda bus: bus.x, axis='columns'), lat=ns.buses.apply(lambda bus: bus.y, axis='columns'),
        mode='markers',
        hoverinfo='text',
        visible=False,
        text=tooltips_htmls,
        marker=go.scattermapbox.Marker(
            showscale=True,
            # colorscale options https://plotly.com/python/builtin-colorscales/
            colorscale='tropic',
            reversescale=True,
            color=node_powers,
            cmin=-cmax,
            cmax=cmax,
            size=node_sizes,
            sizemin=2.5,
            sizemode='area',
            sizeref=node_sizes.max() / node_max_size ** 2,
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

    return node_trace, loaded_lines_trace, easy_lines_trace, line_direction_trace


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

    line_info = get_line_info(n)

    # Create and add traces
    for i, snapshot in enumerate(snapshots):
        ns = NetworkSnapshot(n, snapshot)
        line_info_t = get_line_info_for_snapshot(n, line_info, snapshot)

        node_trace, loaded_lines_trace, easy_lines_trace, line_direction_trace = create_traces(
            ns,
            line_info_t,
            cmax
        )
        # Node annotation pop-ups only show if `node_trace` is added last
        fig.add_traces(data=[loaded_lines_trace, easy_lines_trace, line_direction_trace, node_trace])

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

    return fig


if __name__ == "__main__":
    n = pypsa.Network("results/networks/elec_s_all_ec_lv1.1_2H.nc")
    colored_network_figure(n, 'net_power')
