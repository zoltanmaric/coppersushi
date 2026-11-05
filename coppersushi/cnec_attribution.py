"""Validated normalized-FB attribution inputs."""

from typing import NamedTuple
from collections.abc import Sequence

import numpy as np
import pandas as pd
from shapely.geometry import Point
from pandera.typing import DataFrame

from coppersushi.data_model.cnec_attribution import (
    AlphaFactor, AllocationConstraint, NetPosition, PolishAlternative, AttributionContext, CountryCaps,
)

from coppersushi.data_model.market import ZonalPrices
from coppersushi.data_model.cnec_price_map import MappedCnecElements
from coppersushi.data_model.network_views import BiddingZoneShapes
from coppersushi.market import CORE_ZONES
from coppersushi.market_day import MarketDay

def context(day: MarketDay, alpha_rows: list[AlphaFactor], cap_rows: list[AllocationConstraint],
            position_rows: list[NetPosition], polish_rows: list[PolishAlternative]) -> DataFrame[AttributionContext]:
    """Align public feeds; reconstruct PL quarters only with IDs and an NP cross-check.

    Each incomplete or ambiguous input remains missing. Historical hourly PL support is
    deliberately unavailable: the empirical adapter was validated only after MTU change.
    """
    result = pd.DataFrame({"interval": day.market_time_units()})
    feeds: list[tuple[Sequence[AlphaFactor | AllocationConstraint | NetPosition], dict[str, str]]] = [
        (alpha_rows, {"alphaFactor": "alpha"}),
        (cap_rows, {"limitDown_PL": "import_limit", "limitUp_PL": "export_limit"}),
        (position_rows, {"hub_PL": "polish_position"}),
    ]
    for rows, fields in feeds:
        frame = pd.DataFrame([row.model_dump() for row in rows])
        if frame.empty or not set(fields).issubset(frame):
            for column in fields.values():
                result[column] = np.nan
            continue
        frame = frame.assign(interval=pd.to_datetime(frame.dateTimeUtc, utc=True))
        frame = frame[~frame.interval.duplicated(keep=False)]
        result = result.merge(frame[["interval", *fields]].rename(columns=fields),
                              on="interval", how="left", validate="one_to_one")
    result["polish_alt"] = np.nan
    polish = pd.DataFrame([row.model_dump() for row in polish_rows])
    required = {"id", "dateTimeUtc", "border_PL_ALT", "border_PL_SDAC_NP"}
    if not required.issubset(polish) or len(day.market_time_units()) <= 25:
        return AttributionContext.validate(result)
    polish = polish.assign(hour=pd.to_datetime(polish.dateTimeUtc, utc=True))
    polish = polish.sort_values("id")
    counts = polish.groupby("hour").id.transform("size")
    unique = polish.groupby("hour").id.transform("nunique").eq(4)
    unique &= ~polish.id.duplicated(keep=False).groupby(polish.hour).transform("any")
    rank = polish.groupby("hour").cumcount()
    polish = polish.assign(interval=polish.hour + pd.to_timedelta(rank * 15, unit="min"))
    polish = polish[counts.eq(4) & unique & polish.hour.eq(polish.hour.dt.floor("h"))]
    # Repeated NP values are allowed; all quarter positions must still independently agree.
    matched = result.merge(polish[["interval", "border_PL_ALT", "border_PL_SDAC_NP"]],
                           on="interval", how="left", validate="one_to_one")
    valid = (matched.polish_position - matched.border_PL_SDAC_NP).abs().le(0.051)
    result["polish_alt"] = matched.border_PL_ALT.where(valid)
    return AttributionContext.validate(result)


class PriceSpread(NamedTuple):
    """Signed €/MWh terms for other-zone price minus reference-zone price."""

    observed: float
    selected: float
    remainder: float


def country_cap_effect(country_price: float, adjusted_price: float) -> float:
    """The cap's signed effect on its country's price; retain source precision."""
    return country_price - adjusted_price


def price_spread(reference_price: float, other_price: float, contribution: float) -> PriceSpread:
    """Separate the observed spread from one selected term, without rounding either.

    The remainder includes other constraints and discrepancies between price publications.
    A selected term need not equal, or be smaller than, the observed spread.
    """
    observed = other_price - reference_price
    return PriceSpread(observed, contribution, observed - contribution)


# Published positions can differ from a binding limit by 0.1 MW.
# See wiki/country-import-export-caps.md#poland-validation.
POSITION_TOLERANCE_MW = 0.11


def polish_cap_attribution_unavailable(position: float, import_limit: float,
                                       export_limit: float, alternative_price: float,
                                       clearing_price: float) -> bool:
    """Prices are required only if a limit might bind."""
    if not all(np.isfinite(value) for value in (position, import_limit, export_limit)):
        return True
    strictly_inside = (-import_limit + POSITION_TOLERANCE_MW < position
                       < export_limit - POSITION_TOLERANCE_MW)
    return not strictly_inside and not all(np.isfinite(value) for value in (alternative_price, clearing_price))


def country_caps[Prices: ZonalPrices](inputs: DataFrame[AttributionContext] | None, prices: DataFrame[Prices], interval: pd.Timestamp) -> DataFrame[CountryCaps]:
    """Only a saturated PL cap with a correctly signed, nonzero validated dual is binding."""
    columns = ["source_id", "interval", "name", "shadow_price", "direction", "capacity", "delta"]
    if inputs is None or inputs.empty:
        return CountryCaps.validate(pd.DataFrame(columns=columns).assign(
            interval=pd.Series([], dtype="datetime64[ns, UTC]")))
    rows = inputs[inputs.interval.eq(interval)]
    price = prices[prices.interval.eq(interval) & prices.zone.eq("PL")]
    if len(rows) != 1 or len(price) != 1:
        return CountryCaps.validate(pd.DataFrame(columns=columns).assign(
            interval=pd.Series([], dtype="datetime64[ns, UTC]")))
    row = rows.iloc[0]
    delta = country_cap_effect(float(price.price.iloc[0]), float(row.polish_alt))
    if not np.isfinite(delta) or abs(delta) <= 1e-9:
        return CountryCaps.validate(pd.DataFrame(columns=columns).assign(
            interval=pd.Series([], dtype="datetime64[ns, UTC]")))
    if delta < 0 and abs(row.polish_position - row.export_limit) <= POSITION_TOLERANCE_MW:
        identity, sense, capacity = -2, "export", row.export_limit
    elif delta > 0 and abs(row.polish_position + row.import_limit) <= POSITION_TOLERANCE_MW:
        identity, sense, capacity = -1, "import", row.import_limit
    else:
        return CountryCaps.validate(pd.DataFrame(columns=columns).assign(
            interval=pd.Series([], dtype="datetime64[ns, UTC]")))
    return pd.DataFrame([[identity, interval, f"Poland aggregate {sense} cap", abs(delta), sense,
                          capacity, delta]], columns=columns).pipe(CountryCaps.validate)


def physical_reference(row: pd.Series, geometries: DataFrame[MappedCnecElements], zones: DataFrame[BiddingZoneShapes]) -> str | None:
    """Reference the publisher-oriented sending endpoint, requiring unique zone coverage."""
    matched = geometries[geometries.eic.eq(row.eic) & geometries.tso.eq(row.tso)
                         & geometries.name.eq(row['name'])]
    if len(matched) != 1 or matched.iloc[0].match_status != "matched":
        return None
    mapped = matched.iloc[0]
    if row.direction not in {"DIRECT", "OPPOSITE"}:
        return None
    end = 0 if row.direction == "DIRECT" else 1
    point = Point(mapped[f"x{end}"], mapped[f"y{end}"])
    candidates = [zone for zone, geometry in zip(zones.zone, zones.geometry) if geometry.covers(point)]
    return candidates[0] if len(candidates) == 1 and candidates[0] in CORE_ZONES else None
