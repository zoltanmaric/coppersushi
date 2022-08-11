from collections.abc import Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pypsa


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
        node_values: pd.Series
) -> go.Trace:
    edge_trace = go.Scattermapbox(
        lon=edges_x, lat=edges_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines',
        visible=False
    )

    node_trace = go.Scattermapbox(
        lon=nodes_x, lat=nodes_y,
        mode='markers',
        hoverinfo='text',
        visible=False,
        marker=dict(
            showscale=True,
            # colorscale options
            # 'Greys' | 'YlGnBu' | 'Greens' | 'YlOrRd' | 'Bluered' | 'RdBu' |
            # 'Reds' | 'Blues' | 'Picnic' | 'Rainbow' | 'Portland' | 'Jet' |
            # 'Hot' | 'Blackbody' | 'Earth' | 'Electric' | 'Viridis' |
            colorscale='YlGnBu',
            reversescale=False,
            color=[],
            size=7,
            colorbar=dict(
                thickness=15,
                title='Node Connections',
                xanchor='left',
                titleside='right'
            )
        )
    )

    # Color nodes
    node_trace.marker.color = node_values
    node_trace.text = node_values

    return node_trace, edge_trace


def remove_extremes(df: pd.DataFrame) -> pd.DataFrame:
    q1 = np.quantile(df, 0.25)
    q3 = np.quantile(df, 0.75)
    iqr = q3 - q1

    min = q1 - 1.5 * iqr
    max = q3 + 1.5 * iqr

    return df[min < df][df < max]


def colored_network_figure(n: pypsa.Network, what: str, technology: str = None) -> go.Figure:
    # Create Network Graph
    fig = go.Figure(layout=go.Layout(
                        title='<br>Network graph made with Python',
                        titlefont_size=16,
                        showlegend=False,
                        hovermode='closest',
                        margin=dict(b=20, l=5, r=5, t=40),
                        annotations=[dict(
                            text="Python code: <a href='https://plotly.com/ipython-notebooks/network-graphs/'> https://plotly.com/ipython-notebooks/network-graphs/</a>",
                            showarrow=False,
                            xref="paper", yref="paper",
                            x=0.005, y=-0.002)],
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                    )

    # Create and add slider
    steps = []
    snapshots = n.snapshots #[0:6]
    if type(what) == pd.DataFrame:
        node_values = what
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

    print('Removing extremes outside of Q1 - 1.5*IQR < x < Q3 + 1.5*IQR')
    node_values = remove_extremes(node_values)

    print('{name}:'.format(value=node_values.head(), name='node_values.head()'))
    display(node_values.head())

    nodes_x = n.buses.x.filter(node_values.columns)
    nodes_y = n.buses.y.filter(node_values.columns)

    edges_x = n.lines.apply(get_line_edge(n, 'x'), axis='columns').explode()
    edges_y = n.lines.apply(get_line_edge(n, 'y'), axis='columns').explode()

    for i, snapshot in enumerate(snapshots):
        # print('{name}: {value}'.format(value=snapshot, name='snapshot'))
        node_trace, edge_trace = create_traces(nodes_x, nodes_y, edges_x, edges_y, node_values.loc[snapshot])
        fig.add_traces(data=[edge_trace, node_trace])

        step = dict(
            label=str(snapshot),
            method="update",
            args=[{"visible": [False] * len(snapshots) * 2}],  # layout attribute
        )
        step["args"][0]["visible"][i*2] = True  # Toggle i'th trace to "visible"
        step["args"][0]["visible"][i*2 + 1] = True  # Toggle i'th trace to "visible"
        steps.append(step)

    sliders = [dict(
        active=0,
        currentvalue={"prefix": "Snapshot: "},
        pad={"t": 50},
        steps=steps
    )]
    # Make first pair of traces (nodes & edges) visible
    fig.data[0].visible = True
    fig.data[1].visible = True

    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0},
                      mapbox_style="open-street-map",
                      sliders=sliders
                      )

    return fig
