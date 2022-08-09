import plotly.graph_objects as go
import pypsa


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
    index = 6
    snapshot = n.snapshots[index]
    marginal_prices = []
    for name, bus in n.buses.iterrows():
        marginal_price = n.buses_t.marginal_price.loc[snapshot][name]
        if -650 < marginal_price < 0:
            x, y = bus.x, bus.y
            node_x.append(x)
            node_y.append(y)
            marginal_prices.append(marginal_price)

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
    node_trace.marker.color = marginal_prices
    node_trace.text = marginal_prices

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
