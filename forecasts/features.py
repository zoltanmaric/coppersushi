"""Build model inputs at each delivery day's historical issue cutoff."""
from datetime import date, timedelta
from collections.abc import Sequence

import numpy as np

from forecasts.contracts import FloatArray, Row
from forecasts.snapshot import InputReader, WEATHER_FIELDS

CALENDAR = ["quarter_of_day", "day_of_week", "month", "public_holiday"]
PRICE = [f"price_lag_{d}" for d in (1, 2, 7, 14)] + [f"price_day_{d}_{s}" for d in (1, 7) for s in ("mean", "min", "max")]
BASE = CALENDAR + PRICE + [f + "_missing" for f in PRICE]
WEATHER = list(WEATHER_FIELDS) + [f + "_missing" for f in WEATHER_FIELDS]
FEATURES = {"prices": BASE, "weather": BASE + WEATHER,
            "demand": BASE + WEATHER + ["demand_mw", "demand_available", "demand_missing"]}



def build_features(reader: InputReader, start: date, end: date) -> list[Row]:
    """Build quarter-hour rows in [start, end), with no realised target values.

    Each day uses only inputs eligible by 11:00 Berlin on the preceding day.
    The input reader selects source versions; dataset.build_rows creates price
    lags, calendar fields, aligned weather/demand and missing-value flags.
    """
    rows = []
    day = start
    while day < end:
        rows.extend(reader.features(day))
        day += timedelta(days=1)
    return rows


def feature_matrix(rows: list[Row], fields: Sequence[str]) -> FloatArray:
    """Select the frozen feature columns, mapping missing values to NaN.

    Targets and audit metadata are excluded by the explicit column inventory.
    """
    return np.array([[np.nan if row[f] is None else row[f] for f in fields] for row in rows], dtype=float)
