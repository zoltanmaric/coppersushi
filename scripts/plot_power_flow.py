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
    display(name)
    # generators_at_bus = n.generators.query(f'bus == "{name}"')
    generators_at_bus = n.generators.query(f'bus == "7421"')
    display(generators_at_bus)
    generators_t_p = n.generators_t.p.filter(generators_at_bus.index).loc[snapshot]
    print("generators_t_p")
    display(generators_t_p.T)
    generators_t_p_max_pu = n.generators_t.p_max_pu[generators_at_bus.index].loc[snapshot]
    print("generators_t_p_max_pu")
    display(generators_t_p_max_pu.T)
    print("denominator")
    display((generators_t_p_max_pu * generators_at_bus.p_nom).T)
    curtailed_power_series = generators_t_p / (generators_t_p_max_pu * generators_at_bus.p_nom) * 100
    rounded = curtailed_power_series.round(decimals=2)
    print("rounded")
    display(rounded.T)
    curtailed_power = rounded
    print("curtailed_power")
    display(curtailed_power.T)
    print("curtailed_power.sum")
    display(curtailed_power.sum())
    return curtailed_power.sum()


def get_technology_power(n: pypsa.Network, snapshot, name: str, technology: str) -> float:
    # print('{name}: {value}'.format(value=name, name='name'))
    generators_at_bus = n.generators.query(f'bus == "{name}"')
    # print("generators_at_bus")
    # display(generators_at_bus)
    tech_specific_generators_at_bus = [g for g in generators_at_bus.index.to_list() if technology in g]
    # print("tech specific generators at bus")
    # display(tech_specific_generators_at_bus)
    generators_t_p = n.generators_t.p.filter(tech_specific_generators_at_bus).loc[snapshot]
    # print("generators_t_p")
    # display(generators_t_p)
    # print('{name}:'.format(value=generators_t_p.sum(), name='generators_t_p.sum()'))
    # display(generators_t_p.sum())
    return generators_t_p.sum()


def get_loads_power(n: pypsa.Network, snapshot, name: str) -> float:
    loads_t_p = n.loads_t.p_set.loc[snapshot].filter([name])
    # print('{name}:'.format(value=loads_t_p, name='loads_t_p'))
    # display(loads_t_p)
    return loads_t_p.sum()


def colored_network_figure(n: pypsa.Network) -> go.Figure:
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
        mode='lines')

    node_x = []
    node_y = []
    index = 331*8 + 4
    # index = 6
    snapshot = n.snapshots[index]
    print('{name}: {value}'.format(value=snapshot, name='snapshot'))
    bus_colors = []
    for name, bus in n.buses.iterrows():
        bus_color = get_loads_power(n, snapshot, name)
        if bus_color:
            node_x.append(bus.x)
            node_y.append(bus.y)
            bus_colors.append(bus_color)

    node_trace = go.Scattermapbox(
        lon=node_x, lat=node_y,
        mode='markers',
        hoverinfo='text',
        marker=dict(
            showscale=True,
            # colorscale options
            # 'Greys' | 'YlGnBu' | 'Greens' | 'YlOrRd' | 'Bluered' | 'RdBu' |
            # 'Reds' | 'Blues' | 'Picnic' | 'Rainbow' | 'Portland' | 'Jet' |
            # 'Hot' | 'Blackbody' | 'Earth' | 'Electric' | 'Viridis' |
            colorscale='YlGnBu',
            reversescale=True,
            color=[],
            size=10,
            colorbar=dict(
                thickness=15,
                title='Node Connections',
                xanchor='left',
                titleside='right'
            )))

    # Color nodes
    node_trace.marker.color = bus_colors
    node_trace.text = bus_colors

    # Create Network Graph
    fig = go.Figure(data=[edge_trace, node_trace],
                    layout=go.Layout(
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
    fig.update_layout(height=600, margin={"r": 0, "t": 0, "l": 0, "b": 0}, mapbox_style="open-street-map")

    return fig
