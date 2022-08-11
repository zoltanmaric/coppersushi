import pandas as pd
import plotly.graph_objects as go
import pypsa


def get_marginal_prices(n: pypsa.Network, snapshot, name: str) -> float:
    marginal_price = n.buses_t.marginal_price.loc[snapshot][name]
    if -650 < marginal_price < 0:
        return marginal_price
    else:
        return None


def get_curtailed_power(n: pypsa.Network, snapshot, name: str) -> float:
    # display(name)
    generators_at_bus = n.generators.query(f'bus == "{name}"')
    # generators_at_bus = n.generators.query(f'bus == "7421"')
    # display(generators_at_bus)
    generators_t_p = n.generators_t.p.filter(generators_at_bus.index).loc[snapshot]
    # print("generators_t_p")
    # display(generators_t_p.T)
    generators_t_p_max_pu = n.generators_t.p_max_pu.filter(generators_at_bus.index).loc[snapshot]
    # print("generators_t_p_max_pu")
    # display(generators_t_p_max_pu.T)
    # print("denominator")
    # display((generators_t_p_max_pu * generators_at_bus.p_nom).T)
    usage_factor_series = generators_t_p / (generators_t_p_max_pu * generators_at_bus.p_nom) * 100
    rounded_usage_factor = usage_factor_series.round(decimals=2)
    # print("rounded")
    # display(rounded_usage_factor.T)
    curtailed_power = 100 - rounded_usage_factor
    # print("curtailed_power")
    # display(curtailed_power.T)
    # print("curtailed_power.sum")
    # display(curtailed_power.sum())
    return curtailed_power.sum()


def get_technology_power(n: pypsa.Network, technology: str) -> pd.Series:
    p_by_generators = n.generators_t.p.filter(like=technology)

    # Rename generators columns to their corresponding bus names
    # This may result with multiple columns with the same name,
    # if multiple generators were matched on the same bus for the given technology
    p_by_buses = p_by_generators.rename(n.generators.bus, axis='columns').rename_axis('Bus', axis='columns')

    # Group and sum by bus, in case there's multiple generators for a tech substring
    # (e.g. offwind and onwind for 'wind')
    p_by_buses_sum = p_by_buses.groupby(by=lambda bus_name: bus_name, axis='columns').sum()
    return p_by_buses_sum


def get_loads_power(n: pypsa.Network, snapshot, name: str) -> float:
    loads_t_p = n.loads_t.p_set.loc[snapshot].filter([name])
    # print('{name}:'.format(value=loads_t_p, name='loads_t_p'))
    # display(loads_t_p)
    return loads_t_p.sum()


def create_traces(n: pypsa.Network, bus_colors: pd.Series) -> go.Trace:
    # Create edges
    edge_x = []
    edge_y = []
    for name, line in n.lines.iterrows():
        bus0 = n.buses.loc[line.bus0]
        bus1 = n.buses.loc[line.bus1]
        x0, y0 = bus0.x, bus0.y
        x1, y1 = bus1.x, bus1.y
        edge_x.append(x0)
        edge_x.append(x1)
        edge_x.append(None)
        edge_y.append(y0)
        edge_y.append(y1)
        edge_y.append(None)

    edge_trace = go.Scattermapbox(
        lon=edge_x, lat=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines',
        visible=False
    )

    node_x = n.buses.x.filter(bus_colors.index)
    node_y = n.buses.y.filter(bus_colors.index)
    print('{name}:'.format(value=node_x, name='node_x'))
    display(node_x.to_frame().T)
    print('{name}:'.format(value=node_y, name='node_y'))
    display(node_y.to_frame().T)
    print('{name}:'.format(value=bus_colors, name='bus_colors'))
    display(bus_colors.to_frame().T)

    node_trace = go.Scattermapbox(
        lon=node_x, lat=node_y,
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
            )))

    # Color nodes
    node_trace.marker.color = bus_colors
    node_trace.text = bus_colors

    return node_trace, edge_trace


def colored_network_figure(n: pypsa.Network) -> go.Figure:
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
    snapshots = n.snapshots[0:2]
    display(snapshots)
    bus_colors = get_technology_power(n, 'wind')
    for i, snapshot in enumerate(snapshots):
        print('{name}: {value}'.format(value=snapshot, name='snapshot'))
        node_trace, edge_trace = create_traces(n, bus_colors.loc[snapshot])
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