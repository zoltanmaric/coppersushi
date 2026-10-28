"""Daily quantile prediction and explicit source/execution fallbacks."""
from collections.abc import Mapping

from catboost import CatBoostError
import numpy as np

from forecasts.config import RunConfig
from forecasts.contracts import DayForecast, Predictor, Reference
from pandera.typing.polars import DataFrame
from forecasts.tables import Features
from forecasts.features import feature_matrix
from forecasts.reference import predict_reference


def predict_day(rows: DataFrame[Features], models: Mapping[str, Predictor], reference: Reference,
                config: RunConfig) -> DayForecast:
    """Predict five ordered quantiles per quarter and select a usable method.

    Keep raw outputs and crossing counts. Choose demand → weather → prices →
    reference from source availability and execution success, never scores.
    An individual model failure receives the reference forecast.
    """
    ref = predict_reference(rows, reference)
    raw, predictions, failures, crossing = {}, {}, {}, {}
    for name, fields in config.features.items():
        try:
            if name not in models:
                raise ValueError("Model fit failed")
            q = np.asarray(models[name].predict(feature_matrix(rows, fields)))
            if q.shape != (len(rows), 5) or not np.isfinite(q).all():
                raise ValueError("Non-finite or incomplete model output")
            raw[name], predictions[name] = q, np.sort(q, axis=1)
            crossing[name] = int((np.diff(q, axis=1) < 0).any(axis=1).sum())
        except (CatBoostError, ValueError) as error:
            failures[name] = str(error)
            raw[name], predictions[name], crossing[name] = ref, ref, 0
    reasons = []
    chosen = "reference"
    for name in ("demand", "weather", "prices"):
        if rows["price_lags_unavailable"][0]:
            reasons.append(f"{name}:price_lags_unavailable")
        elif name in failures:
            reasons.append(f"{name}:prediction_failure")
        elif name in ("demand", "weather") and rows["weather_source_unavailable"][0]:
            reasons.append(f"{name}:weather_source_unavailable")
        elif name == "demand" and rows["demand_source_unavailable"][0]:
            reasons.append("demand:demand_source_unavailable")
        else:
            chosen = name
            break
    predictions.update(reference=ref, system=predictions.get(chosen, ref))
    return DayForecast(raw, predictions, failures, crossing, chosen, ";".join(reasons))
