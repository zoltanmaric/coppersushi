"""Thin local Metaflow orchestration; models and data operations remain ordinary Python."""
import json
from pathlib import Path

from metaflow import FlowSpec, IncludeFile, Parameter, current, step

from forecasts.evaluation import evaluate
from forecasts.snapshot import InputReader, read_local


class ForecastEvaluation(FlowSpec):
    config = IncludeFile("config", required=True)
    snapshot = Parameter("snapshot", required=True)
    output = Parameter("output", required=True)

    @step
    def start(self):
        self.settings = json.loads(self.config)
        manifest, self.tables = read_local(Path(self.snapshot))
        if manifest["snapshot_id"] != self.settings["snapshot_id"]:
            raise ValueError("Run requires its frozen input snapshot")
        self.snapshot_id = manifest["snapshot_id"]
        self.next(self.fit)

    @step
    def fit(self):
        self.report = evaluate(InputReader(self.tables), self.settings, Path(self.output))
        self.next(self.track)

    @step
    def track(self):
        from forecasts.run import track, finish
        self.mlflow_run_id = track(Path(self.output), self.settings, self.report, current.pathspec.rsplit('/', 2)[0])
        self.run_manifest = finish(Path(self.output), self.mlflow_run_id, current.pathspec.rsplit('/', 2)[0])
        self.next(self.end)

    @step
    def end(self):
        print(f"Completed run {self.run_manifest['run_id']}; MLflow {self.mlflow_run_id}", flush=True)


if __name__ == "__main__":
    ForecastEvaluation()
