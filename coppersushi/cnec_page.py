"""Pure page state for exploring one day of prices and active constraints."""

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

import pandas as pd
from coppersushi.data_model.cnec_attribution import AttributionContext
import plotly.graph_objects as go
from pandera.typing import DataFrame

from coppersushi import cnec_attribution, cnec_market, cnec_price_map, map_style, market
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.jao import (
    ActiveConstraints,
    ConstraintPtdfs,
)
from coppersushi.data_model.market import DayAheadPrices
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.market_day import MARKET_TZ, MarketDay


@dataclass(frozen=True)
class Day:
    """Delivery-day inputs; geometry is resolved separately for the viewed interval."""

    market_day: MarketDay
    zones: DataFrame[BiddingZoneShapes]
    constraints: DataFrame[ActiveConstraints]
    ptdfs: DataFrame[ConstraintPtdfs]
    prices: DataFrame[DayAheadPrices]
    context: DataFrame[AttributionContext] | None = None


class Rendered(NamedTuple):
    """Rendered map, available constraint choices and selected reference for one interval."""

    figure: go.Figure
    constraint_options: list[dict]
    reference: str | None
    notes: tuple[str, ...]


def local_today() -> str:
    """Today's Core market-day label in its named timezone."""
    return datetime.now(tz=MARKET_TZ).date().isoformat()


NO_SELECTION = {"label": "No constraint selected", "value": "", "source": "constraints"}


def constraint_options(constraints: pd.DataFrame) -> list[dict]:
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
                "source": str(row.option_source),
            }
        )
    return options


def render(
    day: Day,
    mapped_elements: DataFrame[MappedCnecElements],
    interval_index: int,
    selected_source_id: str | int | None,
    mapbox_token: str | None = None,
    basemap: str | dict = map_style.MAP_STYLE,
) -> Rendered:
    """Render one coherent map/control state from already-loaded day inputs."""
    intervals = day.market_day.market_time_units()
    index = min(max(int(interval_index), 0), len(intervals) - 1)
    interval = intervals[index]
    active = day.constraints[day.constraints.interval.eq(interval)]
    caps = cnec_attribution.country_caps(day.context, day.prices, interval)
    option_tables: list[pd.DataFrame] = [
        active.assign(option_source="constraints"), caps.assign(option_source="attribution"),
    ]
    options = constraint_options(pd.concat(option_tables, ignore_index=True))
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
        reference_zone = cnec_attribution.physical_reference(row, mapped_elements, day.zones, day.prices)
        if reference_zone is None:
            note = "Contribution unavailable: no unambiguous Core reference is available."
    if note:
        assert selected is not None
        snapshot = cnec_market.snapshot(day.constraints, day.ptdfs,
                                       day.prices, interval, context=day.context)
        snapshot = snapshot._replace(selected_id=selected.source_id, notes=(*snapshot.notes, note))
    else:
        snapshot = cnec_market.snapshot(
            day.constraints, day.ptdfs, day.prices, interval,
            selected, reference_zone, context=day.context, alpha=alpha,
        )
    return Rendered(
        figure=cnec_price_map.figure(
            day.zones, mapped_elements, snapshot, mapbox_token, basemap
        ),
        constraint_options=options,
        reference=snapshot.reference,
        notes=snapshot.notes,
    )
