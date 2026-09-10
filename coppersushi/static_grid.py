"""JAO's Core Static Grid Model, turned into tidy element tables.

The workbook is the network itself — every Core line, tie-line and transformer with its
rating and its R/X/B/G — where the publication feed only ever describes the elements JAO
happened to monitor in a given hour. `EIC_Code` is the same key the feed's elements carry,
so the two join directly. Five sheets; the three that describe equipment are read here.

Five things about the sheets every consumer would otherwise re-discover:

1. **Both header rows matter.** Row one is a merged banner (`Location`, `Maximum Current
   Imax (A) primary`, `Electrical Parameters (primary) at neutral tap`, `Phase Shifting
   Properties`) and the real names are on row two, so the sheets are read with `header=1`.
2. **The current rating is `Max`, falling back to `Fixed`, then `Min`.** All 520
   transformer rows have at least one of the three; only 339 have `Max`.
3. **A row is a PST when `Theta θ (°)` is populated** — 136 of 520, and 99 of those are
   named `TR`, so the name is not the signal. The feed's own `Transformer`/`PST` split
   disagrees with the workbook's in both directions; θ is what the workbook itself states.
4. **`eic` is not a key.** Two RTE pairs share one EIC while differing in rating and
   impedance, a tie-line is published once per TSO owning an end, and 32 line rows carry
   no EIC at all — 29 blank and three written `N.A.`, blanked here so the key is either
   an EIC or nothing. Every row is kept; nothing is grouped away, so a plain
   `merge(on="eic")` would silently double rows — `join_on_eic` refuses to.
5. **A published reactance is not always a usable one.** One transformer of the 5th
   release has x = −11.7 Ω and one line has x = 0, which in a power flow is a short
   circuit rather than a small impedance. Neither is dropped or repaired here — the
   workbook says what it says — but both are flagged `x_physical = False`, so a consumer
   dividing by `x` has to choose rather than inherit.

Column names are matched on their letters and digits alone, because the workbook spells
the same unit differently from sheet to sheet — `Susceptance_B(μS)` on `Lines` uses GREEK
SMALL LETTER MU and `Susceptance_B (µS)` on `Transformers` uses MICRO SIGN — and both
ohm headers use OHM SIGN rather than the Greek omega an editor would type.

Design: `wiki/specs/jao-grid.md`.
"""

import re

import numpy as np
import pandas as pd
from pandera.typing import DataFrame

from coppersushi.data_model.static_grid import Branches, Transformers

RELEASE = "2024-03-29"  # The 5th release, the one in force on 2024-08-29
SHEETS = ("Lines", "Tielines", "Transformers")
HEADER_ROW = 1  # Zero-based: the second row carries the real column names

SEASONAL_PERIODS = tuple(f"period{n}" for n in range(1, 7))
RATING_PREFERENCE = ("max", "fixed", "min")  # Best available thermal limit, in order
EIC_PLACEHOLDER = "N.A."  # What the `Lines` sheet writes where a row has no EIC


def _key(column: str) -> str:
    """A column name reduced to its letters and digits, lower case."""
    return re.sub(r"[^a-z0-9]", "", column.lower())


def _column(frame: pd.DataFrame, key: str) -> pd.Series:
    """The sheet column whose name reduces to `key`."""
    matches = [column for column in frame.columns if _key(column) == key]
    if len(matches) != 1:
        raise KeyError(f"{key}: matched {matches} of {list(frame.columns)}")
    return frame[matches[0]]


def _numeric(frame: pd.DataFrame, key: str) -> pd.Series:
    return pd.to_numeric(_column(frame, key), errors="coerce")


def _text(frame: pd.DataFrame, key: str) -> pd.Series:
    return _column(frame, key).astype("string").fillna("").str.strip()


def _x_physical(x: pd.Series) -> pd.Series:
    """Whether a published reactance can be turned into a per-unit impedance."""
    return x.notna() & x.gt(0)


def eic_collisions(table: pd.DataFrame) -> pd.DataFrame:
    """The rows sharing an `eic` with another row, ordered by it. Empty when `eic` is a key."""
    shared = table.eic.notna() & table.eic.duplicated(keep=False)
    return table[shared].sort_values("eic")


def join_on_eic(elements: pd.DataFrame, table: pd.DataFrame) -> pd.DataFrame:
    """Left-join `table` onto `elements` on `eic`, refusing to return more rows than it was given.

    `eic` is not a key on either static-grid table, so `elements.merge(table, on="eic")`
    silently duplicates every element whose EIC collides. This raises instead, naming the
    EICs, and leaves the caller to pick a row with `eic_collisions`.
    """
    joined = elements.merge(table, on="eic", how="left", suffixes=("", "_sgm"))
    if len(joined) != len(elements):
        collide = sorted(set(eic_collisions(table).eic) & set(elements.eic))
        raise ValueError(f"eic is not a key: {len(collide)} EICs would multiply rows: {collide}")
    return joined


def s_nom(u_kv: pd.Series, imax_a: pd.Series) -> pd.Series:
    """Three-phase apparent power [MVA] of a thermal current limit at a nominal voltage."""
    return np.sqrt(3) * u_kv * imax_a / 1000


def _imax(rows: pd.DataFrame) -> pd.Series:
    """`Max`, else `Fixed`, else `Min` — raising rather than emitting a rating-less row."""
    candidates = [_numeric(rows, key) for key in RATING_PREFERENCE]
    rating = candidates[0]
    for fallback in candidates[1:]:
        rating = rating.fillna(fallback)
    if rating.isna().any():
        missing = _text(rows, "fullname")[rating.isna()].tolist()
        raise ValueError(f"no current rating on {len(missing)} transformer rows: {missing[:5]}")
    return rating


def transformers(rows: pd.DataFrame) -> DataFrame[Transformers]:
    """The `Transformers` sheet as one rated, impedance-bearing row per workbook row."""
    imax = _imax(rows)
    u_primary = _numeric(rows, "primary")
    theta = _numeric(rows, "theta")
    x = _numeric(rows, "reactancex")
    return pd.DataFrame(
        {
            "eic": _text(rows, "eiccode"),
            "name": _text(rows, "fullname"),
            "tso": _text(rows, "tso"),
            "u_primary": u_primary,
            "u_secondary": _numeric(rows, "secondary"),
            "imax": imax,
            "s_nom": s_nom(u_primary, imax),
            "r": _numeric(rows, "resistancer"),
            "x": x,
            "b": _numeric(rows, "susceptancebs"),
            "g": _numeric(rows, "conductancegs"),
            "theta": theta,
            "is_pst": theta.notna(),
            "x_physical": _x_physical(x),
        }
    ).pipe(Transformers.validate)


def _branch_side(rows: pd.DataFrame, is_tieline: bool) -> pd.DataFrame:
    seasonal = pd.concat([_numeric(rows, period) for period in SEASONAL_PERIODS], axis=1)
    x = _numeric(rows, "reactancex")
    return pd.DataFrame(
        {
            # `Substation_1` and `Substation_2` are both headed `Full_name`, which pandas
            # de-duplicates into `Full_name` and `Full_name.1` in sheet order.
            "eic": _column(rows, "eiccode").astype("string").str.strip().replace(EIC_PLACEHOLDER, pd.NA),
            "name": _text(rows, "nename"),
            "tso": _text(rows, "tso"),
            "substation_from": _text(rows, "fullname"),
            "substation_to": _text(rows, "fullname1"),
            "u": _numeric(rows, "voltagelevelkv"),
            "imax_fixed": _numeric(rows, "fixed"),
            "imax_seasonal": seasonal.max(axis=1),
            "dlr_min": _numeric(rows, "dlrmina"),
            "dlr_max": _numeric(rows, "dlrmaxa"),
            "r": _numeric(rows, "resistancer"),
            "x": x,
            "b": _numeric(rows, "susceptancebs"),
            "length_km": _numeric(rows, "lengthkm"),
            "is_tieline": is_tieline,
            "x_physical": _x_physical(x),
        }
    )


def branches(lines: pd.DataFrame, tielines: pd.DataFrame) -> DataFrame[Branches]:
    """The `Lines` and `Tielines` sheets as one table, each row saying which it came from."""
    return pd.concat(
        [_branch_side(lines, is_tieline=False), _branch_side(tielines, is_tieline=True)],
        ignore_index=True,
    ).pipe(Branches.validate)
