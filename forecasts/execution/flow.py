"""Run the shared historical evaluation and record it in MLflow."""
import json
from pathlib import Path
from typing import cast

from metaflow import FlowSpec, IncludeFile, Parameter, current, step

from forecasts.config import RunConfig
from forecasts.evaluation.workflow import evaluate
from forecasts.execution.tracking import finish, record_comparisons
from forecasts.inputs.selection import InputReader
from forecasts.inputs.snapshot import canonical, read_local


class ForecastEvaluation(FlowSpec):
    """Track a local evaluation against its frozen input snapshot."""

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
        (Path(self.output) / "snapshot-manifest.json").write_bytes(canonical(manifest))
        self.next(self.evaluate)

    @step
    def evaluate(self) -> None:
        """Save historical features, fitted models, predictions and scores."""
        self.report = evaluate(InputReader(self.tables), self.settings, Path(self.output))
        self.next(self.track)

    @step
    def track(self) -> None:
        """Record comparisons, artifacts and final provenance in MLflow."""
        assert current.pathspec is not None
        pathspec = current.pathspec.rsplit('/', 2)[0]
        record_comparisons(Path(self.output), self.settings, self.report, pathspec, self.mlflow_run)
        self.mlflow_run_id = self.mlflow_run
        self.run_manifest = finish(Path(self.output), self.mlflow_run_id, pathspec)
        self.next(self.end)

    @step
    def end(self) -> None:
        """Print the identifiers of the completed run and tracking record."""
        print(f"Completed run {self.run_manifest['run_id']}; MLflow {self.mlflow_run_id}", flush=True)


if __name__ == "__main__":
    ForecastEvaluation()
