"""Values shared by input collection, selection and feature construction."""
from datetime import datetime
from typing import Any, TypedDict

# Serialized provider records have heterogeneous columns, validated at loading.
Row = dict[str, Any]
Report = dict[str, Any]

PriceSeries = dict[datetime, float | None]
WeatherSeries = dict[str, PriceSeries]


class DemandVersion(TypedDict):
    updated: datetime | None
    value: float | None
    source: str


DemandSeries = dict[datetime, list[DemandVersion]]

