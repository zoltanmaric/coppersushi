"""Day-scoped domain data consumed by the browser renderer."""
from datetime import date
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field
from coppersushi.pipelines.data_model.market import CoreZone

Coordinates = Annotated[list[float], Field(min_length=2, max_length=2)]


class Contract(BaseModel):
    """Prepared-publication models reject fields outside the shared contract."""
    model_config = ConfigDict(extra='forbid')

class ZoneGeometry(Contract):
    """Display boundary and interior label anchor shared by every interval."""
    zone: CoreZone
    name: str
    rings: list[list[Coordinates]]
    centre: Coordinates

class ElementGeometry(Contract):
    """Resolved physical element in its publisher's orientation."""
    branch_id: str
    kind: Literal['line', 'transformer']
    endpoints: Annotated[list[Coordinates], Field(min_length=2, max_length=2)]

class BindingRow(Contract):
    """One physical binding publication with its country sensitivities."""
    source_id: int
    eic: str = Field(pattern=r"^[A-Z0-9-]{16}$")
    name: str
    direction: str
    contingency: str | None
    shadow_price: float
    ram: float | None
    capacity: float | None
    geometry: str | None
    ptdfs: dict[CoreZone, float]

class CountryCap(Contract):
    """Inferred Polish cap and its signed effect on the Polish price."""
    source_id: Literal[-1, -2]
    name: str
    direction: str
    capacity: float
    shadow_price: float
    delta: float

class MarketInterval(Contract):
    """Published values for one UTC interval, labelled in market local time."""
    index: int = Field(ge=0)
    label: str
    prices: dict[CoreZone, float]
    constraints: list[BindingRow]
    alpha: float | None
    caps: list[CountryCap]
    notes: list[str]

class DayMetadata(Contract):
    """Versioned, token-free data for all interactions within a delivery day."""
    version: Literal[2] = 2
    day: date
    labels: list[str]
    zones: list[ZoneGeometry]
    elements: dict[str, ElementGeometry]
    price_range: Coordinates

class DayBundle(DayMetadata):
    """Producer-side complete day; browser delivery uses separate interval objects."""
    intervals: list[MarketInterval]


class DayManifest(Contract):
    """Atomic pointer to a complete immutable generation of a prepared day."""
    version: Literal[2] = 2
    day: date
    generation: str = Field(pattern=r'^[0-9a-f]{24}$')
