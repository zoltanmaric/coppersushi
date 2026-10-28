"""Run the local backtest as explicit feature, forecast and scoring stages."""
import argparse
import json
from pathlib import Path

from forecasts.backtest import forecast_months
from forecasts.config import RunConfig
from forecasts.contracts import EvaluationResult, Report
from forecasts.features import build_features
from pandera.typing.polars import DataFrame
from forecasts.tables import Features
from forecasts.scoring import score_forecasts
from forecasts.snapshot import InputReader, read_local


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


def save_features(features: DataFrame[Features], output: Path) -> None:
    """Save the selected features and audit fields as compressed Parquet."""
    output.mkdir(parents=True, exist_ok=True)
    features.write_parquet(output / "features.parquet", compression="zstd")


def save_evaluation(result: EvaluationResult, output: Path) -> None:
    """Save scored prediction rows and the JSON report with native dates and UTC timestamps."""
    output.mkdir(parents=True, exist_ok=True)
    result.rows.write_parquet(output / "predictions.parquet", compression="zstd")
    (output / "report.json").write_text(json.dumps(result.report, indent=2, allow_nan=False) + "\n")


def main() -> None:
    """Evaluate a fixed local snapshot into a new output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("run-config.json"))
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = RunConfig.from_dict(json.loads(args.config.read_text()))
    manifest, tables = read_local(args.snapshot)
    if manifest["snapshot_id"] != config.snapshot_id:
        raise ValueError("Evaluation requires its configured input snapshot")
    args.output.mkdir(parents=True, exist_ok=False)
    evaluate(InputReader(tables), config, args.output)


if __name__ == "__main__":
    main()
