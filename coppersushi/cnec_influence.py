"""A selected CNEC's signed influence on each zone's price, drawn as rays from the element.

A ray is the row's shadow price times the zone's PTDF difference to the reference zone: zonal
sensitivity, never a power-flow path. Rays leave the element, arc north and land on each zone's
label point; they are not routed along grid branches. The look follows
wiki/assets/cnec-price-influence-map-preview.png: width and dot size scale with the size of
the contribution, colour says its sign.
"""

import math
from typing import NamedTuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from coppersushi import map_style
from coppersushi.data_model.cnec_price_map import MATCHED

ARC_POINTS = 24
BOW = 0.18  # Control point this fraction of the chord north of its midpoint: rays rise from the
# element and arc down onto their zones, and a ray due north stays straight
RAY_WIDTH = (1.2, 6.0)  # Thinnest and widest ray, by contribution size relative to the largest drawn
DOT_SIZE = (8, 22)
DOT_HALO_FACTOR = 1.8  # The line halo factor would swallow the neighbouring label
ORIGIN_SIZE = 7
NEUTRAL = "rgba(255,255,255,0.75)"  # The reference zone, and a zone the row leaves untouched
NEGLIGIBLE = 1e-9  # A contribution this small earns a neutral dot and no ray


class Overlay(NamedTuple):
    """The traces drawn over the price layer and the note that says what they are, and are not."""

    traces: list[go.Scattermapbox]
    note: str


def arc(
    origin: tuple[float, float],
    target: tuple[float, float],
    bow: float = BOW,
    points: int = ARC_POINTS,
) -> tuple[np.ndarray, np.ndarray]:
    """A quadratic Bézier from ``origin`` to ``target`` in longitude and latitude.

    The control point sits north of the chord's midpoint by ``bow`` of the chord's length,
    measured on the ground: longitude is scaled by the cosine of latitude, so a ray of a given
    length bows the same at Brussels as at Bucharest.
    """
    (x0, y0), (x1, y1) = origin, target
    ground = math.cos(math.radians((y0 + y1) / 2))
    length = math.hypot((x1 - x0) * ground, y1 - y0)
    control_x, control_y = (x0 + x1) / 2, (y0 + y1) / 2 + bow * length
    t = np.linspace(0.0, 1.0, points)

    def bezier(start: float, control: float, end: float) -> np.ndarray:
        return (1 - t) ** 2 * start + 2 * (1 - t) * t * control + t**2 * end

    return bezier(x0, control_x, x1), bezier(y0, control_y, y1)


def _sized(contributions: pd.Series, smallest: float, largest: float) -> pd.Series:
    """Linear in the contribution's size relative to the largest drawn."""
    scale = contributions.abs().max()
    share = contributions.abs() / scale if scale > 0 else contributions.abs()
    return smallest + (largest - smallest) * share


def _colour(contribution: float) -> str:
    if contribution > NEGLIGIBLE:
        return map_style.PRICE_UP
    if contribution < -NEGLIGIBLE:
        return map_style.PRICE_DOWN
    return NEUTRAL


def _rays(origin: tuple[float, float], zonal: pd.DataFrame) -> list[go.Scattermapbox]:
    """Every glow first, then every core, so no ray's halo lies over another's core."""
    influenced = zonal[zonal.contribution.abs() > NEGLIGIBLE]
    widths = _sized(influenced.contribution, *RAY_WIDTH)
    haloed = []
    for row, width in zip(influenced.itertuples(), widths):
        lon, lat = arc(origin, (row.x, row.y))
        core = go.Scattermapbox(
            name=f"{row.zone} ray",
            lon=lon,
            lat=lat,
            mode="lines",
            hoverinfo="skip",
            showlegend=False,
            line=dict(color=_colour(row.contribution), width=width),
        )
        haloed.append(map_style.haloed(core))
    return [glow for glow, _ in haloed] + [core for _, core in haloed]


def _dots(zonal: pd.DataFrame, reference: str) -> list[go.Scattermapbox]:
    """A dot on every drawn zone, sized and coloured by its contribution."""
    at_reference = zonal.zone.eq(reference)
    text = zonal.zone + " · " + np.where(
        at_reference,
        "reference zone",
        zonal.contribution.map(lambda value: f"{value:+,.2f} €/MWh") + f" relative to {reference}",
    )
    dots = go.Scattermapbox(
        name=f"contribution relative to {reference}",
        lon=zonal.x,
        lat=zonal.y,
        mode="markers",
        hoverinfo="text",
        text=text,
        marker=go.scattermapbox.Marker(
            color=[_colour(value) for value in zonal.contribution],
            size=_sized(zonal.contribution, *DOT_SIZE),
        ),
    )
    return map_style.haloed(dots, factor=DOT_HALO_FACTOR)


def overlay(selected: pd.Series, centres: pd.DataFrame, contribution: pd.DataFrame) -> Overlay:
    """The selected row's rays and zone dots over the price layer.

    ``selected`` is the row with its geometry, ``centres`` one label point per drawn zone.
    An unmapped selected row keeps its dots: its rays have nowhere to start.
    """
    zonal = contribution.merge(centres[["zone", "x", "y"]], on="zone", how="inner")
    reference = str(contribution.reference_zone.iloc[0])
    dots = _dots(zonal, reference)
    note = (
        f"Selected contribution relative to <b>{reference}</b>. "
        "Rays are zonal PTDF influence, not a power-flow path."
    )
    if selected.match_status != MATCHED:
        note += " The selected CNEC has no mapped geometry, so its rays cannot be anchored."
        return Overlay(dots, note)
    origin = ((selected.x0 + selected.x1) / 2, (selected.y0 + selected.y1) / 2)
    origin_dot = go.Scattermapbox(
        name="ray origin",
        lon=[origin[0]],
        lat=[origin[1]],
        mode="markers",
        hoverinfo="skip",
        marker=go.scattermapbox.Marker(color="white", size=ORIGIN_SIZE),
    )
    return Overlay(_rays(origin, zonal) + dots + map_style.haloed(origin_dot), note)
