"""HTTP contracts for independently loaded CNEC map layers and enrichment."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, JsonValue


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class ApiError(Contract):
    error: str
