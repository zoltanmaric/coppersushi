"""Pandera schemas for the tidy tables `static_grid.py` builds out of JAO's Core Static Grid Model.

Units are the workbook's: kV, A, MVA, ohms and microsiemens at the primary side, degrees, km.
`strict = False` throughout, so a caller may carry extra workbook columns through.
"""

import pandera.pandas as pa
from pandera.typing import Series


class Transformers(pa.DataFrameModel):
    """One row per transformer row of the `Transformers` sheet, rated and impedance-bearing.

    Not keyed on `eic`: two French pairs share an EIC while differing in rating and
    impedance, and both rows are kept rather than one of them silently dropped.
    """

    eic: Series[str]  # EIC_Code; the same key the publication feed's elements carry
    name: Series[str]  # The TSO's own name for the transformer
    tso: Series[str]  # Owning TSO, as the workbook spells it
    u_primary: Series[float]  # Primary nominal voltage [kV]
    u_secondary: Series[float]  # Secondary nominal voltage [kV]
    imax: Series[float]  # Thermal current limit at the primary side [A]
    s_nom: Series[float]  # √3 · u_primary · imax, the nameplate apparent power [MVA]
    r: Series[float]  # Resistance at neutral tap, primary side [Ω]
    x: Series[float]  # Reactance at neutral tap, primary side [Ω]
    b: Series[float] = pa.Field(nullable=True)  # Susceptance [µS]; RTE publishes none
    g: Series[float] = pa.Field(nullable=True)  # Conductance [µS]; RTE publishes none
    theta: Series[float] = pa.Field(nullable=True)  # Phase-shift angle θ [°]; NaN on a plain transformer
    is_pst: Series[bool]  # Whether θ is published at all

    class Config:
        strict = False
        coerce = True


class Branches(pa.DataFrameModel):
    """One row per row of the `Lines` and `Tielines` sheets, concatenated.

    Neither sheet is keyed on `eic` either: a tie-line is published once per TSO that owns
    an end, and 29 line rows carry no EIC at all.
    """

    eic: Series[str] = pa.Field(nullable=True)  # EIC_Code, absent on some line rows
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

    class Config:
        strict = False
        coerce = True
