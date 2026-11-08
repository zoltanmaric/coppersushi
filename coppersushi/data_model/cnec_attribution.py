"""Inputs for explaining electricity-price differences between bidding zones.

Price attribution calculates each binding constraint's contribution to an observed
price difference, in EUR/MWh. These models hold supplementary inputs: flow-based
scaling and Polish import/export limits, net positions and alternative prices.
See wiki/flow-based-market-coupling.md#attribution for an example and interpretation.
"""


import datetime

import pandera.pandas as pa
from pandera.typing import Series
from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictFloat, StrictInt

from coppersushi.data_model.jao import ZonedTimestamp


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


class AttributionContext(pa.DataFrameModel):
    """Table of scaling and Polish cap inputs, one UTC market interval per row."""

    interval: Series[ZonedTimestamp] = pa.Field(dtype_kwargs={"tz": datetime.UTC}, unique=True)
    alpha: Series[float] = pa.Field(nullable=True, ge=0, le=1)
    import_limit: Series[float] = pa.Field(nullable=True)
    export_limit: Series[float] = pa.Field(nullable=True)
    polish_position: Series[float] = pa.Field(nullable=True)
    polish_alt: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True


class CountryCaps(pa.DataFrameModel):
    """Binding Polish aggregate import/export limits and their price effects for an interval."""

    source_id: Series[int]
    interval: Series[ZonedTimestamp] = pa.Field(dtype_kwargs={"tz": datetime.UTC})
    name: Series[str]
    shadow_price: Series[float] = pa.Field(gt=0)
    direction: Series[str] = pa.Field(isin=["import", "export"])
    capacity: Series[float]
    delta: Series[float]

    class Config:
        strict = True
        coerce = True
        unique = ["interval", "source_id"]
