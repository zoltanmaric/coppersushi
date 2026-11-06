"""Published zonal prices and market-binding CNECs in one Plotly map."""

import math

import numpy as np
import pandas as pd
from shapely.geometry import LinearRing, MultiPolygon, Polygon
from pandera.typing import DataFrame
from coppersushi.data_model.cnec_attribution import CountryCaps
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.data_model.market import ZonalPrices
from coppersushi.data_model.jao import ActiveConstraints
import plotly.graph_objects as go

from coppersushi import cnec_influence, map_style, market
from coppersushi.country_outline import country_rings as _country_rings
from coppersushi.cnec_market import Snapshot, daily_price_range
from coppersushi.data_model.cnec_price_map import MATCHED, MappedCnecElements

COUNTRY_CHANNEL_HALF_WIDTH_M = 500  # Close inland-water channels up to 1 km wide in the display outline.

POINT_TYPES = ("Transformer", "PST")
FRAME_ZOOM = 1.0  # Chosen against the rendered page, not derived: viewport aspect varies
LINE_WIDTH = 2.5
SELECTED_WIDTH = 4  # The selected row's branch, under the same halo as the rest
END_SIZE = 6  # Mapbox caps Plotly's lines flat; a dot at each end rounds them. Only
# circles take the trace colour: every other symbol is the sprite's own grey icon.
TARGET_SIZE = 8
POINT_SIZE = 10  # Owned sprite pixels at native size (Plotly scales icons by size / 10).


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
    priced_zones: pd.DataFrame, fill_anchor: str | None, price_range: tuple[float, float]
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
                    "geometry": MultiPolygon([Polygon(ring) for ring in _country_rings(geometry)]).__geo_interface__,
                }
                for zone, geometry in zip(priced_zones.zone, priced_zones.geometry)
            ],
        },
        locations=priced_zones.zone,
        z=priced_zones.price,
        zmin=price_range[0], zmax=price_range[1], zauto=False,
        colorscale=map_style.VALUE_COLORSCALE,
        marker_opacity=map_style.ZONE_FILL_OPACITY,
        marker_line_color=map_style.ZONE_BORDER,
        marker_line_width=map_style.ZONE_BORDER_WIDTH,
        below=fill_anchor,
        hoverinfo="skip",  # The label already says what a hover would
        showscale=False,
    )
    names = labels_at.zone.map(market.ZONE_NAMES).fillna(labels_at.zone)
    labels = go.Scattermapbox(
        name="zone prices",
        lon=labels_at.x,
        lat=labels_at.y,
        mode="text",
        customdata=[["zone", zone] for zone in labels_at.zone],
        hoverinfo="none",
        text=names + "<br>" + labels_at.price.map(lambda value: f"€{value:,.2f}"),
        marker=dict(symbol="circle"),
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
    PST's is a map-owned pair of rings, independent of decorative selection effects.
    """
    mapped = placed[placed.match_status.eq(MATCHED)]
    line_rows = mapped[~mapped.element_type.isin(POINT_TYPES)]
    unique_lines = line_rows.drop_duplicates("branch_id")
    lon, lat = _line_coordinates(unique_lines)

    def line(name: str, width: float, lon: np.ndarray | list[float], lat: np.ndarray | list[float]) -> list[go.Scattermapbox]:
        core = go.Scattermapbox(
            name=name,
            lon=list(lon),
            lat=list(lat),
            mode="lines",
            hoverinfo="none",
            line=dict(color=map_style.BINDING, width=width),
        )
        return [core]

    highlighted = []
    if selected is not None and selected.match_status == MATCHED:
        highlighted = line(
            "selected CNEC", SELECTED_WIDTH, [selected.x0, selected.x1], [selected.y0, selected.y1]
        )
        if selected.element_type in POINT_TYPES:
            highlighted = [go.Scattermapbox(name="selected CNEC", mode="markers",
                lon=[(selected.x0 + selected.x1) / 2], lat=[(selected.y0 + selected.y1) / 2],
                marker=dict(symbol="transformer-selected", size=POINT_SIZE, angle=0, allowoverlap=True),
                hoverinfo="skip", meta={"role": "binding-symbol", "effect": "transformer"})]
        else:
            highlighted[0].meta = {"effect": "line"}

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
            meta={"role": "binding-symbol"},
            lon=targets.target_x.to_list(),
            lat=targets.target_y.to_list(),
            mode="markers",
            hoverinfo="text",
            hoverlabel=map_style.BINDING_HOVERLABEL,
            text=targets.hover,
            customdata=targets[["source_ids"]].to_numpy(),
            marker=go.scattermapbox.Marker(
                color=map_style.BINDING, size=size, symbol=symbol, angle=targets.angle.to_list() if directed else 0,
                opacity=1, allowoverlap=True
            ),
        )

    point_rows = mapped[mapped.element_type.isin(POINT_TYPES)]
    branches = map_style.haloed(line("market-binding CNECs", LINE_WIDTH, lon, lat)[0])
    branches[0].line.color = map_style.BINDING_LIGHT
    branches[-1].meta = {"ambient": True}
    return [
        *branches,
        ends,
        _line_hit_targets(line_rows),
        markers(line_rows, "binding rows", "triangle", TARGET_SIZE, directed=True),
        markers(point_rows, "binding transformers and PSTs", "transformer", POINT_SIZE, directed=False),
        *highlighted,
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
        text=hover, hoverinfo="text", hoverlabel=map_style.BINDING_HOVERLABEL, showlegend=False)



def _cap_traces(zones: DataFrame[BiddingZoneShapes], caps: DataFrame[CountryCaps], selected_id: int | None) -> list:
    traces: list[go.Scattermapbox] = []
    if caps.empty:
        return traces
    polish = zones[zones.zone.eq("PL")]
    if len(polish) != 1:
        return traces
    geometry = polish.geometry.iloc[0]
    lon, lat = [], []
    for ring in _country_rings(geometry):
        # Include gaps between islands so no connecting border or click target is invented.
        # Preserve every coastline corner; densify long edges only for reachable click targets.
        points = list(ring.segmentize(0.05).coords)
        lon.extend([x for x, _ in points] + [None])
        lat.extend([y for _, y in points] + [None])
    row = caps.iloc[0]
    hover = (f"{row['name']}<br>Net {row.direction} limit: {row.capacity:,.0f} MW<br>"
             f"Cap shadow price: {row.shadow_price:,.2f} €/MWh")
    outline = go.Scattermapbox(name="binding country cap", lon=lon,
        lat=lat, mode="lines", line=dict(color=map_style.BINDING,
        width=SELECTED_WIDTH if selected_id == row.source_id else LINE_WIDTH), hoverinfo="skip")
    traces += map_style.haloed(outline)
    traces.append(go.Scattermapbox(name="select country cap", lon=outline.lon, lat=outline.lat,
        mode="markers", marker=dict(size=14, color="rgba(128,80,255,0.01)"),
        customdata=[[str(row.source_id)]] * len(lon), text=[hover] * len(lon), hoverinfo="text", hoverlabel=map_style.BINDING_HOVERLABEL))
    for trace in traces:
        trace.meta = {"role": "country-cap", "ambient": trace is outline}
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
    fill, labels = _price_traces(priced_zones, _fill_anchor(basemap), view.price_range)
    centres = _zone_centres(priced_zones)
    physical_selection = _selected(placed, view.selected_id)
    traces = [fill, *_constraint_traces(placed, physical_selection),
              *_cap_traces(zones, view.caps, view.selected_id)]
    if view.contribution is not None:
        assert view.reference is not None
        influence = cnec_influence.overlay(centres, view.contribution)
        traces += influence.traces
    symbols = [t for t in traces if isinstance(t.meta, dict) and t.meta.get("role") == "binding-symbol"]
    traces = [t for t in traces if not (isinstance(t.meta, dict) and t.meta.get("role") == "binding-symbol")]
    traces.extend(sorted(symbols, key=lambda t: bool(t.meta.get("effect"))))
    traces.append(labels)  # Last, so no dot or ray lands on a price
    fig = go.Figure(traces)
    fig.layout = map_layout(zones, mapbox_token, basemap)
    return fig


def price_figure(zones: DataFrame[BiddingZoneShapes], prices: DataFrame[ZonalPrices],
                 interval: pd.Timestamp, token: str, basemap: str | dict) -> go.Figure:
    """Price layer independent of constraint and attribution availability."""
    priced = _priced_zones(zones, ZonalPrices.validate(prices[prices.interval.eq(interval)]))
    return go.Figure(_price_traces(priced, _fill_anchor(basemap), daily_price_range(prices)),
                     layout=map_layout(zones, token, basemap))


def constraint_figure(zones: DataFrame[BiddingZoneShapes], constraints: DataFrame[ActiveConstraints],
                      geometries: DataFrame[MappedCnecElements],
                      interval: pd.Timestamp, selected_id: int | None, token: str,
                      basemap: str | dict) -> go.Figure:
    """Binding lines and interfaces, available without prices or attribution inputs."""
    placed = _placed(constraints, geometries)
    traces = _constraint_traces(placed, _selected(placed, selected_id))
    return go.Figure(traces, layout=map_layout(zones, token, basemap))


def map_layout(zones: DataFrame[BiddingZoneShapes], token: str | None,
               basemap: str | dict) -> go.Layout:
    """Shared stable camera and labels for independently arriving map layers."""
    return go.Layout(
        hovermode="closest",
        margin=dict(r=0, t=0, l=0, b=0),
        mapbox_style=basemap,
        mapbox_accesstoken=token,
        mapbox=_view(zones),
        uirevision="cnec-camera",
        showlegend=False,

    )
