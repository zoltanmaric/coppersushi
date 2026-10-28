"""Run the local backtest as explicit feature, forecast and scoring stages."""
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from forecasts.backtest import forecast_months
from forecasts.config import RunConfig
from forecasts.contracts import EvaluationResult, Report, Row
from forecasts.features import build_features
from forecasts.scoring import score_forecasts
from forecasts.snapshot import InputReader


def evaluate(reader: InputReader, config: RunConfig, output: Path,
             restore_models: Path | None = None) -> Report:
    """Build historical inputs, forecast monthly windows, then score fixed outputs.

    Save feature rows, models, predictions and the report in output. For accepted
    reproduction, restore_models selects preserved fits instead of retraining.
    """
    features = build_features(reader, config.history_start, config.end_exclusive)
    save_features(features, output)
    predictions = forecast_months(reader, features, config, output, restore_models)
    result = score_forecasts(predictions, reader.truth, config)
    save_evaluation(result, output)
    return result.report


def save_features(features: list[Row], output: Path) -> None:
    """Save the selected features and audit fields as compressed Parquet."""
    output.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(features), output / "features.parquet", compression="zstd")


def save_evaluation(result: EvaluationResult, output: Path) -> None:
    """Save scored prediction rows and the JSON report with their existing schemas."""
    output.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(result.rows), output / "predictions.parquet", compression="zstd")
    (output / "report.json").write_text(json.dumps(result.report, indent=2, allow_nan=False) + "\n")
