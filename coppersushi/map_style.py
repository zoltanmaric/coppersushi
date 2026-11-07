"""Shared OPF map styling and the value scale used by the browser map."""
import plotly.graph_objects as go

BINDING = "#a72af5"
MUTED_BRANCH = "gray"
MAP_STYLE = "dark"
OPF_CAMERA = dict(center=dict(lat=53, lon=9), zoom=3.9, pitch=60)
VALUE_COLORSCALE = go.Choroplethmapbox(colorscale="tropic").colorscale
