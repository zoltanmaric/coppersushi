"""Named values passed between feature building, fitting and prediction."""
from dataclasses import dataclass
from typing import Protocol, TypedDict

import numpy as np
from numpy.typing import NDArray

from pandera.typing.polars import DataFrame
from forecasts.model.tables import Features

FloatArray = NDArray[np.float64]


class Reference(TypedDict):
    """Seasonal reference medians and calibration quantile offsets."""
    medians: dict[int, float]
    offsets: list[float]
    calibration_rows: int
    excluded_rows: int


class Predictor(Protocol):
    def predict(self, data: FloatArray) -> FloatArray:
        """Return one five-quantile vector per feature row."""
        ...


@dataclass
class TrainingData:
    """Historical feature rows paired with labels eligible at the fit cutoff."""
    rows: DataFrame[Features]
    targets: FloatArray


@dataclass
class FittedMonth:
    """Models and reference frozen for one monthly prediction window."""
    models: dict[str, Predictor]
    reference: Reference
    training_rows: int
    failures: dict[str, str]


@dataclass
class DayForecast:
    """Predictions and execution diagnostics; no scoring truth."""
    raw: dict[str, FloatArray]
    ordered: dict[str, FloatArray]
    failures: dict[str, str]
    crossings: dict[str, int]
    selected_model: str
    fallback_reason: str
