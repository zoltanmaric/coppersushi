"""Pandera schemas for the DataFrames `snapshot.py` and `power_flow.py` build on top of a
solved `pypsa.Network`.

Purely documentation: `strict = False` on every model, so extra columns pass through
untouched. Where a column is sourced straight from PyPSA (rather than computed here),
its `dtype` and unit/description are copied from PyPSA's own attribute schema
(`n.components[<Component>].defaults`); `PYPSA_SOURCED` below pins that these have not
drifted.
"""

import pandera.pandas as pa
from pandera.typing import Series


class Buses(pa.DataFrameModel):
    """One row per bus, indexed by bus name."""

    x: Series[float]  # Longitude. PyPSA: Bus.x
    y: Series[float]  # Latitude. PyPSA: Bus.y
    country: Series[str]  # PyPSA-Eur addition — not a PyPSA attribute
    v_nom: Series[float] = pa.Field(gt=0)  # Nominal voltage [kV]. PyPSA: Bus.v_nom
    p: Series[float]  # Active power at bus [MW] (+ve if net generation). PyPSA: Bus.p

    class Config:
        strict = False
        coerce = True


class Loads(pa.DataFrameModel):
    """One row per bus with a load, indexed by Bus."""

    p_load: Series[float]  # Active power consumption [MW]. Sourced from PyPSA's Load.p.

    class Config:
        strict = False
        coerce = True


class Generators(pa.DataFrameModel):
    """One row per (Bus, carrier), indexed by that MultiIndex."""

    p_nom_opt: Series[float] = pa.Field(nullable=True)  # Optimised nominal capacity [MW]. PyPSA: Generator.p_nom_opt
    p: Series[float]  # Active power [MW] (+ve if net generation). PyPSA: Generator.p
    p_max_pu: Series[float] = pa.Field(nullable=True)  # Max output, per unit of p_nom_opt. PyPSA: Generator.p_max_pu
    p_max: Series[float] = pa.Field(nullable=True)  # Ours: p_max_pu * p_nom_opt [MW]

    class Config:
        strict = False
        coerce = True


class BusCoordinates(pa.DataFrameModel):
    """Coordinates of one bus role (`bus0` or `bus1`) per branch, indexed by branch name.

    Carries no validation: the real column names are built from a `bus_name` argument
    into `<bus_name>_x`/`<bus_name>_y`, so this documents the shape before that rename
    and no static schema can describe the result.
    """

    x: Series[float]  # PyPSA: Bus.x
    y: Series[float]  # PyPSA: Bus.y

    class Config:
        strict = False
        coerce = True


class BranchInfo(pa.DataFrameModel):
    """One row per branch (Line/Link/Transformer), indexed by branch name."""

    bus0_x: Series[float]  # Ours: `BusCoordinates.x` for bus0
    bus0_y: Series[float]  # Ours: `BusCoordinates.y` for bus0
    bus1_x: Series[float]  # Ours: `BusCoordinates.x` for bus1
    bus1_y: Series[float]  # Ours: `BusCoordinates.y` for bus1
    mid_x: Series[float]  # Ours: Mercator midpoint of bus0/bus1, projected back to longitude
    mid_y: Series[float]  # Ours: Mercator midpoint of bus0/bus1, projected back to latitude
    p_max: Series[float] = pa.Field(nullable=True)  # Ours: s_max_pu * s_nom (lines) or p_max_pu * p_nom (links)
    direction: Series[float]  # Ours: geodesic bearing bus0 -> bus1, clockwise from North
    inverse_direction: Series[float]  # Ours: geodesic bearing bus1 -> bus0

    class Config:
        strict = False
        coerce = True


class BranchQuantityByComponentAndName(pa.DataFrameModel):
    """One quantity indexed by (component, name).

    Generic over `quantity`; `p0` is the column documented here, and the model carries
    no validation so another `quantity` still passes.
    """

    p0: Series[float]  # PyPSA: Line/Link/Transformer.p0

    class Config:
        strict = False
        coerce = True


class BranchInfoForSnapshot(BranchInfo):
    """`BranchInfo` plus per-snapshot flow."""

    p0: Series[float] = pa.Field(nullable=True)  # Active power at bus0 [MW]. PyPSA: Line/Link/Transformer.p0
    branch_loading: Series[float] = pa.Field(nullable=True)  # Ours: abs(p0) / p_max * 100
    arrow_angle: Series[float] = pa.Field(nullable=True)  # Ours: direction if p0 >= 0 else inverse_direction

    class Config:
        strict = False
        coerce = True


class NodeInfoForSnapshot(Buses):
    """`Buses` plus a rendered tooltip."""

    html: Series[str]  # Ours: rendered tooltip markup

    class Config:
        strict = False
        coerce = True


# Columns our models source directly from PyPSA: (our model, our column, PyPSA
# component, PyPSA attribute). Our declared dtype and PyPSA's must agree; neither side
# is hardcoded, so either drifting independently is caught.
#
# `Loads.p_load` is the one non-identity rename: it's sourced from PyPSA's `Load.p`.
#
# Two attributes we rely on are deliberately absent: `Bus.country` is a PyPSA-Eur
# addition, not a PyPSA attribute, and `Line.v_nom` is derived at runtime by
# `calculate_dependent_values`, not declared in PyPSA's schema either.
PYPSA_SOURCED = [
    (Buses, "v_nom", "Bus", "v_nom"),
    (Buses, "x", "Bus", "x"),
    (Buses, "y", "Bus", "y"),
    (Buses, "p", "Bus", "p"),
    (BranchInfoForSnapshot, "p0", "Line", "p0"),
    (BranchInfoForSnapshot, "p0", "Link", "p0"),
    (BranchInfoForSnapshot, "p0", "Transformer", "p0"),
    (Generators, "p", "Generator", "p"),
    (Generators, "p_max_pu", "Generator", "p_max_pu"),
    (Generators, "p_nom_opt", "Generator", "p_nom_opt"),
    (Loads, "p_load", "Load", "p"),
]
