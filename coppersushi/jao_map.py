"""JAO's day drawn on our network: which grid elements actually limited cross-border trade.

The domain feed says what every monitored element's limit was in each hour; the shadow-price
feed says which of them the market coupling actually hit, and what one more MW there would have
been worth. `elements.branch_for` has already said which `Line` or `Transformer` of ours each
element is. This module is the last step: those three, per hour, as Plotly traces.

Three things decide the shape of what is drawn.

1. **A fixed number of traces per hour.** The figure carries every hour's traces at once and the
   slider makes one hour's visible, exactly as `power_flow.show_snapshot` does; the arithmetic
   that finds an hour's traces is a stride, so the stride may not vary with the data. A
   Scattermapbox line has one colour for the whole trace, so "colour by shadow price" has to be
   bins — and the bin edges are therefore constants (the real day's quartiles, rounded), never
   quantiles recomputed per hour, which would silently renumber every trace.
2. **Binding and non-binding are different questions.** An element that bound has a price, and
   the price is the interesting number. One that did not has a margin, `ram / fmax`, and the
   interesting number is how close it came. Two scales, and a non-binding element never borrows
   the binding palette.
3. **What is missing is on the map.** External constraints have no location at all — they are
   limits on a zone's net position, not on a wire — and unmatched elements have no branch to
   draw. Both are counted into a layout annotation, so a reader sees that part of JAO's day is
   not on screen rather than assuming the screen is all of it.

`to_snapshot` is the one place JAO's tz-aware UTC hours become PyPSA's naive ones. Getting it
wrong drops every join and renders an empty map without raising, so it is a named function with
a test rather than an inline `tz_localize`.

Design: `wiki/specs/jao-grid.md`.
"""

import logging

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pypsa
from pandera.typing import DataFrame

from coppersushi import power_flow
from coppersushi.data_model.elements import ElementMatches
from coppersushi.data_model.jao import Elements, ExternalConstraintsWithPrices, ShadowPrices
from coppersushi.data_model.jao_map import HourlyElements
from coppersushi.elements import MATCHED, NO_COMPONENT, TRANSFORMER

logger = logging.getLogger(__name__)

# Upper edge, legend label, colour. The edges are the real day's quartiles of `ram / fmax`
# (0.54, 0.70, 0.90 on 2024-08-29), rounded and frozen: the trace count must not move with
# the data. Cool and thin, so a binding element is never lost among them.
MARGIN_BINS = (
    (0.55, "margin < 55%", "#8ad9ff"),
    (0.70, "margin 55–70%", "#4c9fd0"),
    (0.90, "margin 70–90%", "#2d6183"),
    (np.inf, "margin ≥ 90%", "#1d4258"),
)

# The same, for the shadow price of an element that bound: the day's quartiles were 41, 100
# and 211 EUR/MWh. Warm and thick — these are the elements that cost the market money.
PRICE_BINS = (
    (40.0, "binding < 40 €/MWh", "#ffd166"),
    (100.0, "binding 40–100 €/MWh", "#f4813f"),
    (210.0, "binding 100–210 €/MWh", "#ef476f"),
    (np.inf, "binding ≥ 210 €/MWh", "#ff1f4b"),
)

MARGIN_WIDTH = 2.0
PRICE_WIDTH = 5.0

# Background, one trace per margin bin, one per price bin, the line hover markers, the points.
NUM_TRACES_PER_HOUR = 1 + len(MARGIN_BINS) + len(PRICE_BINS) + 2

HOURLY_COLUMNS = [
    "snapshot", "eic", "name", "tso", "element_type", "branch_type", "branch_id", "end0", "end1",
    "x0", "y0", "x1", "y1", "fmax", "ram", "margin", "shadow_price", "binding",
]


def to_snapshot(hours: pd.Series) -> pd.Series:
    """JAO's tz-aware UTC hours as PyPSA's naive ones — the single conversion point.

    PyPSA snapshots are naive and mean UTC; JAO publishes `dateTimeUtc` aware. Joining the two
    without this drops every row and draws an empty map without raising.
    """
    return hours.dt.tz_convert("UTC").dt.tz_localize(None)


def _tightest_by_hour(elements: DataFrame[Elements]) -> pd.DataFrame:
    """One row per (snapshot, eic): the tighter of the two directions JAO publishes.

    An element carries a DIRECT and an OPPOSITE limit in the same hour. What the map asks is
    how close the element came to binding at all, so the smaller margin is the answer.
    """
    hourly = elements.assign(snapshot=to_snapshot(elements.hour), margin=elements.ram / elements.fmax)
    return hourly.sort_values("margin").groupby(["snapshot", "eic"], as_index=False).first()


def _prices_by_hour(shadow_prices: DataFrame[ShadowPrices]) -> pd.DataFrame:
    """One row per (snapshot, eic): the dearest price the element bound at that hour.

    An element can bind against several contingencies in one hour; the map draws one element,
    so it draws the worst of them.
    """
    priced = shadow_prices.assign(
        snapshot=to_snapshot(shadow_prices.hour), shadow_price=shadow_prices.shadow_price.abs()
    )
    return priced.groupby(["snapshot", "eic"], as_index=False).shadow_price.max()


def hourly_elements(
    n: pypsa.Network,
    matched: DataFrame[ElementMatches],
    elements: DataFrame[Elements],
    shadow_prices: DataFrame[ShadowPrices],
) -> DataFrame[HourlyElements]:
    """Every matched element, per hour, with its limit, its price and its coordinates."""
    placed = matched[matched.match_status == MATCHED]
    hourly = _tightest_by_hour(elements).merge(
        placed[["eic", "name", "element_type", "branch_type", "branch_id", "bus0", "bus1"]],
        on="eic",
        suffixes=("_jao", ""),
    )
    hourly = hourly.merge(_prices_by_hour(shadow_prices), on=["snapshot", "eic"], how="left")
    hourly["binding"] = hourly.shadow_price.notna()
    labels = power_flow.bus_labels(n.buses)
    for end, bus in (("0", "bus0"), ("1", "bus1")):
        hourly["x" + end] = n.buses.x.reindex(hourly[bus]).to_numpy()
        hourly["y" + end] = n.buses.y.reindex(hourly[bus]).to_numpy()
        hourly["end" + end] = labels.reindex(hourly[bus]).to_numpy()
    logger.info(
        "%d of %d elements placed; %d (snapshot, element) rows, %d of them binding",
        placed.eic.nunique(),
        len(matched),
        len(hourly),
        int(hourly.binding.sum()),
    )
    return hourly[HOURLY_COLUMNS].pipe(HourlyElements.validate)


def _bin_of(values: pd.Series, bins: tuple) -> pd.Series:
    """The index of each value's bin, the last bin catching everything above the last edge."""
    edges = [edge for edge, _, _ in bins[:-1]]
    return pd.Series(np.digitize(values.to_numpy(dtype=float), edges), index=values.index)


def _hover(frame: pd.DataFrame) -> pd.Series:
    """The element's own name as the heading, the branch of ours it is beneath it."""
    price = frame.shadow_price.map(lambda value: f"{value:,.0f} €/MWh" if pd.notna(value) else "did not bind")
    return (
        "<b>" + frame["name"] + "</b><br>"
        + frame.end0 + " → " + frame.end1 + "<br>"
        + frame.branch_id + "<br>"
        + frame.tso + " · " + frame.element_type.replace("", "element") + "<br>"
        + "RAM " + frame.ram.round().astype(int).astype(str)
        + " / " + frame.fmax.round().astype(int).astype(str) + " MW"
        + " (" + (frame.margin * 100).round().astype(int).astype(str) + "%)<br>"
        + "Shadow price: " + price
    )


def _line_trace(frame: pd.DataFrame, name: str, colour: str, width: float) -> go.Scattermapbox:
    """One bin's worth of line elements, each drawn bus0 → bus1."""
    gap = np.full(len(frame), np.nan)  # Plotly breaks the line where a coordinate is null
    lon = np.stack([frame.x0.to_numpy(float), frame.x1.to_numpy(float), gap], axis=1).ravel()
    lat = np.stack([frame.y0.to_numpy(float), frame.y1.to_numpy(float), gap], axis=1).ravel()
    return go.Scattermapbox(
        lon=lon, lat=lat, mode="lines", name=name, hoverinfo="none", visible=False,
        line=dict(width=width, color=colour),
    )


def _marker_trace(
    frame: pd.DataFrame, name: str, size: float, symbol: str, in_legend: bool
) -> go.Scattermapbox:
    """Hover targets: line elements at their midpoint, point elements at their substation.

    A Scattermapbox line carries one colour, which is why the bins exist; a marker carries one
    per point, so these are coloured from the same bins without needing one trace each.
    """
    return go.Scattermapbox(
        lon=(frame.x0 + frame.x1) / 2, lat=(frame.y0 + frame.y1) / 2,
        mode="markers", name=name, hoverinfo="text", text=_hover(frame), visible=False,
        showlegend=in_legend,
        marker=go.scattermapbox.Marker(size=size, color=_colours(frame), symbol=symbol),
    )


def _colours(frame: pd.DataFrame) -> list[str]:
    """Each element's colour: its price bin where it bound, else its margin bin."""
    price_bin = _bin_of(frame.shadow_price.fillna(0.0), PRICE_BINS)
    margin_bin = _bin_of(frame.margin, MARGIN_BINS)
    return [
        PRICE_BINS[price][2] if binding else MARGIN_BINS[margin][2]
        for binding, price, margin in zip(frame.binding, price_bin, margin_bin)
    ]


def background_trace(n: pypsa.Network) -> go.Scattermapbox:
    """The rest of the network, so the elements JAO monitors are seen in their grid."""
    lines = n.lines[["bus0", "bus1"]]
    ends = pd.DataFrame(
        {
            "x0": n.buses.x.reindex(lines.bus0).to_numpy(), "x1": n.buses.x.reindex(lines.bus1).to_numpy(),
            "y0": n.buses.y.reindex(lines.bus0).to_numpy(), "y1": n.buses.y.reindex(lines.bus1).to_numpy(),
        }
    )
    trace = _line_trace(ends, "the rest of the network", "#4a4a4a", 0.5)
    trace.showlegend = False
    return trace


def hour_traces(frame: DataFrame[HourlyElements], background: go.Scattermapbox) -> list[go.Scattermapbox]:
    """One hour's traces, always `NUM_TRACES_PER_HOUR` of them however empty the hour is."""
    lines = frame[frame.branch_type != TRANSFORMER]
    points = frame[frame.branch_type == TRANSFORMER]
    non_binding, binding = lines[~lines.binding], lines[lines.binding]

    traces = [go.Scattermapbox(background)]
    traces += [
        _line_trace(non_binding[_bin_of(non_binding.margin, MARGIN_BINS) == index], label, colour, MARGIN_WIDTH)
        for index, (_, label, colour) in enumerate(MARGIN_BINS)
    ]
    traces += [
        _line_trace(binding[_bin_of(binding.shadow_price, PRICE_BINS) == index], label, colour, PRICE_WIDTH)
        for index, (_, label, colour) in enumerate(PRICE_BINS)
    ]
    # The line markers only carry the hover; their colours already have a legend entry each.
    traces.append(_marker_trace(lines, "line elements", 6.0, "circle", in_legend=False))
    traces.append(_marker_trace(points, "transformers and PSTs", 13.0, "square", in_legend=True))
    return traces


def missing_note(
    matched: DataFrame[ElementMatches],
    external_constraints: DataFrame[ExternalConstraintsWithPrices] | None = None,
) -> str:
    """What of JAO's day is not on the map, and why — the annotation's text.

    `no_component_in_network` is separated from the rest because it is not a matching failure:
    it is our network having no such component class at all, which an upstream simplification
    is responsible for.
    """
    missing = matched[matched.match_status != MATCHED]
    counts = missing.match_status.value_counts()
    lines = [f"<b>{len(matched) - len(missing)} of {len(matched)} elements on the map</b>"]
    if not counts.empty:
        lines.append("not drawn: " + ", ".join(f"{count} {status}" for status, count in counts.items()))
    absent = missing[missing.match_status == NO_COMPONENT]
    if not absent.empty:
        lines.append(f"({len(absent)} of those are transformers and PSTs: our network carries none)")
    if external_constraints is not None and not external_constraints.empty:
        bound = external_constraints[external_constraints.shadow_price.notna()].name.nunique()
        lines.append(
            f"{external_constraints.name.nunique()} external constraints have no location at all"
            + (f"; {bound} of them bound" if bound else "")
        )
    return "<br>".join(lines)


def figure(
    n: pypsa.Network,
    matched: DataFrame[ElementMatches],
    elements: DataFrame[Elements],
    shadow_prices: DataFrame[ShadowPrices],
    external_constraints: DataFrame[ExternalConstraintsWithPrices] | None = None,
    mapbox_token: str | None = None,
    note: str = "",
) -> go.Figure:
    """JAO's day on the network: one trace set per snapshot, the first of them visible.

    The hours come from `n.snapshots`, not from JAO, so the slider that drives the rest of the
    app drives this too — and an hour JAO published nothing for is an empty frame, not a
    missing one.
    """
    hourly = hourly_elements(n, matched, elements, shadow_prices)
    background = background_trace(n)
    by_snapshot = dict(list(hourly.groupby("snapshot")))
    empty = hourly.iloc[:0]

    fig = go.Figure(layout=go.Layout(hovermode="closest", uirevision=True))
    for snapshot in n.snapshots:
        fig.add_traces(hour_traces(by_snapshot.get(snapshot, empty), background))

    annotation = "<br>".join(filter(None, [note, missing_note(matched, external_constraints)]))
    fig.update_layout(
        margin=dict(r=0, t=0, l=0, b=0),
        mapbox_style="dark",
        mapbox_accesstoken=mapbox_token,
        showlegend=True,
        legend=dict(x=0.01, y=0.99, bgcolor="rgba(0,0,0,0.6)", font=dict(size=11)),
        annotations=[
            go.layout.Annotation(
                text=annotation, xref="paper", yref="paper", x=0.99, y=0.01,
                xanchor="right", yanchor="bottom", align="right", showarrow=False,
                bgcolor="rgba(0,0,0,0.6)", bordercolor="#666", borderpad=6, font=dict(size=11),
            )
        ],
    )
    return power_flow.show_snapshot(fig, 0, NUM_TRACES_PER_HOUR)
