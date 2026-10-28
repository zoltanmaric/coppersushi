"""Local Metaflow stages: load → features → monthly backtest → score → record."""
import json
from pathlib import Path
from typing import cast

from metaflow import FlowSpec, IncludeFile, Parameter, current, step

from forecasts.backtest import forecast_months
from forecasts.config import RunConfig
from forecasts.evaluation import save_evaluation, save_features
from forecasts.features import build_features
from forecasts.scoring import score_forecasts
from forecasts.snapshot import InputReader, read_local


class ForecastEvaluation(FlowSpec):
    """Persist each pipeline stage locally; keep computation in ordinary Python."""

    # Metaflow replaces parameter declarations with parsed values before steps run.
    config = cast(str, IncludeFile("config", required=True))
    snapshot = cast(str, Parameter("snapshot", required=True))
    output = cast(str, Parameter("output", required=True))
    mlflow_run = cast(str, Parameter("mlflow-run", required=True))

    @step
    def start(self) -> None:
        """Load and validate the exact snapshot frozen in the run configuration."""
        self.settings = RunConfig.from_dict(json.loads(self.config))
        manifest, self.tables = read_local(Path(self.snapshot))
        if manifest["snapshot_id"] != self.settings.snapshot_id:
            raise ValueError("Run requires its frozen input snapshot")
        self.snapshot_id = manifest["snapshot_id"]
        self.next(self.features)

    @step
    def features(self) -> None:
        """Build each day's point-in-time feature rows and save their audit fields."""
        self.feature_rows = build_features(InputReader(self.tables),
                                           self.settings.history_start,
                                           self.settings.end_exclusive)
        save_features(self.feature_rows, Path(self.output))
        self.next(self.backtest)

    @step
    def backtest(self) -> None:
        """Fit each month on earlier labels, then predict each day in that month."""
        self.predictions = forecast_months(InputReader(self.tables), self.feature_rows,
                                           self.settings, Path(self.output))
        self.next(self.score)

    @step
    def score(self) -> None:
        """Join realised outcomes after prediction and save the comparison report."""
        result = score_forecasts(self.predictions, InputReader(self.tables).truth, self.settings)
        save_evaluation(result, Path(self.output))
        self.report = result.report
        self.next(self.track)

    @step
    def track(self) -> None:
        """Record comparisons, artifacts and final provenance in MLflow."""
        from forecasts.run import finish, track
        assert current.pathspec is not None
        pathspec = current.pathspec.rsplit('/', 2)[0]
        self.mlflow_run_id = track(Path(self.output), self.settings, self.report, pathspec, self.mlflow_run)
        self.run_manifest = finish(Path(self.output), self.mlflow_run_id, pathspec)
        self.next(self.end)

    @step
    def end(self) -> None:
        """Print the identifiers of the completed run and tracking record."""
        print(f"Completed run {self.run_manifest['run_id']}; MLflow {self.mlflow_run_id}", flush=True)


if __name__ == "__main__":
    ForecastEvaluation()
