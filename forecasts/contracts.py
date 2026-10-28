"""Named values passed between feature building, fitting, prediction and scoring."""
from dataclasses import dataclass
from typing import Protocol, TypedDict

import numpy as np
from numpy.typing import NDArray

from forecasts.input_types import Row, Report

FloatArray = NDArray[np.float64]


class Reference(TypedDict):
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
    rows: list[Row]
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


@dataclass
class BacktestPredictions:
    """Fixed predictions and fit diagnostics, before joining realised prices."""
    rows: list[Row]
    folds: list[Report]
    failures: list[Report]
    fallback_rows: dict[str, int]
    crossing_rows: dict[str, int]


@dataclass
class EvaluationResult:
    """Predictions joined with scoring truth, plus aggregate comparisons."""
    rows: list[Row]
    report: Report
