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


# Opposite Nordic endpoints in the published market topology.
NORDIC_HUBS = {
    "NL_DK1_COBRA": "DK1_CO", "NL_NO2_NorNed": "NO2_ND",
    "DE_NO2_BigHub": "NO2_NK", "PL_SE4_SwePol": "SE4_SP",
    "DE_SE4_Baltic": "SE4_BC", "DE_DK1_VH": "DK1_DE", "DE_DK2_BigHub": "DK2_KO",
}


def nordic_outer_term(rows: list[dict], hub: str, interval: pd.Timestamp) -> float | None:
    """Published Nordic virtual-minus-country potential, with no Core α scaling.

    Compare endpoints within the same synchronous group; Nordic groups do not share
    one balance-price constant. An entirely missing shadow-price column is unavailable.
    """
    virtual = NORDIC_HUBS.get(hub)
    if virtual is None or not rows:
        return None
    other = INTERFACES[hub][1]
    frame = pd.DataFrame(rows)
    required = {"id", "dateTimeUtc", "shadowPrice", f"ptdf_{virtual}", f"ptdf_{other}"}
    if not required.issubset(frame) or frame.id.duplicated().any():
        return None
    if not pd.to_datetime(frame.dateTimeUtc, utc=True, errors="coerce").eq(interval).all():
        return None
    duals = pd.to_numeric(frame.shadowPrice, errors="coerce")
    if not duals.notna().any() or (duals.dropna() < 0).any():
        return None
    active = frame[duals.gt(0)]
    coefficients = active[[f"ptdf_{virtual}", f"ptdf_{other}"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(coefficients.to_numpy()).all() or not np.isfinite(duals.dropna()).all():
        return None
    difference = coefficients[f"ptdf_{virtual}"] - coefficients[f"ptdf_{other}"]
    return float(-(duals.loc[active.index] * difference).sum())


def interface_spread(core_outer: float, bound_term: float, adjacent_outer: float,
                     country_cap: float = 0.0) -> float:
    """Owner-minus-adjacent spread; every argument is an independent signed €/MWh term."""
    return core_outer + bound_term + adjacent_outer + country_cap


# Nord Pool documents implicit-loss pricing on these links. A lossless match alone
# cannot validate how a selected dual scales between sending and receiving MWh.
LOSS_HUBS = {'NL_NO2_NorNed', 'DE_NO2_BigHub', 'DE_SE4_Baltic'}


def virtual_validated(hub: str, ptdfs: pd.DataFrame, physical: pd.DataFrame,
                      external: pd.DataFrame, prices: pd.DataFrame, inputs: pd.DataFrame | None,
                      alpha: float, adjacent: pd.Series) -> bool:
    """Require the complete candidate endpoint decomposition to match published prices.

    Loss/ramping terms are not inferred from the residual. An unexplained residual rejects
    attribution for this interval while retaining selection and the published bound dual.
    """
    if hub not in INTERFACES or hub in {"ALBE", "ALDE"} or hub in LOSS_HUBS or not 0 < alpha <= 1:
        return False
    owner, _, _ = INTERFACES[hub]
    quoted = prices[prices.zone.eq(owner)]
    if len(quoted) != 1:
        return False
    values = [quoted.price.iloc[0], adjacent.adjacent_price, adjacent.adjacent_term]
    if not np.isfinite(values).all():
        return False
    required = ptdfs[ptdfs.source_id.isin(physical.source_id) & ptdfs.zone.isin([owner, hub])]
    if required.duplicated(['source_id', 'zone']).any() or len(required) != 2 * len(physical):
        return False
    terms = required.merge(physical[['source_id', 'shadow_price']], on='source_id', validate='many_to_one')
    if not np.isfinite(terms[['ptdf', 'shadow_price']].to_numpy()).all():
        return False
    signed = terms.ptdf * np.where(terms.zone.eq(owner), -1, 1)
    core = float((signed * terms.shadow_price / alpha).sum())
    bounds = external[external.hub.eq(hub)]
    if bounds.empty or not bounds.coefficient.isin([-1, 1]).all() or not np.isfinite(bounds.shadow_price).all():
        return False
    middle = float((bounds.coefficient * bounds.shadow_price / alpha).sum())
    cap = 0.0
    if owner == 'PL':
        if inputs is None or len(inputs) != 1 or not np.isfinite(inputs.polish_alt.iloc[0]):
            return False
        cap = country_cap_effect(float(quoted.price.iloc[0]), float(inputs.polish_alt.iloc[0]))
        if abs(cap) > 1e-9:
            if not {'interval', 'polish_position', 'import_limit', 'export_limit'}.issubset(inputs):
                return False
            if country_caps(inputs, prices, inputs.interval.iloc[0]).empty:
                return False
    predicted = interface_spread(core, middle, float(adjacent.adjacent_term), cap)
    observed = float(quoted.price.iloc[0] - adjacent.adjacent_price)
    return abs(predicted - observed) <= 0.02
