"""Predict one complete delivery day with the fixed model set."""
from collections.abc import Mapping
from datetime import timedelta

from catboost import CatBoostError
import numpy as np

from forecasts.config import RunConfig
from forecasts.coverage import require_static_features
from forecasts.contracts import DayForecast, Predictor, Reference
from pandera.typing.polars import DataFrame
from forecasts.tables import Features
from forecasts.features import feature_matrix
from forecasts.reference import predict_reference


def predict_day(rows: DataFrame[Features], models: Mapping[str, Predictor], reference: Reference,
                config: RunConfig) -> DayForecast:
    """Require complete inputs and successful predictions from every method."""
    if rows.is_empty():
        raise ValueError("No delivery quarters to predict")
    day = rows["delivery_date"][0]
    require_static_features(rows, day, day + timedelta(days=1))
    shape = (len(rows), len(config.quantiles))
    ref = predict_reference(rows, reference)
    if ref.shape != shape or not np.isfinite(ref).all() or (np.diff(ref, axis=1) < 0).any():
        raise ValueError(f"Non-finite, unordered or incomplete reference prediction for {day}")
    raw, predictions, crossing = {}, {}, {}
    for name, fields in config.features.items():
        try:
            if name not in models:
                raise ValueError("Model fit is missing")
            q = np.asarray(models[name].predict(feature_matrix(rows, fields)))
            if q.shape != shape or not np.isfinite(q).all():
                raise ValueError("Non-finite or incomplete model output")
        except (CatBoostError, ValueError) as error:
            raise ValueError(f"{name} prediction failed for {day}: {error}") from error
        raw[name], predictions[name] = q, np.sort(q, axis=1)
        crossing[name] = int((np.diff(q, axis=1) < 0).any(axis=1).sum())
    predictions.update(reference=ref, system=predictions["demand"])
    return DayForecast(raw, predictions, {}, crossing, "demand", "")
