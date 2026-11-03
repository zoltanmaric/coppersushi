"""Contracts for JAO attribution objects and the normalized attribution table."""

import pandera.pandas as pa
from pandera.typing import Series
from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictFloat, StrictInt

from coppersushi.data_model.jao import UtcTimestamp


class JaoRecord(BaseModel):
    """Only consumed fields are modeled; additional publisher fields are harmless."""

    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)
    dateTimeUtc: AwareDatetime


class AlphaFactor(JaoRecord):
    alphaFactor: StrictFloat | None


class AllocationConstraint(JaoRecord):
    limitDown_PL: StrictFloat | None
    limitUp_PL: StrictFloat | None


class NetPosition(JaoRecord):
    hub_PL: StrictFloat | None


class PolishAlternative(JaoRecord):
    id: StrictInt
    border_PL_ALT: StrictFloat | None
    border_PL_SDAC_NP: StrictFloat | None


class AttributionRow(BaseModel):
    """JSON null means an unavailable input, never a zero contribution."""

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
