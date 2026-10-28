"""Training-only calibration and prediction for the simple price reference."""
from collections import defaultdict
from datetime import date, datetime

import numpy as np

from forecasts.config import RunConfig
from forecasts.contracts import FloatArray, Reference
from pandera.typing.polars import DataFrame
from forecasts.tables import Features
from forecasts.dataset import BERLIN
from forecasts.scoring import QUANTILES
from forecasts.snapshot import InputReader
from forecasts.labels import select_labels


def fit_reference(reader: InputReader, rows: DataFrame[Features], y: FloatArray,
                  fit_day: date, config: RunConfig) -> Reference:
    """Calibrate five error offsets using eligible training labels only.

    Historical fallback medians use information available at each historical
    issue. Reject a fit without enough errors or history for all local quarters.
    """
    history_start = config.history_start
    labels = {t: v for t, v in select_labels(reader, fit_day).items() if t.astimezone(BERLIN).date() >= history_start}
    medians = _quarter_medians(labels, config.reference_min_per_quarter)
    if set(medians) != set(range(96)):
        raise ValueError("Insufficient reference history for every local quarter")
    past, errors, excluded = {}, [], 0
    for (day, lag1, lag7, quarter), actual in zip(
            rows.select("delivery_date", "price_lag_1", "price_lag_7", "quarter_of_day").iter_rows(), y):
        if day not in past:
            earlier = {t: v for t, v in select_labels(reader, day).items() if t.astimezone(BERLIN).date() >= history_start}
            past[day] = _quarter_medians(earlier, config.reference_min_per_quarter)
        estimate = _simple_estimate(lag1, lag7, quarter, past[day])
        if estimate is None:
            excluded += 1
        else:
            errors.append(actual - estimate)
    if len(errors) < config.reference_min_errors:
        raise ValueError("Insufficient eligible reference calibration errors")
    return {"medians": medians, "offsets": np.quantile(errors, QUANTILES, method="linear").tolist(),
            "calibration_rows": len(errors), "excluded_rows": excluded}


def predict_reference(rows: DataFrame[Features], reference: Reference) -> FloatArray:
    """Add the fitted error quantiles to each day's lag-based price estimate."""
    medians = {int(k): v for k, v in reference["medians"].items()}
    return np.array([_simple_estimate(lag1, lag7, quarter, medians)
                     for lag1, lag7, quarter in rows.select("price_lag_1", "price_lag_7", "quarter_of_day").iter_rows()])[:, None] + np.asarray(reference["offsets"])


def _simple_estimate(lag1: float | None, lag7: float | None, quarter: int,
                     medians: dict[int, float]) -> float | None:
    available = [value for value in (lag1, lag7) if value is not None]
    return float(np.mean(available)) if available else medians.get(quarter)


def _quarter_medians(labels: dict[datetime, float | None], minimum: int) -> dict[int, float]:
    values = defaultdict(list)
    for timestamp, value in labels.items():
        local = timestamp.astimezone(BERLIN)
        if value is not None:
            values[local.hour * 4 + local.minute // 15].append(value)
    return {q: float(np.median(v)) for q, v in values.items() if len(v) >= minimum}
