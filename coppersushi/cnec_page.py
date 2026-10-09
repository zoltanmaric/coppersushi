"""Pure page state for exploring one day of prices and active constraints."""

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

import pandas as pd
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import dcc, html
from pandera.typing import DataFrame

from coppersushi import cnec_attribution, cnec_market, cnec_price_map, map_style, market
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.jao import (
    ActiveConstraints,
    ActiveExternalConstraints,
    ConstraintPtdfs,
)
from coppersushi.data_model.market import DayAheadPrices
from coppersushi.market_day import MARKET_TZ, MarketDay


@dataclass(frozen=True)
class Day:
    """Delivery-day inputs; geometry is resolved separately for the viewed interval."""

    market_day: MarketDay
    zones: pd.DataFrame
    constraints: DataFrame[ActiveConstraints]
    ptdfs: DataFrame[ConstraintPtdfs]
    external_constraints: DataFrame[ActiveExternalConstraints]
    prices: DataFrame[DayAheadPrices]
    context: pd.DataFrame | None = None


class Rendered(NamedTuple):
    """Map and control state emitted together so no control can drift from its interval."""

    figure: go.Figure
    interval_max: int
    interval_marks: dict[int, str]
    interval_value: int
    constraint_options: list[dict]
    constraint_value: str | None  # Bootstrap select values are strings
    reference: str | None


def local_today() -> str:
    """Today's Core market-day label in its named timezone."""
    return datetime.now(tz=MARKET_TZ).date().isoformat()


def empty_map(mapbox_token: str | None = None) -> go.Figure:
    """The geographic shell shown before the requested day's data arrives."""
    figure = go.Figure(go.Scattermapbox(lon=[], lat=[], hoverinfo="skip", showlegend=False))
    figure.update_layout(
        margin=dict(r=0, t=0, l=0, b=0),
        paper_bgcolor="#1b1b1b",
        mapbox=dict(
            style=map_style.MAP_STYLE,
            accesstoken=mapbox_token,
            center=dict(lat=50, lon=10),
            zoom=3.5,
        ),
        showlegend=False,
    )
    return figure


def layout(day: str | None = None, mapbox_token: str | None = None) -> html.Div:
    """The CNEC page controls; data loading and callbacks remain at the app boundary."""
    return html.Div(
        [
            html.Div(
                [
                    # Bootstrap controls, not `dcc` ones: the dark theme styles these, while
                    # `dcc.DatePickerSingle` and `dcc.Dropdown` ship a light palette of their
                    # own and would render their own state white on white.
                    dbc.Input(id="cnec-date", type="date", value=day or local_today()),
                    dbc.Select(
                        id="cnec-constraint",
                        placeholder="Select a binding row",
                    ),
                    html.Span(id="cnec-reference-zone"),
                    dbc.Button("Retry", id="cnec-retry", n_clicks=0, color="secondary"),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "12em minmax(20em, 1fr) auto auto",
                    "gap": "0.6em",
                    "padding": "0.4em 1em",
                },
            ),
            dbc.Alert(id="cnec-status", color="danger", is_open=False, style={"margin": "0 1em"}),
            dcc.Loading(
                [
                    dcc.Store(id="cnec-active-ready"),
                    dcc.Store(id="cnec-view-day"),
                    dcc.Store(id="cnec-prices-ready"),
                    dcc.Graph(
                        id="cnec-map",
                        figure=empty_map(mapbox_token),
                        style={"height": "100%"},
                        config={"responsive": True, "displayModeBar": False, "scrollZoom": True},
                    ),
                ],
                custom_spinner=html.Div(
                    [
                        html.Div(className="spinner-border spinner-border-sm", role="status"),
                        html.Span("Loading binding constraints…", id="cnec-progress"),
                    ],
                    style={"display": "flex", "gap": "0.6em", "alignItems": "center"},
                ),
                delay_show=300,
                parent_style={"height": "calc(100vh - 210px)", "minHeight": "400px"},
                overlay_style={"visibility": "visible", "opacity": 0.4},
            ),
            html.Div(
                [dbc.Button("Previous", id="cnec-previous", disabled=True, n_clicks=0),
                 dbc.Button("Next", id="cnec-next", disabled=True, n_clicks=0),
                 dcc.Slider(id="cnec-interval", min=0, max=1, step=1, value=0, allow_direct_input=False)],
                style={"padding": "0 1em 1.5em"},
            ),
        ]
    )


def interval_marks(day: MarketDay) -> dict[int, dict]:
    """A label every two hours on either hourly or quarter-hourly controls, in market time."""
    intervals = day.market_time_units()
    stride = 2 if len(intervals) <= 25 else 8
    return {
        index: {
            "label": interval.tz_convert(MARKET_TZ).strftime("%H:%M %Z") if index % stride == 0 else " ",
            "style": {"color": "white"},
        }
        for index, interval in enumerate(intervals)
    }


NO_SELECTION = {"label": "No constraint selected", "value": ""}


def _constraint_options(constraints: pd.DataFrame) -> list[dict]:
    options = [NO_SELECTION]
    for row in constraints.sort_values("shadow_price", ascending=False).itertuples():
        contingency = getattr(row, "cont_name", None)
        contingency = contingency if pd.notna(contingency) else "base case"
        options.append(
            {
                "label": (
                    f"{row.name} · {row.direction} · {contingency} · "
                    f"{row.shadow_price:,.2f} €/MWh"
                ),
                "value": str(row.source_id),
            }
        )
    return options


def render(
    day: Day,
    mapped_elements: DataFrame[MappedCnecElements],
    interval_index: int,
    selected_source_id: int | None,
    mapbox_token: str | None = None,
    basemap: str | dict = map_style.MAP_STYLE,
) -> Rendered:
    """Render one coherent map/control state from already-loaded day inputs."""
    intervals = day.market_day.market_time_units()
    index = min(max(int(interval_index), 0), len(intervals) - 1)
    interval = intervals[index]
    active = day.constraints[day.constraints.interval.eq(interval)]
    caps = cnec_attribution.country_caps(day.context, day.prices, interval)
    external = day.external_constraints[day.external_constraints.interval.eq(interval)]
    interfaces = external[external.hub.isin(cnec_attribution.INTERFACES)
                          & external.coefficient.isin([-1, 1])
                          & external.name.str.startswith("External Constraint")]
    options = _constraint_options(pd.concat([active, caps, interfaces], ignore_index=True))
    option_values = {option["value"] for option in options} - {NO_SELECTION["value"]}
    chosen = "" if selected_source_id is None else str(selected_source_id)
    selected_value = chosen if chosen in option_values else None
    selected = (
        cnec_market.ConstraintKey(int(selected_value)) if selected_value is not None else None
    )
    reference_zone = None
    note = ""
    alpha = None
    if day.context is not None:
        scaling = day.context[day.context.interval.eq(interval)]
        if len(scaling) == 1:
            alpha = float(scaling.alpha.iloc[0])
    if selected is not None and selected.source_id in active.source_id.values:
        row = active[active.source_id.eq(selected.source_id)].iloc[0]
        reference_zone = cnec_attribution.physical_reference(row, mapped_elements, day.zones)
        if reference_zone is None:
            note = "Contribution unavailable: sending endpoint has no unambiguous Core bidding zone."
    if note:
        snapshot = cnec_market.snapshot(day.constraints, day.ptdfs, day.external_constraints,
                                       day.prices, interval, context=day.context)
        snapshot = snapshot._replace(selected_id=selected.source_id, note=note)
    else:
        snapshot = cnec_market.snapshot(
            day.constraints, day.ptdfs, day.external_constraints, day.prices, interval,
            selected, reference_zone, context=day.context, alpha=alpha,
        )
    return Rendered(
        figure=cnec_price_map.figure(
            day.zones, mapped_elements, snapshot, mapbox_token, basemap
        ),
        interval_max=len(intervals) - 1,
        interval_marks=interval_marks(day.market_day),
        interval_value=index,
        constraint_options=options,
        constraint_value=selected_value,
        reference=snapshot.reference,
    )


def clicked_selection(click: dict | None, options: list[dict], current: str | None) -> str | None:
    """Resolve map hits against this interval only; keep a selected contingency in a group."""
    if not click or not click.get("points"):
        return current
    values = click["points"][0].get("customdata")
    if not isinstance(values, (list, tuple)) or not values:
        return current
    candidates = set(str(values[0]).split(","))
    allowed = [str(option["value"]) for option in options if option["value"]]
    if current in candidates and current in allowed:
        return current
    return next((value for value in allowed if value in candidates), current)


def advance_interval(day: MarketDay, index: int, step: int) -> int:
    """Move one market time unit, clamped to the delivery day's actual UTC extent."""
    return min(max(index + step, 0), len(day.market_time_units()) - 1)
