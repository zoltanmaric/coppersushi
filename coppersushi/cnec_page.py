"""Pure page state for exploring one day of prices and active constraints."""

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

import pandas as pd
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
from dash import dcc, html
from pandera.typing import DataFrame

from coppersushi import cnec_market, cnec_price_map, map_style, market
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
    """All in-memory inputs for one delivery day's page."""

    market_day: MarketDay
    zones: pd.DataFrame
    mapped_elements: DataFrame[MappedCnecElements]
    constraints: DataFrame[ActiveConstraints]
    ptdfs: DataFrame[ConstraintPtdfs]
    external_constraints: DataFrame[ActiveExternalConstraints]
    prices: DataFrame[DayAheadPrices]


class Rendered(NamedTuple):
    """Map and control state emitted together so no control can drift from its interval."""

    figure: go.Figure
    interval_max: int
    interval_marks: dict[int, str]
    interval_value: int
    constraint_options: list[dict]
    constraint_value: str | None  # Bootstrap select values are strings


def local_today() -> str:
    """Today's Core market-day label in its named timezone."""
    return datetime.now(tz=MARKET_TZ).date().isoformat()


def layout(day: str | None = None) -> html.Div:
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
                    dbc.Select(
                        id="cnec-reference-zone",
                        options=[{"label": zone, "value": zone} for zone in market.CORE_ZONES],
                        value="AT",
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "12em minmax(24em, 1fr) 7em",
                    "gap": "0.6em",
                    "padding": "0.4em 1em",
                },
            ),
            dbc.Alert(id="cnec-status", color="danger", is_open=False, style={"margin": "0 1em"}),
            dcc.Graph(
                id="cnec-map",
                style={"height": "82vh"},
                config={"responsive": True, "displayModeBar": False, "scrollZoom": True},
            ),
            html.Div(
                dcc.Slider(id="cnec-interval", min=0, max=1, step=1, value=0),
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
            "label": interval.tz_convert(MARKET_TZ).strftime("%H:%M"),
            "style": {"color": "white"},
        }
        for index, interval in enumerate(intervals)
        if index % stride == 0
    }


NO_SELECTION = {"label": "No constraint selected", "value": ""}


def _constraint_options(constraints: pd.DataFrame) -> list[dict]:
    options = [NO_SELECTION]
    for row in constraints.sort_values("shadow_price", ascending=False).itertuples():
        contingency = row.cont_name if pd.notna(row.cont_name) else "base case"
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
    interval_index: int,
    selected_source_id: int | None,
    reference_zone: str,
    mapbox_token: str | None = None,
    basemap: str | dict = map_style.MAP_STYLE,
) -> Rendered:
    """Render one coherent map/control state from already-loaded day inputs."""
    intervals = day.market_day.market_time_units()
    index = min(max(int(interval_index), 0), len(intervals) - 1)
    interval = intervals[index]
    active = day.constraints[day.constraints.interval.eq(interval)]
    options = _constraint_options(active)
    option_values = {option["value"] for option in options} - {NO_SELECTION["value"]}
    chosen = "" if selected_source_id is None else str(selected_source_id)
    selected_value = chosen if chosen in option_values else None
    selected = (
        cnec_market.ConstraintKey(int(selected_value)) if selected_value is not None else None
    )
    snapshot = cnec_market.snapshot(
        day.constraints,
        day.ptdfs,
        day.external_constraints,
        day.prices,
        interval,
        selected,
        reference_zone if selected is not None else None,
    )
    return Rendered(
        figure=cnec_price_map.figure(
            day.zones, day.mapped_elements, snapshot, mapbox_token, basemap
        ),
        interval_max=len(intervals) - 1,
        interval_marks=interval_marks(day.market_day),
        interval_value=index,
        constraint_options=options,
        constraint_value=selected_value,
    )
