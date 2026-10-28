"""Training-only calibration and prediction for the simple price reference."""
from collections import defaultdict
from datetime import date, datetime

import numpy as np

from forecasts.config import RunConfig
from forecasts.contracts import FloatArray, Reference, Row
from forecasts.dataset import BERLIN
from forecasts.scoring import QUANTILES
from forecasts.snapshot import InputReader


def fit_reference(reader: InputReader, rows: list[Row], y: FloatArray,
                  fit_day: date, config: RunConfig) -> Reference:
    """Calibrate five error offsets using eligible training labels only.

    Historical fallback medians use information available at each historical
    issue. Reject a fit without enough errors or history for all local quarters.
    """
    history_start = config.history_start
    labels = {t: v for t, v in reader.labels_at(fit_day).items() if t.astimezone(BERLIN).date() >= history_start}
    medians = _quarter_medians(labels, config.reference_min_per_quarter)
    if set(medians) != set(range(96)):
        raise ValueError("Insufficient reference history for every local quarter")
    past, errors, excluded = {}, [], 0
    for row, actual in zip(rows, y):
        day = date.fromisoformat(row["delivery_date"])
        if day not in past:
            earlier = {t: v for t, v in reader.labels_at(day).items() if t.astimezone(BERLIN).date() >= history_start}
            past[day] = _quarter_medians(earlier, config.reference_min_per_quarter)
        estimate = _simple_estimate(row, past[day])
        if estimate is None:
            excluded += 1
        else:
            errors.append(actual - estimate)
    if len(errors) < config.reference_min_errors:
        raise ValueError("Insufficient eligible reference calibration errors")
    return {"medians": medians, "offsets": np.quantile(errors, QUANTILES, method="linear").tolist(),
            "calibration_rows": len(errors), "excluded_rows": excluded}


def predict_reference(rows: list[Row], reference: Reference) -> FloatArray:
    """Add the fitted error quantiles to each day's lag-based price estimate."""
    medians = {int(k): v for k, v in reference["medians"].items()}
    return np.array([_simple_estimate(row, medians) for row in rows])[:, None] + np.asarray(reference["offsets"])


def _simple_estimate(row: Row, medians: dict[int, float]) -> float | None:
    available = [row[f"price_lag_{d}"] for d in (1, 7) if row[f"price_lag_{d}"] is not None]
    return float(np.mean(available)) if available else medians.get(row["quarter_of_day"])


def _quarter_medians(labels: dict[datetime, float | None], minimum: int) -> dict[int, float]:
    values = defaultdict(list)
    for timestamp, value in labels.items():
        local = timestamp.astimezone(BERLIN)
        if value is not None:
            values[local.hour * 4 + local.minute // 15].append(value)
    return {q: float(np.median(v)) for q, v in values.items() if len(v) >= minimum}
