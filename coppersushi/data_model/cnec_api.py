"""HTTP contracts for independently loaded CNEC map layers and enrichment."""

from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt
from coppersushi.data_model.cnec_attribution import AttributionPayload
from coppersushi.data_model.market import CoreZone


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ViewRequest(Contract):
    """One explicit market-day view; selection is a published row identifier."""
    day: date
    interval: StrictInt = Field(ge=0)
    selected: StrictInt | None
    reference: CoreZone | None = None  # None chooses the element’s automatic reference.


class EnrichedRequest(ViewRequest):
    """Current view plus already fetched attribution, independent of Lambda affinity."""
    attribution: AttributionPayload


class PlotlyLayout(BaseModel):
    """A map layout with Plotly-owned extensions and an explicit camera object."""
    model_config = ConfigDict(extra="allow")
    mapbox: dict[str, JsonValue]
    uirevision: str


class PlotlyFigure(Contract):
    """Plotly's extensible JSON figure; Plotly validates its trace/layout schemas."""
    data: list[dict[str, JsonValue]]
    layout: PlotlyLayout


class ConstraintOption(Contract):
    label: str
    value: str
    source: Literal["constraints", "attribution"]


class LayerResponse(Contract):
    """One ready visual layer scoped to the exact view that requested it."""
    request: ViewRequest
    figure: PlotlyFigure
    options: list[ConstraintOption]
    reference: str | None
    notes: list[str]


class DayResponse(Contract):
    """Market-time-unit labels computed in the market timezone, including DST folds."""
    day: date
    labels: list[str]


class ApiError(Contract):
    error: str
