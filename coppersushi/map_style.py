"""Shared visual language for Copper Sushi's geographic network views."""

BINDING = "#a72af5"
BACKGROUND_BRANCH = "#4a4a4a"
MUTED_BRANCH = "gray"
MAP_STYLE = "dark"
LEGEND_BACKGROUND = "rgba(0,0,0,0.6)"
NETWORK_VALUE_COLORSCALE = "tropic"
PRICE_COLORSCALE = "RdYlBu_r"  # Cheap blue, dear red, as price maps are read
ZONE_FILL_OPACITY = 0.6
ZONE_BORDER = "rgba(255,255,255,0.55)"
ZONE_BORDER_WIDTH = 1.2
LABEL_LAYERS = "symbol"  # Every label in a Mapbox style is a symbol layer


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
