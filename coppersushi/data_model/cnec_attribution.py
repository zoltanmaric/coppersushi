"""Inputs for explaining electricity-price differences between bidding zones.

Price attribution calculates each binding constraint's contribution to an observed
price difference, in EUR/MWh. These models hold supplementary inputs: flow-based
scaling and Polish import/export limits, net positions and alternative prices.
See wiki/flow-based-market-coupling.md#attribution for an example and interpretation.
"""


import datetime
from datetime import date

import pandas as pd
import pandera.pandas as pa
from pandera.typing import DataFrame, Series
from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictFloat, StrictInt, field_validator

from coppersushi.data_model.jao import ZonedTimestamp
from coppersushi.market_day import MarketDay


class JaoRecord(BaseModel):
    """A timestamped JAO publication record; unconsumed publisher fields are ignored."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    dateTimeUtc: AwareDatetime


class AlphaFactor(JaoRecord):
    """Published flow-based scaling factor for one market interval."""

    alphaFactor: StrictFloat


class AllocationConstraint(JaoRecord):
    """Polish aggregate import and export limits in MW for one market interval."""

    limitDown_PL: StrictFloat
    limitUp_PL: StrictFloat


class NetPosition(JaoRecord):
    """Polish net position in MW for one market interval."""

    hub_PL: StrictFloat


class PolishAlternative(JaoRecord):
    """Polish net position and alternative price used to infer the cap contribution."""

    id: StrictInt
    border_PL_ALT: StrictFloat
    border_PL_SDAC_NP: StrictFloat


class AttributionRow(BaseModel):
    """Inputs for explaining why electricity prices differ between bidding zones.

    Attribution calculates how much each binding grid or import/export limit
    contributes to that price difference, in EUR/MWh. This row holds the scaling
    factor and Polish cap inputs for one market interval, encoded as browser JSON.
    Null means an input is unavailable.

    See wiki/flow-based-market-coupling.md#attribution for an example and limits.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    interval: AwareDatetime
    alpha: StrictFloat | None
    import_limit: StrictFloat | None
    export_limit: StrictFloat | None
    polish_position: StrictFloat | None
    polish_alt: StrictFloat | None


class AttributionRequest(BaseModel):
    """Delivery date shared by attribution browser responses."""

    model_config = ConfigDict(extra="forbid", strict=True)
    day: date

    @field_validator('day', mode='before')
    @classmethod
    def parse_delivery_date(cls, value: object) -> object:
        """Parse the browser's ISO date; strict validation rejects other representations."""
        return date.fromisoformat(value) if isinstance(value, str) else value


class AttributionPayload(AttributionRequest):
    """Successfully loaded price-attribution inputs for one browser request."""

    complete: bool
    rows: list[AttributionRow]


class AttributionFailure(AttributionRequest):
    """A failed attribution load, tied to its browser request; contains no data."""

    error: str


class AttributionContext(pa.DataFrameModel):
    """Table of scaling and Polish cap inputs, one UTC market interval per row."""

    interval: Series[ZonedTimestamp] = pa.Field(dtype_kwargs={"tz": datetime.UTC}, unique=True)
    alpha: Series[float] = pa.Field(nullable=True)
    import_limit: Series[float] = pa.Field(nullable=True)
    export_limit: Series[float] = pa.Field(nullable=True)
    polish_position: Series[float] = pa.Field(nullable=True)
    polish_alt: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True


def attribution_to_browser(frame: DataFrame[AttributionContext], day: MarketDay) -> AttributionPayload:
    """Build a typed browser payload from a day's table, preserving missing inputs as None."""
    return AttributionPayload.model_validate({
        'day': day.date,
        'rows': frame.astype(object).where(frame.notna(), None).to_dict(orient='records'),
        'complete': bool(frame.notna().all().all()),
    })


def attribution_from_browser(payload: AttributionPayload) -> DataFrame[AttributionContext]:
    """Restore UTC timestamps and numeric missing values from a validated browser payload."""
    frame = pd.DataFrame([row.model_dump() for row in payload.rows])
    frame['interval'] = pd.to_datetime(frame.interval, utc=True)
    return AttributionContext.validate(frame)
