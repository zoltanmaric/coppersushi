"""Run the local backtest as explicit feature, forecast and scoring stages."""
import argparse
import json
from pathlib import Path

from pandera.typing.polars import DataFrame

from forecasts.config import RunConfig
from forecasts.evaluation.backtest import forecast_months
from forecasts.evaluation.contracts import BacktestPredictions
from forecasts.evaluation.scoring import score_forecasts
from forecasts.inputs.input_types import Report
from forecasts.inputs.selection import InputReader
from forecasts.inputs.snapshot import read_local
from forecasts.model.features import build_features
from forecasts.model.tables import Features


def evaluate(reader: InputReader, config: RunConfig, output: Path,
             restore_models: Path | None = None) -> Report:
    """Build historical inputs, forecast monthly windows, then score fixed outputs.

    Save feature rows, models, predictions and the report in output. For accepted
    reproduction, restore_models selects preserved fits instead of retraining.
    """
    features = prepare_features(reader, config, output)
    predictions = forecast_months(reader, features, config, output, restore_models)
    return score_predictions(predictions, reader, config, output)


def prepare_features(reader: InputReader, config: RunConfig, output: Path) -> DataFrame[Features]:
    """Build point-in-time feature rows and save their audit fields."""
    features = build_features(reader, config.history_start, config.end_exclusive,
                              complete_from=config.train_start)
    output.mkdir(parents=True, exist_ok=True)
    features.write_parquet(output / "features.parquet", compression="zstd")
    return features


def score_predictions(predictions: BacktestPredictions, reader: InputReader,
                      config: RunConfig, output: Path) -> Report:
    """Score fixed predictions against realised prices and save the rows and report."""
    result = score_forecasts(predictions, reader.realized_prices(), config)
    result.rows.write_parquet(output / "predictions.parquet", compression="zstd")
    (output / "report.json").write_text(json.dumps(result.report, indent=2, allow_nan=False) + "\n")
    return result.report


def main() -> None:
    """Evaluate a fixed local snapshot into a new output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "run-config.json")
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
