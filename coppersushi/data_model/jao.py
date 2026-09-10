"""Pandera schemas for the tidy tables `cnecs.py` builds out of JAO's Core publication feeds.

Units and meanings are the handbook's (`wiki/literature/jao-core-publication-handbook.md`).
`strict = False` throughout, so raw JAO columns a caller chooses to keep pass through.
"""

import datetime

import pandas as pd
import pandera.pandas as pa
from pandera import dtypes
from pandera.engines import pandas_engine
from pandera.typing import Series


@dtypes.immutable(init=True)
class UtcTimestamp(pandas_engine.DateTime):
    """A UTC timestamp that refuses naive input rather than coercing it.

    Pandera's own UTC coercion localises a naive column, which would silently bless a
    timestamp whose true zone was never known (`coppersushi/AGENTS.md`, explicit-timezones).
    """

    tz: datetime.tzinfo | str | None = "UTC"

    def coerce(self, data_container):
        dtype = getattr(data_container, "dtype", None)
        if not isinstance(dtype, pd.DatetimeTZDtype):
            raise TypeError(f"expected tz-aware timestamps, got {dtype}")
        return super().coerce(data_container)


class Elements(pa.DataFrameModel):
    """One row per (hour, element EIC, direction): a presolved, physical CNEC."""

    hour: Series[UtcTimestamp]  # Market time unit, its first instant
    eic: Series[str]  # EIC code of the monitored element
    name: Series[str]  # The TSO's name for the element
    tso: Series[str]  # Monitoring TSO, upper case
    direction: Series[str]  # DIRECT or OPPOSITE, the sense the limit applies in
    hub_from: Series[str] = pa.Field(nullable=True)  # Bidding zone the element leaves
    hub_to: Series[str] = pa.Field(nullable=True)  # Bidding zone it enters
    substation_from: Series[str] = pa.Field(nullable=True)  # Substation at the from end
    substation_to: Series[str] = pa.Field(nullable=True)  # Substation at the to end
    element_type: Series[str]  # Line, TieLine, Transformer or PST
    fmax_type: Series[str] = pa.Field(nullable=True)  # Basis of the rating, e.g. SEASONAL
    u: Series[float] = pa.Field(nullable=True)  # Nominal voltage [kV]
    imax: Series[float] = pa.Field(nullable=True)  # Thermal current limit [A]
    fmax: Series[float]  # Maximum admissible flow [MW]; the tighter one where TSOs differ
    frm: Series[float] = pa.Field(nullable=True)  # Flow reliability margin [MW]
    fref: Series[float] = pa.Field(nullable=True)  # Reference flow [MW]
    ram: Series[float]  # Remaining available margin left to the market [MW]
    contingency_count: Series[int]  # Presolved rows behind this element and direction
    tso_disagreement: Series[bool]  # Two TSOs published different fmax for this element

    class Config:
        strict = False
        coerce = True


class ElementEnds(pa.DataFrameModel):
    """One TSO's orientation of one physical element: the ends its DIRECT runs between.

    ``Elements`` folds the TSOs of a shared element into one row per hour, EIC and direction,
    but each TSO's ``direction`` is relative to its own ``substation_from``, and two TSOs can
    publish one tie-line from opposite ends. This table keeps every publisher's own ends.
    """

    eic: Series[str]
    tso: Series[str]
    element_type: Series[str]
    substation_from: Series[str] = pa.Field(nullable=True)
    substation_to: Series[str] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True
        unique = ["eic", "tso"]


class Contingencies(pa.DataFrameModel):
    """One row per branch of every contingency behind a presolved element."""

    hour: Series[UtcTimestamp]
    eic: Series[str]  # EIC of the monitored element, not of the outaged branch
    direction: Series[str]  # DIRECT or OPPOSITE
    cont_name: Series[str] = pa.Field(nullable=True)  # Free-text name of the whole contingency
    branch_eic: Series[str] = pa.Field(nullable=True)  # EIC of the outaged branch
    branch_name: Series[str] = pa.Field(nullable=True)  # Name of the outaged branch
    substation_from: Series[str] = pa.Field(nullable=True)  # Branch's from-end substation
    substation_to: Series[str] = pa.Field(nullable=True)  # Branch's to-end substation
    element_type: Series[str] = pa.Field(nullable=True)  # Type of the outaged branch

    class Config:
        strict = False
        coerce = True


class ShadowPrices(pa.DataFrameModel):
    """One row per binding element, direction and hour of the shadow-price feed."""

    hour: Series[UtcTimestamp]
    eic: Series[str]
    name: Series[str]
    tso: Series[str]
    direction: Series[str]
    cont_name: Series[str] = pa.Field(nullable=True)  # The contingency that made it bind
    shadow_price: Series[float]  # Welfare gain of one more MW on the element [EUR/MWh]
    ram: Series[float] = pa.Field(nullable=True)  # Remaining available margin [MW]
    fmax: Series[float] = pa.Field(nullable=True)  # Maximum admissible flow [MW]

    class Config:
        strict = False
        coerce = True


class ExternalConstraints(pa.DataFrameModel):
    """The non-physical rows of either feed: the ALEGrO external and the equality constraints.

    They carry no element, so no EIC, substations or element type — only a name and a limit.
    """

    hour: Series[UtcTimestamp]
    name: Series[str]  # e.g. "External Constraint BE_AL_export"
    tso: Series[str]  # Often empty: several of these belong to no single TSO
    direction: Series[str] = pa.Field(nullable=True)  # "NA" in the domain feed
    fmax: Series[float] = pa.Field(nullable=True)  # The constraint's limit [MW]
    ram: Series[float] = pa.Field(nullable=True)  # Margin left of it [MW]

    class Config:
        strict = False
        coerce = True


class ExternalConstraintsWithPrices(ExternalConstraints):
    """`ExternalConstraints` plus what the shadow-price feed says about each hourly row."""

    shadow_price: Series[float] = pa.Field(nullable=True)  # NaN where the constraint did not bind
    binding_direction: Series[str] = pa.Field(nullable=True)  # The sense that bound; only the price feed states it

    class Config:
        strict = False
        coerce = True


class ElementsWithPrices(Elements):
    """`Elements` plus what the shadow-price feed says about each row."""

    shadow_price: Series[float] = pa.Field(nullable=True)  # NaN where the element did not bind
    binding_contingency: Series[str] = pa.Field(nullable=True)  # Contingency named by the price feed

    class Config:
        strict = False
        coerce = True


class ActiveConstraints(pa.DataFrameModel):
    """One physical row that bound in EUPHEMIA, per market time unit and contingency."""

    source_id: Series[int] = pa.Field(unique=True)  # Stable row identifier from the publication
    interval: Series[UtcTimestamp]
    eic: Series[str]
    name: Series[str]
    tso: Series[str]
    direction: Series[str] = pa.Field(isin=["DIRECT", "OPPOSITE"])
    cont_name: Series[str] = pa.Field(nullable=True)  # Null means the base case, without contingency
    branch_eic: Series[str] = pa.Field(nullable=True)
    hub_from: Series[str]
    hub_to: Series[str]
    shadow_price: Series[float] = pa.Field(gt=0)  # Welfare gain from 1 MW more RAM [EUR/MWh]
    ram: Series[float] = pa.Field(nullable=True)  # Published RAM [MW]
    ram_mcp: Series[float] = pa.Field(nullable=True)  # RAM left at the market-clearing point [MW]

    class Config:
        strict = False
        coerce = True


class ConstraintPtdfs(pa.DataFrameModel):
    """A binding physical row's zonal PTDFs, one Core bidding zone per row."""

    source_id: Series[int]
    interval: Series[UtcTimestamp]
    eic: Series[str]
    direction: Series[str]
    cont_name: Series[str] = pa.Field(nullable=True)
    zone: Series[str]
    ptdf: Series[float]  # Change in monitored flow per MW of zonal net-position change [MW/MW]

    class Config:
        strict = False
        coerce = True


class ConstraintContributions(ConstraintPtdfs):
    """One selected row's relative zonal price contribution under an explicit reference."""

    reference_zone: Series[str]
    ptdf_difference: Series[float]
    contribution: Series[float]  # -shadow_price * ptdf_difference [EUR/MWh]

    class Config:
        strict = False
        coerce = True


class ActiveExternalConstraints(pa.DataFrameModel):
    """A binding non-spatial row, retained beside the mappable flow-based constraints."""

    interval: Series[UtcTimestamp]
    name: Series[str]
    tso: Series[str]
    direction: Series[str]
    shadow_price: Series[float] = pa.Field(gt=0)
    ram: Series[float] = pa.Field(nullable=True)
    ram_mcp: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = False
        coerce = True
