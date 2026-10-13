"""Validated normalized-FB attribution inputs and explicit virtual-interface mapping."""

from typing import NamedTuple

import numpy as np
import pandas as pd
from shapely.geometry import Point

from coppersushi.market import CORE_ZONES
from coppersushi.market_day import MarketDay

# Owning Core end, adjacent bidding zone, asset. ALBE/ALDE share one physical asset.
INTERFACES = {
    "ALBE": ("BE", "DE", "ALEGrO"), "ALDE": ("DE", "BE", "ALEGrO"),
    "NL_DK1_COBRA": ("NL", "DK1", "COBRA"),
    "NL_NO2_NorNed": ("NL", "NO2", "NorNed"),
    "DE_NO2_BigHub": ("DE", "NO2", "NordLink"),
    "PL_SE4_SwePol": ("PL", "SE4", "SwePol"),
    "DE_SE4_Baltic": ("DE", "SE4", "Baltic Cable"),
    "PL_LT_BigHub": ("PL", "LT", "LitPol AC interface"),
    "DE_DK1_VH": ("DE", "DK1", "DE–DK1 AC interface"),
    "DE_DK2_BigHub": ("DE", "DK2", "Kontek / Kriegers Flak interface"),
    "RO_BG_VH": ("RO", "BG", "RO–BG AC interface"),
}
# Label anchors only: schematic interfaces do not claim a cable route or converter location.
ADJACENT_ANCHORS = {"DK1": (9.1, 56.1), "DK2": (12.0, 55.6), "NO2": (7.4, 58.6),
                    "SE4": (14.2, 56.2), "LT": (24.0, 55.2), "BG": (25.3, 42.7)}


def context(day: MarketDay, alpha_rows: list[dict], cap_rows: list[dict],
            position_rows: list[dict], polish_rows: list[dict]) -> pd.DataFrame:
    """Align public feeds; reconstruct PL quarters only with IDs and an NP cross-check.

    Each incomplete or ambiguous input remains missing. Historical hourly PL support is
    deliberately unavailable: the empirical adapter was validated only after MTU change.
    """
    result = pd.DataFrame({"interval": day.market_time_units()})
    for rows, fields in [(alpha_rows, {"alphaFactor": "alpha"}),
                         (cap_rows, {"limitDown_PL": "import_limit", "limitUp_PL": "export_limit"}),
                         (position_rows, {"hub_PL": "polish_position"})]:
        frame = pd.DataFrame(rows)
        if frame.empty or not set(fields).issubset(frame):
            for column in fields.values():
                result[column] = np.nan
            continue
        frame = frame.assign(interval=pd.to_datetime(frame.dateTimeUtc, utc=True))
        frame = frame[~frame.interval.duplicated(keep=False)]
        result = result.merge(frame[["interval", *fields]].rename(columns=fields),
                              on="interval", how="left", validate="one_to_one")
    result["polish_alt"] = np.nan
    polish = pd.DataFrame(polish_rows)
    required = {"id", "dateTimeUtc", "border_PL_ALT", "border_PL_SDAC_NP"}
    if not required.issubset(polish) or len(day.market_time_units()) <= 25:
        return result
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
    return result


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


def country_caps(inputs: pd.DataFrame, prices: pd.DataFrame, interval: pd.Timestamp) -> pd.DataFrame:
    """Only a saturated PL cap with a correctly signed, nonzero validated dual is binding."""
    columns = ["source_id", "interval", "name", "shadow_price", "direction", "capacity", "delta"]
    if inputs is None or inputs.empty:
        return pd.DataFrame(columns=columns)
    rows = inputs[inputs.interval.eq(interval)]
    price = prices[prices.interval.eq(interval) & prices.zone.eq("PL")]
    if len(rows) != 1 or len(price) != 1:
        return pd.DataFrame(columns=columns)
    row = rows.iloc[0]
    delta = country_cap_effect(float(price.price.iloc[0]), float(row.polish_alt))
    if not np.isfinite(delta) or abs(delta) <= 1e-9:
        return pd.DataFrame(columns=columns)
    if delta < 0 and abs(row.polish_position - row.export_limit) <= 0.051:
        identity, sense, capacity = -2, "export", row.export_limit
    elif delta > 0 and abs(row.polish_position + row.import_limit) <= 0.051:
        identity, sense, capacity = -1, "import", row.import_limit
    else:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame([[identity, interval, f"Poland aggregate {sense} cap", abs(delta), sense,
                          capacity, delta]], columns=columns)


def physical_reference(row: pd.Series, geometries: pd.DataFrame, zones: pd.DataFrame) -> str | None:
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
    candidates = [z.zone for z in zones.itertuples() if z.geometry.covers(point)]
    return candidates[0] if len(candidates) == 1 and candidates[0] in CORE_ZONES else None


def virtual_reference(row: pd.Series) -> str | None:
    """Positive virtual injection enters Core; a negative bound limits export from Core."""
    mapping = INTERFACES.get(row.hub)
    if mapping is None or row.coefficient not in (-1, 1):
        return None
    owner, other, _ = mapping
    return other if row.coefficient == 1 else owner


def alegro_validated(ptdfs: pd.DataFrame, physical: pd.DataFrame, external: pd.DataFrame,
                     prices: pd.DataFrame, alpha: float) -> bool:
    """Independent virtual-hub stationarity and observed endpoint-spread checks.

    Keep distinct source duals at both ALEGrO ends. They are terms of one cap's total
    effect, not duplicate rows just because they refer to the same cable.
    """
    if not 0 < alpha <= 1:
        return False
    terms = ptdfs.merge(physical[["source_id", "shadow_price"]], on="source_id", validate="many_to_one")
    potentials = (-terms.ptdf * terms.shadow_price / alpha).groupby(terms.zone).sum()
    if not {"ALBE", "ALDE", "BE", "DE"}.issubset(potentials.index):
        return False
    bounds = external[external.hub.isin(["ALBE", "ALDE"])]
    if not bounds.coefficient.isin([-1, 1]).all():
        return False
    signed = bounds.shadow_price * bounds.coefficient / alpha
    middle = signed[bounds.hub.eq("ALDE")].sum() - signed[bounds.hub.eq("ALBE")].sum()
    stationarity = potentials.ALDE - potentials.ALBE - middle
    quotes = prices.set_index("zone").price
    if not {"BE", "DE"}.issubset(quotes.index):
        return False
    observed = quotes.DE - quotes.BE
    reconstructed = (potentials.ALBE - potentials.BE) + middle + (potentials.DE - potentials.ALDE)
    return abs(stationarity) <= 0.02 and abs(observed - reconstructed) <= 0.02
