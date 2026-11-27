"""Build model inputs from eligible prices and the Berlin delivery calendar."""
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import cast

import numpy as np
from pandera.typing.polars import DataFrame
import polars as pl

from forecasts.inputs.selection import PriceHistoryReader
from forecasts.market import cutoff, issue_deadline, quarters, require_quarters
from forecasts.model.calendar import assemble_price_calendar
from forecasts.model.contracts import FloatArray
from forecasts.model.coverage import require_static_features
from forecasts.config import LAGS
from forecasts.model.price_features import build_price_features
from forecasts.model.tables import Features


def build_features(reader: PriceHistoryReader, start: date, end: date, *,
                   complete_from: date | None = None) -> DataFrame[Features]:
    """Build historical features in [start, end) at each day's issue cutoff."""
    if start >= end:
        raise ValueError("Feature start must precede end")
    days = (start + timedelta(days=offset) for offset in range((end - start).days))
    rows = Features.validate(pl.concat([
        _day_features(reader, day, cutoff(day), False, complete_from is not None and day >= complete_from)
        for day in days
    ]))
    if complete_from is not None:
        checked = cast(DataFrame[Features], rows.filter(pl.col("delivery_date") >= complete_from))
        require_static_features(checked, max(start, complete_from), end)
    return rows


def build_day_features(reader: PriceHistoryReader, day: date, live: bool = False,
                       issue_time: datetime | None = None, *,
                       require_complete: bool = False) -> DataFrame[Features]:
    """Build one day from eligible prices, using the actual issue time in live mode."""
    deadline = issue_deadline(day, live, issue_time)
    rows = Features.validate(_day_features(reader, day, deadline, live, require_complete))
    if require_complete:
        require_static_features(rows, day, day + timedelta(days=1))
    return rows


def feature_matrix(rows: DataFrame[Features], fields: Sequence[str]) -> FloatArray:
    """Select the frozen feature columns, mapping missing values to NaN."""
    return rows.select(fields).to_numpy().astype(np.float64, copy=False)


def _day_features(reader: PriceHistoryReader, day: date, deadline: datetime, live: bool,
                  require_complete: bool) -> pl.DataFrame:
    history = reader.price_history(day, deadline, live=live, earliest_day=day - timedelta(days=max(LAGS)))
    if require_complete:
        observed = {timestamp for timestamp, value in history.iter_rows() if value is not None}
        for lag in LAGS:
            lag_day = day - timedelta(days=lag)
            stop = lag_day + timedelta(days=1)
            require_quarters((timestamp for timestamp in quarters(lag_day, stop) if timestamp in observed),
                             lag_day, stop,
                             f"Eligible prices at {deadline.isoformat()} for delivery {day} (D-{lag})")
    prices = build_price_features(history, list(quarters(day, day + timedelta(days=1))))
    return assemble_price_calendar(prices)
