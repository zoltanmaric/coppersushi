"""Values shared by input collection, selection and feature construction."""
from datetime import datetime
from typing import Any, NotRequired, TypedDict

# Serialized provider records have heterogeneous columns, validated at loading.
Row = dict[str, Any]
Report = dict[str, Any]

PriceSeries = dict[datetime, float | None]
WeatherSeries = dict[str, PriceSeries]


class DemandVersion(TypedDict):
    """One retained publication of the country-level demand forecast."""
    updated: datetime | None
    value: float | None
    source: str
    eligible_at_issue: NotRequired[bool]  # Snapshot evidence adds a receipt policy to the raw update cutoff.


DemandSeries = dict[datetime, list[DemandVersion]]

