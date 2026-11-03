"""Contracts for JAO attribution objects and the normalized attribution table."""

import pandera.pandas as pa
from pandera.typing import Series
from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictFloat, StrictInt

from coppersushi.data_model.jao import UtcTimestamp


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
    """Attribution inputs for one interval in browser JSON; null means unavailable."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    interval: AwareDatetime
    alpha: StrictFloat | None
    import_limit: StrictFloat | None
    export_limit: StrictFloat | None
    polish_position: StrictFloat | None
    polish_alt: StrictFloat | None


class AttributionPayload(BaseModel):
    """Browser enrichment scoped to the day and retry that requested it."""

    model_config = ConfigDict(extra="forbid", strict=True)
    day: str
    request: int | None
    complete: bool
    rows: list[AttributionRow] | None = None
    error: str | None = None


class AttributionContext(pa.DataFrameModel):
    """One UTC market interval per row; optional feeds stay numeric when missing."""

    interval: Series[UtcTimestamp] = pa.Field(unique=True)
    alpha: Series[float] = pa.Field(nullable=True)
    import_limit: Series[float] = pa.Field(nullable=True)
    export_limit: Series[float] = pa.Field(nullable=True)
    polish_position: Series[float] = pa.Field(nullable=True)
    polish_alt: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True
