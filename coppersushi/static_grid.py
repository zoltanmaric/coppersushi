"""JAO's Core Static Grid Model, turned into tidy element tables.

The workbook is the network itself — every Core line, tie-line and transformer with its
rating and its R/X/B/G — where the publication feed only ever describes the elements JAO
happened to monitor in a given hour. `EIC_Code` is the same key the feed's elements carry,
so the two join directly. Five sheets; the three that describe equipment are read here.

Four things about the sheets every consumer would otherwise re-discover:

1. **Both header rows matter.** Row one is a merged banner (`Location`, `Maximum Current
   Imax (A) primary`, `Electrical Parameters (primary) at neutral tap`, `Phase Shifting
   Properties`) and the real names are on row two, so the sheets are read with `header=1`.
2. **The current rating is `Max`, falling back to `Fixed`, then `Min`.** All 520
   transformer rows have at least one of the three; only 339 have `Max`.
3. **A row is a PST when `Theta θ (°)` is populated** — 136 of 520, and 99 of those are
   named `TR`, so the name is not the signal. The feed's own `Transformer`/`PST` split
   disagrees with the workbook's in both directions; θ is what the workbook itself states.
4. **`eic` is not a key.** Two RTE pairs share one EIC while differing in rating and
   impedance, a tie-line is published once per TSO owning an end, and 29 line rows carry
   no EIC at all. Every row is kept; nothing is grouped away.

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
            "x": _numeric(rows, "reactancex"),
            "b": _numeric(rows, "susceptancebs"),
            "g": _numeric(rows, "conductancegs"),
            "theta": theta,
            "is_pst": theta.notna(),
        }
    ).pipe(Transformers.validate)


def _branch_side(rows: pd.DataFrame, is_tieline: bool) -> pd.DataFrame:
    seasonal = pd.concat([_numeric(rows, period) for period in SEASONAL_PERIODS], axis=1)
    return pd.DataFrame(
        {
            # `Substation_1` and `Substation_2` are both headed `Full_name`, which pandas
            # de-duplicates into `Full_name` and `Full_name.1` in sheet order.
            "eic": _column(rows, "eiccode").astype("string").str.strip(),
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
            "x": _numeric(rows, "reactancex"),
            "b": _numeric(rows, "susceptancebs"),
            "length_km": _numeric(rows, "lengthkm"),
            "is_tieline": is_tieline,
        }
    )


def branches(lines: pd.DataFrame, tielines: pd.DataFrame) -> DataFrame[Branches]:
    """The `Lines` and `Tielines` sheets as one table, each row saying which it came from."""
    return pd.concat(
        [_branch_side(lines, is_tieline=False), _branch_side(tielines, is_tieline=True)],
        ignore_index=True,
    ).pipe(Branches.validate)
