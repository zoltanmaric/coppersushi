"""Published zonal prices and market-binding CNECs in one Plotly map."""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from pandera.typing import DataFrame

from coppersushi import map_style
from coppersushi.cnec_market import Snapshot
from coppersushi.data_model.cnec_price_map import MappedCnecElements

POSITIVE = "#42d9f5"
NEGATIVE = "#ff9f43"
POINT_TYPES = ("Transformer", "PST")
MAPPED = "matched"
FRAME_ZOOM = 1.0  # Chosen against the rendered page, not derived: viewport aspect varies


def _priced_zones(zones: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    priced = zones[["zone", "geometry"]].merge(
        prices[["zone", "price"]], on="zone", how="inner", validate="one_to_one"
    )
    if priced.empty:
        raise ValueError("none of the priced zones has geometry on the map")
    return priced


def _zone_centres(priced_zones: pd.DataFrame) -> pd.DataFrame:
    """One label position per zone, guaranteed to fall inside the zone's own polygon."""
    points = [geometry.representative_point() for geometry in priced_zones.geometry]
    return pd.DataFrame(
        {
            "zone": priced_zones.zone.to_numpy(),
            "x": [point.x for point in points],
            "y": [point.y for point in points],
            "price": priced_zones.price.to_numpy(),
        }
    )


def _placed(constraints: pd.DataFrame, geometries: DataFrame[MappedCnecElements]) -> pd.DataFrame:
    return constraints.merge(geometries, on="eic", how="left", validate="many_to_one")


def _hover(rows: pd.DataFrame) -> pd.Series:
    ram = rows.ram.map(lambda value: "n/a" if pd.isna(value) else f"{value:,.0f} MW")
    contingency = rows.cont_name.fillna("Base case (no contingency)")
    return (
        "<b>" + rows["name"] + "</b><br>"
        + "Binding under: " + contingency + "<br>"
        + "Direction: " + rows.direction + "<br>"
        + "RAM: " + ram + "<br>"
        + "Shadow price: " + rows.shadow_price.map(lambda value: f"{value:,.2f} €/MWh")
    )


def _line_coordinates(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    gap = np.full(len(rows), np.nan)
    lon = np.stack([rows.x0.to_numpy(float), rows.x1.to_numpy(float), gap], axis=1).ravel()
    lat = np.stack([rows.y0.to_numpy(float), rows.y1.to_numpy(float), gap], axis=1).ravel()
    return lon, lat


def _price_traces(priced_zones: pd.DataFrame) -> list[go.Choroplethmapbox | go.Scattermapbox]:
    labels_at = _zone_centres(priced_zones)
    fill = go.Choroplethmapbox(
        name="published day-ahead price",
        geojson={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": row.zone,
                    "properties": {},
                    "geometry": row.geometry.__geo_interface__,
                }
                for row in priced_zones.itertuples()
            ],
        },
        locations=priced_zones.zone,
        z=priced_zones.price,
        colorscale=map_style.NETWORK_VALUE_COLORSCALE,
        marker_opacity=map_style.ZONE_FILL_OPACITY,
        marker_line_color=map_style.ZONE_BORDER,
        marker_line_width=map_style.ZONE_BORDER_WIDTH,
        hoverinfo="text",
        text=(
            priced_zones.zone + " · " + priced_zones.price.map(lambda value: f"{value:,.2f} €/MWh")
        ),
        colorbar=go.choroplethmapbox.ColorBar(
            title=dict(text="Day-ahead price [€/MWh]", side="top"),
            orientation="h",
            y=-0.02,
            yanchor="top",
            thickness=14,
        ),
    )
    labels = go.Scattermapbox(
        name="zone prices",
        lon=labels_at.x,
        lat=labels_at.y,
        mode="text",
        hoverinfo="skip",
        text=labels_at.zone + "<br>" + labels_at.price.map(lambda value: f"{value:,.0f} €"),
        textfont=dict(color="white", size=13),
        showlegend=False,
    )
    return [fill, labels]


def _hover_targets(rows: pd.DataFrame) -> pd.DataFrame:
    """One reachable marker per plotted location, carrying every active row there."""
    targets = rows.assign(
        target_x=(rows.x0 + rows.x1) / 2,
        target_y=(rows.y0 + rows.y1) / 2,
        hover=_hover(rows),
    )
    return (
        targets.groupby(["target_x", "target_y"], as_index=False, dropna=False)
        .agg(
            hover=("hover", lambda values: "<br><br>".join(values)),
            source_ids=("source_id", lambda values: ",".join(map(str, values))),
        )
    )


def _constraint_traces(placed: pd.DataFrame) -> list[go.Scattermapbox]:
    """Draw each matched branch once and aggregate all binding rows at its hover target.

    The domain can publish both directions and several contingencies for an element. More
    than one EIC can also resolve to one PyPSA branch. Those are distinct market rows but
    not distinct lines on the map, so the line and its marker have different grains.
    """
    mapped = placed[placed.match_status.eq(MAPPED)]
    line_rows = mapped[~mapped.element_type.isin(POINT_TYPES)]
    unique_lines = line_rows.drop_duplicates("branch_id")
    lon, lat = _line_coordinates(unique_lines)
    lines = go.Scattermapbox(
        name="market-binding CNECs",
        lon=lon,
        lat=lat,
        mode="lines",
        hoverinfo="none",
        line=dict(color=map_style.BINDING, width=5),
    )

    def markers(rows: pd.DataFrame, name: str, symbol: str, size: int) -> go.Scattermapbox:
        targets = _hover_targets(rows)
        return go.Scattermapbox(
            name=name,
            lon=targets.target_x,
            lat=targets.target_y,
            mode="markers",
            hoverinfo="text",
            text=targets.hover,
            customdata=targets[["source_ids"]].to_numpy(),
            marker=go.scattermapbox.Marker(color=map_style.BINDING, size=size, symbol=symbol),
        )

    point_rows = mapped[mapped.element_type.isin(POINT_TYPES)]
    return [
        lines,
        markers(line_rows, "binding rows", "circle", 8),
        markers(point_rows, "binding transformers and PSTs", "square", 14),
    ]


def _selected_row(placed: pd.DataFrame, contribution: pd.DataFrame) -> pd.Series:
    first = contribution.iloc[0]
    selected = placed[placed.source_id.eq(first.source_id)]
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
                line=dict(color=map_style.BINDING, width=9),
                marker=go.scattermapbox.Marker(color=map_style.BINDING, size=9),
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


def _view(priced_zones: pd.DataFrame) -> dict:
    """Centre and zoom that frame the zones being drawn.

    A mapbox subplot does not fit itself to its traces, so without this the map opens on
    the default null island. One zoom level per halving of the drawn span, plus the
    constant that fills a wide viewport with Core rather than with the Atlantic.
    """
    bounds = [zone.bounds for zone in priced_zones.geometry]
    west, south = min(b[0] for b in bounds), min(b[1] for b in bounds)
    east, north = max(b[2] for b in bounds), max(b[3] for b in bounds)
    span = max(east - west, north - south)
    return dict(
        center=go.layout.mapbox.Center(lat=(south + north) / 2, lon=(west + east) / 2),
        zoom=math.log2(360 / span) + FRAME_ZOOM,
    )


def figure(
    zones: pd.DataFrame,
    geometries: DataFrame[MappedCnecElements],
    view: Snapshot,
    mapbox_token: str | None = None,
    basemap: str | dict = map_style.MAP_STYLE,
) -> go.Figure:
    """The zonal price choropleth plus every mapped physical row active in ``view.interval``.

    ``basemap`` is a Plotly preset name or a Mapbox style document (see ``map_style.without_labels``).
    """
    priced_zones = _priced_zones(zones, view.prices)
    centres = _zone_centres(priced_zones)
    placed = _placed(view.constraints, geometries)
    mapped = placed.match_status.eq(MAPPED).sum()
    annotation = (
        f"<b>{mapped} of {len(placed)} active rows mapped</b><br>"
        "Purple means market-binding under contingency, not physically overloaded."
    )
    traces = _price_traces(priced_zones) + _constraint_traces(placed)
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
        mapbox_style=basemap,
        mapbox_accesstoken=mapbox_token,
        mapbox=_view(priced_zones),
        uirevision=True,
        legend=dict(x=0.01, y=0.99, bgcolor=map_style.LEGEND_BACKGROUND),
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
                bordercolor=map_style.BINDING,
                borderpad=7,
            )
        ],
    )
    return fig
