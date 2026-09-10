"""Published zonal prices and market-binding CNECs in one Plotly map."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pandera.typing import DataFrame

from coppersushi.cnec_market import Snapshot
from coppersushi.data_model.cnec_price_map import CnecGeometries

PURPLE = "#b45cff"
NETWORK_GREY = "#5d6570"
POINT_TYPES = ("Transformer", "PST")
MAPPED = "matched"


def _priced_buses(buses: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    priced = buses.reset_index(names="bus").merge(
        prices[["zone", "price"]], left_on="country", right_on="zone", how="inner"
    )
    if priced.empty:
        raise ValueError("none of the priced zones has a bus on the map")
    return priced


def _zone_centres(priced_buses: pd.DataFrame) -> pd.DataFrame:
    """One restrained label position per zone, derived from the shown network nodes."""
    return priced_buses.groupby("zone", as_index=False).agg(
        x=("x", "median"), y=("y", "median"), price=("price", "first")
    )


def _placed(constraints: pd.DataFrame, geometries: DataFrame[CnecGeometries]) -> pd.DataFrame:
    return constraints.merge(geometries, on="eic", how="left", validate="many_to_one")


def _hover(rows: pd.DataFrame) -> pd.Series:
    ram = rows.ram.map(lambda value: "n/a" if pd.isna(value) else f"{value:,.0f} MW")
    return (
        "<b>" + rows["name"] + "</b><br>"
        + "Binding under: " + rows.cont_name + "<br>"
        + "Direction: " + rows.direction + "<br>"
        + "RAM: " + ram + "<br>"
        + "Shadow price: " + rows.shadow_price.map(lambda value: f"{value:,.2f} €/MWh")
    )


def _line_coordinates(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    gap = np.full(len(rows), np.nan)
    lon = np.stack([rows.x0.to_numpy(float), rows.x1.to_numpy(float), gap], axis=1).ravel()
    lat = np.stack([rows.y0.to_numpy(float), rows.y1.to_numpy(float), gap], axis=1).ravel()
    return lon, lat


def _price_traces(priced_buses: pd.DataFrame) -> list[go.Scattermapbox]:
    centres = _zone_centres(priced_buses)
    nodes = go.Scattermapbox(
        name="published day-ahead price",
        lon=priced_buses.x,
        lat=priced_buses.y,
        mode="markers",
        hoverinfo="text",
        text=(
            priced_buses.zone + " · " + priced_buses.price.map(lambda value: f"{value:,.2f} €/MWh")
        ),
        marker=go.scattermapbox.Marker(
            color=priced_buses.price,
            colorscale="Turbo",
            size=7,
            opacity=0.72,
            showscale=True,
            colorbar=go.scattermapbox.marker.ColorBar(
                title=dict(text="Day-ahead price [€/MWh]", side="top"),
                orientation="h",
                y=-0.02,
                yanchor="top",
                thickness=14,
            ),
        ),
    )
    labels = go.Scattermapbox(
        name="zone prices",
        lon=centres.x,
        lat=centres.y,
        mode="text",
        hoverinfo="skip",
        text=centres.zone + "<br>" + centres.price.map(lambda value: f"{value:,.2f} €"),
        textfont=dict(color="white", size=12),
        showlegend=False,
    )
    return [nodes, labels]


def _constraint_traces(placed: pd.DataFrame) -> list[go.Scattermapbox]:
    mapped = placed[placed.match_status.eq(MAPPED)]
    line_rows = mapped[~mapped.element_type.isin(POINT_TYPES)]
    unique_lines = line_rows.drop_duplicates("eic")
    lon, lat = _line_coordinates(unique_lines)
    lines = go.Scattermapbox(
        name="market-binding CNECs",
        lon=lon,
        lat=lat,
        mode="lines",
        hoverinfo="none",
        line=dict(color=PURPLE, width=5),
    )

    def markers(rows: pd.DataFrame, name: str, symbol: str, size: int) -> go.Scattermapbox:
        return go.Scattermapbox(
            name=name,
            lon=(rows.x0 + rows.x1) / 2,
            lat=(rows.y0 + rows.y1) / 2,
            mode="markers",
            hoverinfo="text",
            text=_hover(rows),
            customdata=rows[["eic", "direction", "cont_name"]].to_numpy(),
            marker=go.scattermapbox.Marker(color=PURPLE, size=size, symbol=symbol),
        )

    point_rows = mapped[mapped.element_type.isin(POINT_TYPES)]
    return [
        lines,
        markers(line_rows, "binding rows", "circle", 8),
        markers(point_rows, "binding transformers and PSTs", "square", 14),
    ]


def figure(
    buses: pd.DataFrame,
    geometries: DataFrame[CnecGeometries],
    view: Snapshot,
    mapbox_token: str | None = None,
) -> go.Figure:
    """The base price layer plus every mapped physical row active in ``view.interval``."""
    priced_buses = _priced_buses(buses, view.prices)
    placed = _placed(view.constraints, geometries)
    mapped = placed.match_status.eq(MAPPED).sum()
    annotation = (
        f"<b>{mapped} of {len(placed)} active rows mapped</b><br>"
        "Purple means market-binding under contingency, not physically overloaded."
    )
    fig = go.Figure(_price_traces(priced_buses) + _constraint_traces(placed))
    fig.update_layout(
        hovermode="closest",
        margin=dict(r=0, t=0, l=0, b=0),
        mapbox_style="dark",
        mapbox_accesstoken=mapbox_token,
        uirevision=True,
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(0,0,0,0.6)"),
        annotations=[
            go.layout.Annotation(
                text=annotation,
                xref="paper",
                yref="paper",
                x=0.99,
                y=0.01,
                xanchor="right",
                yanchor="bottom",
                align="right",
                showarrow=False,
                bgcolor="rgba(0,0,0,0.65)",
                bordercolor=PURPLE,
                borderpad=7,
            )
        ],
    )
    return fig
