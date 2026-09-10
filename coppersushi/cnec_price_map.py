"""Published zonal prices and market-binding CNECs in one Plotly map."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pandera.typing import DataFrame

from coppersushi.cnec_market import Snapshot
from coppersushi.data_model.cnec_price_map import CnecGeometries

PURPLE = "#b45cff"
NETWORK_GREY = "#5d6570"
POSITIVE = "#42d9f5"
NEGATIVE = "#ff9f43"
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


def _selected_row(placed: pd.DataFrame, contribution: pd.DataFrame) -> pd.Series:
    first = contribution.iloc[0]
    selected = placed[
        placed.eic.eq(first.eic)
        & placed.direction.eq(first.direction)
        & placed.cont_name.eq(first.cont_name)
    ]
    if len(selected) != 1:
        raise ValueError(f"contribution matched {len(selected)} active rows")
    return selected.iloc[0]


def _contribution_traces(
    placed: pd.DataFrame,
    centres: pd.DataFrame,
    contribution: pd.DataFrame,
) -> tuple[list[go.Scattermapbox], str]:
    """Signed zonal influence radiating from the selected element, never along grid edges."""
    selected = _selected_row(placed, contribution)
    zonal = contribution.merge(centres[["zone", "x", "y"]], on="zone", how="inner")
    reference = str(contribution.reference_zone.iloc[0])
    scale = zonal.contribution.abs().max() or 1.0
    colours = [POSITIVE if value >= 0 else NEGATIVE for value in zonal.contribution]
    sizes = 7 + 17 * zonal.contribution.abs() / scale
    markers = go.Scattermapbox(
        name=f"contribution relative to {reference}",
        lon=zonal.x,
        lat=zonal.y,
        mode="markers",
        hoverinfo="text",
        text=(
            zonal.zone + " · "
            + zonal.contribution.map(lambda value: f"{value:+,.2f} €/MWh")
            + f" relative to {reference}"
        ),
        marker=go.scattermapbox.Marker(color=colours, size=sizes, opacity=0.88),
    )
    traces = [markers]
    mapped = selected.match_status == MAPPED
    if mapped:
        origin_x = (selected.x0 + selected.x1) / 2
        origin_y = (selected.y0 + selected.y1) / 2
        for row in zonal[zonal.contribution.abs() > 1e-9].itertuples():
            traces.append(
                go.Scattermapbox(
                    name=f"{row.zone} contribution",
                    lon=[origin_x, row.x],
                    lat=[origin_y, row.y],
                    mode="lines",
                    hoverinfo="skip",
                    showlegend=False,
                    line=dict(
                        color=POSITIVE if row.contribution > 0 else NEGATIVE,
                        width=0.8 + 5.2 * abs(row.contribution) / scale,
                    ),
                    opacity=0.5,
                )
            )
        traces.append(
            go.Scattermapbox(
                name="selected CNEC",
                lon=[selected.x0, selected.x1],
                lat=[selected.y0, selected.y1],
                mode="lines+markers",
                hoverinfo="skip",
                line=dict(color=PURPLE, width=9),
                marker=go.scattermapbox.Marker(color=PURPLE, size=9),
                showlegend=False,
            )
        )
    note = (
        f"Selected contribution relative to <b>{reference}</b>. "
        "Rays are zonal PTDF influence, not a power-flow path."
    )
    if not mapped:
        note += " The selected CNEC has no mapped geometry, so its rays cannot be anchored."
    return traces, note


def figure(
    buses: pd.DataFrame,
    geometries: DataFrame[CnecGeometries],
    view: Snapshot,
    mapbox_token: str | None = None,
) -> go.Figure:
    """The base price layer plus every mapped physical row active in ``view.interval``."""
    priced_buses = _priced_buses(buses, view.prices)
    centres = _zone_centres(priced_buses)
    placed = _placed(view.constraints, geometries)
    mapped = placed.match_status.eq(MAPPED).sum()
    annotation = (
        f"<b>{mapped} of {len(placed)} active rows mapped</b><br>"
        "Purple means market-binding under contingency, not physically overloaded."
    )
    traces = _price_traces(priced_buses) + _constraint_traces(placed)
    if view.contribution is not None:
        contribution_traces, contribution_note = _contribution_traces(
            placed, centres, view.contribution
        )
        traces += contribution_traces
        annotation += "<br>" + contribution_note
    fig = go.Figure(traces)
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
