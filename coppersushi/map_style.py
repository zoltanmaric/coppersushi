"""Shared visual language for Copper Sushi's geographic network views."""

import numpy as np
import plotly.graph_objects as go

BINDING = "#a72af5"
BACKGROUND_BRANCH = "#4a4a4a"
MUTED_BRANCH = "gray"
MAP_STYLE = "dark"
# One scale for every mapped value; purple is reserved for binding (wiki/sushi-2.md, Architecture 5)
VALUE_COLORSCALE = "tropic"
# A selected CNEC's signed influence on a zone's price: pink raises it, cyan lowers it
PRICE_UP = "#ff4fb8"
PRICE_DOWN = "#3fd0ff"
ZONE_FILL_OPACITY = 0.6
ZONE_BORDER = "rgba(255,255,255,0.55)"
ZONE_BORDER_WIDTH = 1.2
HALO_FACTOR = 3.0  # A translucent copy this much wider reads as a halo, not a bar
HALO_OPACITY = 0.3
LABEL_LAYERS = "symbol"  # Every label in a Mapbox style is a symbol layer


def haloed(
    core: go.Scattermapbox, factor: float = HALO_FACTOR, opacity: float = HALO_OPACITY
) -> list[go.Scattermapbox]:
    """``core`` over a wider, translucent copy of itself.

    Mapbox draws Plotly's lines with flat caps and its markers hard-edged; the copy
    underneath softens both into a glow.
    """
    glow = go.Scattermapbox(core)
    glow.update(name=f"{core.name} glow", opacity=opacity, hoverinfo="skip", showlegend=False)
    if core.line.width is not None:
        glow.line.width = core.line.width * factor
    if core.marker.size is not None:
        glow.marker.size = np.asarray(core.marker.size) * factor
    return [glow, core]


def without_labels(style: dict) -> dict:
    """A Mapbox style document with its own labels removed.

    Mapbox drops a label that collides with one it has already placed, and the dark
    style writes each country's name where that country's value wants to be. Without
    the basemap's symbol layers, the figure's text has the frame to itself.
    """
    return {
        **style,
        "layers": [layer for layer in style["layers"] if layer["type"] != LABEL_LAYERS],
    }
