"""Pandera schemas for the tidy tables `static_grid.py` builds out of JAO's Core Static Grid Model.

Units are the workbook's: kV, A, MVA, ohms and microsiemens at the primary side, degrees, km.
Both producers build a fresh frame, so these columns are all there is; `strict = False`
matches `data_model/jao.py` and lets a consumer add its own columns without re-validating.
"""

import pandera.pandas as pa
from pandera.typing import Series


class Transformers(pa.DataFrameModel):
    """One row per transformer row of the `Transformers` sheet, rated and impedance-bearing.

    Not keyed on `eic`: two French pairs share an EIC while differing in rating and
    impedance, and both rows are kept rather than one of them silently dropped. Join with
    `static_grid.join_on_eic`, which refuses to multiply rows, rather than `merge`.

    `x_physical` is false where the published reactance cannot be a per-unit impedance —
    negative, zero or absent. One row of the 5th release is negative.
    """

    eic: Series[str] = pa.Field(unique=False)  # EIC_Code; the feed's key, but not unique here
    name: Series[str]  # The TSO's own name for the transformer
    tso: Series[str]  # Owning TSO, as the workbook spells it
    u_primary: Series[float]  # Primary nominal voltage [kV]
    u_secondary: Series[float]  # Secondary nominal voltage [kV]
    imax: Series[float]  # Thermal current limit at the primary side [A]
    s_nom: Series[float]  # √3 · u_primary · imax, the nameplate apparent power [MVA]
    r: Series[float]  # Resistance at neutral tap, primary side [Ω]
    x: Series[float]  # Reactance at neutral tap, primary side [Ω]; one RTE row publishes −11.7
    b: Series[float] = pa.Field(nullable=True)  # Susceptance [µS]; RTE publishes none
    g: Series[float] = pa.Field(nullable=True)  # Conductance [µS]; RTE publishes none
    theta: Series[float] = pa.Field(nullable=True)  # Phase-shift angle θ [°]; NaN on a plain transformer
    is_pst: Series[bool]  # Whether θ is published at all
    x_physical: Series[bool]  # Whether `x` can be turned into a per-unit impedance

    class Config:
        strict = False
        coerce = True


class Branches(pa.DataFrameModel):
    """One row per row of the `Lines` and `Tielines` sheets, concatenated.

    Neither sheet is keyed on `eic` either: a tie-line is published once per TSO that owns
    an end, and 29 line rows carry no EIC at all. `x_physical` means what it means on
    `Transformers`; one line of the 5th release publishes a reactance of exactly zero,
    which is a short circuit rather than a small impedance.
    """

    eic: Series[str] = pa.Field(nullable=True, unique=False)  # EIC_Code, absent on some line rows
    name: Series[str]  # NE_name, the TSO's own name
    tso: Series[str]
    substation_from: Series[str]  # Substation_1 — a name, never a coordinate
    substation_to: Series[str]  # Substation_2
    u: Series[float]  # Nominal voltage [kV]
    imax_fixed: Series[float] = pa.Field(nullable=True)  # Season-independent current limit [A]
    imax_seasonal: Series[float] = pa.Field(nullable=True)  # Highest of the six seasonal periods [A]
    dlr_min: Series[float] = pa.Field(nullable=True)  # Dynamic line rating, lower bound [A]
    dlr_max: Series[float] = pa.Field(nullable=True)  # Dynamic line rating, upper bound [A]
    r: Series[float] = pa.Field(nullable=True)  # Resistance [Ω]
    x: Series[float] = pa.Field(nullable=True)  # Reactance [Ω]
    b: Series[float] = pa.Field(nullable=True)  # Susceptance [µS]
    length_km: Series[float] = pa.Field(nullable=True)  # Circuit length [km]
    is_tieline: Series[bool]  # Which of the two sheets the row came from
    x_physical: Series[bool]  # Whether `x` can be turned into a per-unit impedance

    class Config:
        strict = False
        coerce = True
