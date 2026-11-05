"""Published zonal prices and market-binding CNECs in one Plotly map."""

import math

import numpy as np
import pandas as pd
from pandera.typing import DataFrame
from coppersushi.data_model.cnec_attribution import CountryCaps
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.data_model.market import ZonalPrices
from coppersushi.data_model.jao import ActiveConstraints
import plotly.graph_objects as go

from coppersushi import cnec_influence, map_style, market
from coppersushi.cnec_market import Snapshot
from coppersushi.data_model.cnec_price_map import MATCHED, MappedCnecElements
from coppersushi.market_day import MARKET_TZ

POINT_TYPES = ("Transformer", "PST")
FRAME_ZOOM = 1.0  # Chosen against the rendered page, not derived: viewport aspect varies
LINE_WIDTH = 2.5
SELECTED_WIDTH = 4  # The selected row's branch, under the same halo as the rest
GLOW_FACTOR = 4.4  # Wider than map_style's default: a 2.5-px line wants an 11-px halo to read at all
END_SIZE = 6  # Mapbox caps Plotly's lines flat; a dot at each end rounds them. Only
# circles take the trace colour: every other symbol is the sprite's own grey icon.
TARGET_SIZE = 8
POINT_SIZE = 9


def _priced_zones(zones: DataFrame[BiddingZoneShapes], prices: DataFrame[ZonalPrices]) -> pd.DataFrame:
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
            **({"price": priced_zones.price.to_numpy()} if "price" in priced_zones else {}),
        }
    )


def _placed(constraints: DataFrame[ActiveConstraints], geometries: DataFrame[MappedCnecElements]) -> pd.DataFrame:
    return constraints.merge(
        geometries, on=["eic", "tso", "name"], how="left", validate="many_to_one"
    )


def _hover(rows: pd.DataFrame) -> pd.Series:
    if rows.empty:
        return pd.Series(index=rows.index, dtype="str")
    ram = rows.ram.map(lambda value: "n/a" if pd.isna(value) else f"{value:,.0f} MW")
    capacity = rows.capacity.map(lambda value: "n/a" if pd.isna(value) else f"{value:,.0f} MW")
    contingency = rows.cont_name.fillna("Base case (no contingency)")
    return (
        "<b>" + rows["name"] + "</b><br>"
        + "Binding under: " + contingency + "<br>"
        + "Direction: " + rows.direction + "<br>"
        + "RAM: " + ram + "<br>"
        + "Capacity: " + capacity + "<br>"
        + "Shadow price: " + rows.shadow_price.map(lambda value: f"{value:,.2f} €/MWh")
    )


def _line_coordinates(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    gap = np.full(len(rows), np.nan)
    lon = np.stack([rows.x0.to_numpy(float), rows.x1.to_numpy(float), gap], axis=1).ravel()
    lat = np.stack([rows.y0.to_numpy(float), rows.y1.to_numpy(float), gap], axis=1).ravel()
    return lon, lat


def _bearing(x0: pd.Series, y0: pd.Series, x1: pd.Series, y1: pd.Series) -> pd.Series:
    """Bearing of each drawn segment in degrees clockwise from north.

    Measured in the Web Mercator plane the map draws in, so a marker rotated by it lies
    along the straight line between the endpoints at any latitude.
    """
    dy = np.degrees(
        np.log(np.tan(np.radians(45 + y1 / 2))) - np.log(np.tan(np.radians(45 + y0 / 2)))
    )
    return np.degrees(np.arctan2(x1 - x0, dy)) % 360


def _fill_anchor(basemap: str | dict) -> str | None:
    """The basemap layer the price fill goes under.

    Plotly's default puts a choropleth under the basemap's first symbol layer; the label-free
    basemap has none, so the fill would land above the labels and markers drawn after it and
    tint them. Under the topmost basemap layer, borders and roads also stay legible on it.
    """
    return basemap["layers"][-1]["id"] if isinstance(basemap, dict) else None


def _price_traces(
    priced_zones: pd.DataFrame, fill_anchor: str | None
) -> tuple[go.Choroplethmapbox, go.Scattermapbox]:
    """The price fill and, apart, the labels: the figure draws those last, over every dot and ray."""
    labels_at = _zone_centres(priced_zones)
    fill = go.Choroplethmapbox(
        name="published day-ahead price",
        geojson={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": zone,
                    "properties": {},
                    "geometry": geometry.__geo_interface__,
                }
                for zone, geometry in zip(priced_zones.zone, priced_zones.geometry)
            ],
        },
        locations=priced_zones.zone,
        z=priced_zones.price,
        colorscale=map_style.VALUE_COLORSCALE,
        marker_opacity=map_style.ZONE_FILL_OPACITY,
        marker_line_color=map_style.ZONE_BORDER,
        marker_line_width=map_style.ZONE_BORDER_WIDTH,
        below=fill_anchor,
        hoverinfo="skip",  # The label already says what a hover would
        colorbar=go.choroplethmapbox.ColorBar(
            title=dict(text="Day-ahead price [€/MWh]", side="top"),
            orientation="h",
            y=-0.02,
            yanchor="top",
            thickness=14,
        ),
    )
    names = labels_at.zone.map(market.ZONE_NAMES).fillna(labels_at.zone)
    labels = go.Scattermapbox(
        name="zone prices",
        lon=labels_at.x,
        lat=labels_at.y,
        mode="text",
        hoverinfo="text",
        text=names + "<br>" + labels_at.price.map(lambda value: f"€{value:,.2f}"),
        hovertext=names + " · " + labels_at.price.map(lambda value: f"{value:,.2f} €/MWh"),
        textfont=dict(color="white", size=14),
        showlegend=False,
    )
    return fill, labels


def _hover_targets(rows: pd.DataFrame, directed: bool) -> pd.DataFrame:
    """One reachable marker per plotted location and sense, carrying every active row there.

    A row's sense is the way it binds: its geometry runs from the publishing TSO's own
    `substation_from`, and that TSO's DIRECT runs the same way.
    """
    bearing = _bearing(rows.x0, rows.y0, rows.x1, rows.y1)
    angle = np.where(rows.direction.eq("DIRECT"), bearing, (bearing + 180) % 360)
    targets = rows.assign(
        target_x=(rows.x0 + rows.x1) / 2,
        target_y=(rows.y0 + rows.y1) / 2,
        angle=angle if directed else 0.0,
        hover=_hover(rows),
    )
    return (
        targets.groupby(["target_x", "target_y", "angle"], as_index=False, dropna=False)
        .agg(
            hover=("hover", lambda values: "<br><br>".join(values)),
            source_ids=("source_id", lambda values: ",".join(map(str, values))),
        )
    )


def _constraint_traces(
    placed: pd.DataFrame, selected: pd.Series | None = None
) -> list[go.Scattermapbox]:
    """Draw each matched branch once and aggregate all binding rows at its hover target.

    The domain can publish both directions and several contingencies for an element. More
    than one EIC can also resolve to one PyPSA branch. Those are distinct market rows but
    not distinct lines on the map, so the line and its marker have different grains.

    A line's hover target is a triangle pointing the way its rows bind; a transformer's or
    PST's is a square.
    """
    mapped = placed[placed.match_status.eq(MATCHED)]
    line_rows = mapped[~mapped.element_type.isin(POINT_TYPES)]
    unique_lines = line_rows.drop_duplicates("branch_id")
    lon, lat = _line_coordinates(unique_lines)

    def line(name: str, width: float, lon: np.ndarray | list[float], lat: np.ndarray | list[float]) -> list[go.Scattermapbox]:
        core = go.Scattermapbox(
            name=name,
            lon=lon,
            lat=lat,
            mode="lines",
            hoverinfo="none",
            line=dict(color=map_style.BINDING, width=width),
        )
        return map_style.haloed(core, factor=GLOW_FACTOR)

    highlighted = []
    if selected is not None and selected.match_status == MATCHED:
        highlighted = line(
            "selected CNEC", SELECTED_WIDTH, [selected.x0, selected.x1], [selected.y0, selected.y1]
        )

    ends = go.Scattermapbox(
        name="binding line ends",
        lon=np.concatenate([unique_lines.x0, unique_lines.x1]),
        lat=np.concatenate([unique_lines.y0, unique_lines.y1]),
        mode="markers",
        hoverinfo="skip",
        marker=go.scattermapbox.Marker(color=map_style.BINDING, size=END_SIZE, symbol="circle"),
    )

    def markers(rows: pd.DataFrame, name: str, symbol: str, size: int, directed: bool) -> go.Scattermapbox:
        targets = _hover_targets(rows, directed)
        return go.Scattermapbox(
            name=name,
            lon=targets.target_x,
            lat=targets.target_y,
            mode="markers",
            hoverinfo="text",
            text=targets.hover,
            customdata=targets[["source_ids"]].to_numpy(),
            marker=go.scattermapbox.Marker(
                color=map_style.BINDING, size=size, symbol=symbol, angle=targets.angle
            ),
        )

    point_rows = mapped[mapped.element_type.isin(POINT_TYPES)]
    return [
        *line("market-binding CNECs", LINE_WIDTH, lon, lat),
        *highlighted,
        ends,
        _line_hit_targets(line_rows),
        markers(line_rows, "binding rows", "triangle", TARGET_SIZE, directed=True),
        markers(point_rows, "binding transformers and PSTs", "square", POINT_SIZE, directed=False),
    ]


def _selected(placed: pd.DataFrame, source_id: int | None) -> pd.Series | None:
    if source_id is None:
        return None
    rows = placed[placed.source_id.eq(source_id)]
    return rows.iloc[0] if len(rows) == 1 else None


def _line_hit_targets(rows: pd.DataFrame) -> go.Scattermapbox:
    """Continuous-looking hit areas along line interiors, carrying all source row IDs."""
    lon, lat, data, hover = [], [], [], []
    for _, group in rows.groupby(["x0", "y0", "x1", "y1"], dropna=True):
        row = group.iloc[0]
        ids = ",".join(group.source_id.astype(str))
        text = "<br><br>".join(_hover(group))
        for t in np.linspace(0, 1, 41):
            lon.append(row.x0 + t * (row.x1 - row.x0))
            lat.append(row.y0 + t * (row.y1 - row.y0))
            data.append([ids])
            hover.append(text)
    return go.Scattermapbox(name="select line", lon=lon, lat=lat, mode="markers",
        marker=dict(size=16, color="rgba(128,80,255,0.01)"), customdata=data,
        text=hover, hoverinfo="text", showlegend=False)


def _cap_traces(zones: DataFrame[BiddingZoneShapes], caps: DataFrame[CountryCaps], selected_id: int | None) -> list:
    traces: list[go.Scattermapbox] = []
    if caps.empty:
        return traces
    polish = zones[zones.zone.eq("PL")]
    if len(polish) != 1:
        return traces
    geometry = polish.geometry.iloc[0]
    polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
    lon, lat = [], []
    for polygon in polygons:
        for ring in [polygon.exterior, *polygon.interiors]:
            # Include gaps between rings so islands do not gain invented connecting borders.
            n = max(20, int(ring.length * 20))
            points = [ring.interpolate(t, normalized=True) for t in np.linspace(0, 1, n)]
            lon.extend([p.x for p in points] + [None])
            lat.extend([p.y for p in points] + [None])
    row = caps.iloc[0]
    hover = (f"{row['name']}<br>Net {row.direction} limit: {row.capacity:,.0f} MW<br>"
             f"Cap shadow price: {row.shadow_price:,.2f} €/MWh")
    outline = go.Scattermapbox(name="binding country cap", lon=lon,
        lat=lat, mode="lines", line=dict(color=map_style.BINDING,
        width=SELECTED_WIDTH if selected_id == row.source_id else LINE_WIDTH), hoverinfo="skip")
    traces += map_style.haloed(outline)
    traces.append(go.Scattermapbox(name="select country cap", lon=outline.lon, lat=outline.lat,
        mode="markers", marker=dict(size=14, color="rgba(128,80,255,0.01)"),
        customdata=[[str(row.source_id)]] * len(lon), text=[hover] * len(lon), hoverinfo="text"))
    for trace in traces:
        trace.meta = "country-cap"
    return traces


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
    zones: DataFrame[BiddingZoneShapes],
    geometries: DataFrame[MappedCnecElements],
    view: Snapshot,
    mapbox_token: str | None = None,
    basemap: str | dict = map_style.MAP_STYLE,
) -> go.Figure:
    """The zonal price choropleth plus every mapped physical row active in ``view.interval``.

    ``basemap`` is a Plotly preset name or a Mapbox style document (see ``map_style.without_labels``).
    """
    priced_zones = _priced_zones(zones, view.prices)
    placed = _placed(view.constraints, geometries)
    mapped = placed.match_status.eq(MATCHED).sum()
    annotation = (
        f"<b>{mapped} of {len(placed)} active rows mapped</b><br>"
        "Purple means market-binding under contingency, not physically overloaded."
    )
    fill, labels = _price_traces(priced_zones, _fill_anchor(basemap))
    selected = _selected(placed, view.selected_id)
    centres = _zone_centres(priced_zones)
    if view.selected_id in view.caps.source_id.values:
        anchor = centres[centres.zone.eq("PL")]
        if len(anchor) == 1:
            point = anchor.iloc[0]
            selected = pd.Series(dict(x0=point.x, y0=point.y, x1=point.x, y1=point.y, match_status=MATCHED))
    physical_selection = _selected(placed, view.selected_id)
    traces = [fill, *_constraint_traces(placed, physical_selection),
              *_cap_traces(zones, view.caps, view.selected_id)]
    annotation += "<br>Country-spread attribution: physical CNECs and country caps."
    if view.selected_id is not None:
        annotation += f"<br>Selected row {view.selected_id} · Reference: {view.reference or 'unavailable'}"
    if view.note:
        annotation += "<br>" + view.note
    if selected is not None and view.contribution is not None:
        assert view.reference is not None
        effects = view.contribution[view.contribution.zone.ne(view.reference)]
        if view.selected_id in view.caps.source_id.values:
            annotation += f"<br><b>Other Core zones: {effects.contribution.iloc[0]:+,.2f} €/MWh relative to PL</b>"
        influence = cnec_influence.overlay(selected, centres, view.contribution)
        traces += influence.traces
        annotation += "<br>" + influence.note
    traces.append(labels)  # Last, so no dot or ray lands on a price
    fig = go.Figure(traces)
    fig.layout = map_layout(zones, view.interval, mapbox_token, basemap, annotation)
    return fig


def price_figure(zones: DataFrame[BiddingZoneShapes], prices: DataFrame[ZonalPrices],
                 interval: pd.Timestamp, token: str, basemap: str | dict) -> go.Figure:
    """Price layer independent of constraint and attribution availability."""
    priced = _priced_zones(zones, prices)
    return go.Figure(_price_traces(priced, _fill_anchor(basemap)),
                     layout=map_layout(zones, interval, token, basemap, ""))


def constraint_figure(zones: DataFrame[BiddingZoneShapes], constraints: DataFrame[ActiveConstraints],
                      geometries: DataFrame[MappedCnecElements],
                      interval: pd.Timestamp, selected_id: int | None, token: str,
                      basemap: str | dict) -> go.Figure:
    """Binding lines and interfaces, available without prices or attribution inputs."""
    placed = _placed(constraints, geometries)
    annotation = (f"<b>{placed.match_status.eq(MATCHED).sum()} of {len(placed)} active rows mapped</b><br>"
                  "Purple means market-binding under contingency, not physically overloaded.")
    traces = _constraint_traces(placed, _selected(placed, selected_id))
    return go.Figure(traces, layout=map_layout(zones, interval, token, basemap, annotation))


def map_layout(zones: DataFrame[BiddingZoneShapes], interval: pd.Timestamp, token: str | None,
               basemap: str | dict, annotation: str) -> go.Layout:
    """Shared stable camera and labels for independently arriving map layers."""
    return go.Layout(
        hovermode="closest",
        margin=dict(r=0, t=0, l=0, b=0),
        mapbox_style=basemap,
        mapbox_accesstoken=token,
        mapbox=_view(zones),
        uirevision="cnec-camera",
        showlegend=False,
        annotations=[
            go.layout.Annotation(
                text=annotation, xref="paper", yref="paper", x=0.99, y=0.01,
                xanchor="right", yanchor="bottom", align="right", showarrow=False,
                bgcolor="rgba(0,0,0,0.65)", bordercolor=map_style.BINDING, borderpad=7,
            ),
            go.layout.Annotation(
                text=f"<b>{interval.tz_convert(MARKET_TZ).strftime('%a %d %b %Y · %H:%M %Z')}</b>",
                xref="paper", yref="paper", x=0.01, y=0.99, xanchor="left", yanchor="top",
                showarrow=False, font=dict(size=15, color="white"),
                bgcolor="rgba(0,0,0,0.65)", borderpad=6,
            ),
        ],
    )
