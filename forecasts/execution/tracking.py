"""Store forecast execution provenance and review records in local MLflow."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING

from forecasts.config import RunConfig
from forecasts.execution import data_root
from forecasts.inputs.input_types import Report
from forecasts.inputs.snapshot import canonical
from forecasts.model.coverage import STATIC_INPUT_POLICY
from forecasts.provenance import digest

if TYPE_CHECKING:
    from mlflow import MlflowClient


APPROACHES = {
    "prices": ("Baseline · CatBoost prices + calendar", "Uses earlier prices and calendar information."),
    "reference": ("Benchmark · historical prices + past-error intervals", "Averages yesterday and last week's same-clock prices, with missing-history fallbacks and training-only error intervals."),
}


@contextmanager
def record_execution(directory: Path, config: RunConfig) -> Iterator[str]:
    """Record a running execution and its outcome around the Metaflow subprocess."""
    client = tracking_client()
    run_id = _start_tracking(client, directory, config)
    try:
        yield run_id
    except BaseException as error:
        interrupted = isinstance(error, (KeyboardInterrupt, SystemExit)) or (
            isinstance(error, subprocess.CalledProcessError) and error.returncode in (-2, -15, 130, 143))
        client.set_tag(run_id, "failure_type", type(error).__name__)
        client.set_terminated(run_id, status="KILLED" if interrupted else "FAILED")
        raise
    else:
        client.set_terminated(run_id)


def record_comparisons(directory: Path, config: RunConfig, report: Report, metaflow_run: str, mlflow_run: str) -> None:
    """Record comparison children and artifacts under the active execution."""
    client = tracking_client()
    parent = client.get_run(mlflow_run)
    client.set_tag(mlflow_run, "metaflow_run", metaflow_run)
    for feature_set, scores in report["metrics"].items():
        name, description = APPROACHES[feature_set]
        child = client.create_run(parent.info.experiment_id, tags={
            "mlflow.parentRunId": mlflow_run, "mlflow.runName": name,
            "mlflow.note.content": description + " Aggregate comparison across monthly fits; Duration measures result logging, not separately timed training.",
            "record_type": "comparison", "timing_semantics": "logging_only",
            "feature_set": feature_set, "snapshot_id": config.snapshot_id,
            "code_revision": parent.data.tags["code_revision"], "metaflow_run": metaflow_run,
        })
        child_id = child.info.run_id
        try:
            for key in ("evaluation_start", "end_exclusive"):
                client.log_param(child_id, key, getattr(config, key).isoformat())
            for key, value in scores.items():
                if isinstance(value, (float, int)):
                    client.log_metric(child_id, key, value)
            client.log_text(child_id, json.dumps(config.features.get(feature_set, []), indent=2), "features.json")
        except BaseException:
            client.set_terminated(child_id, status="FAILED")
            raise
        else:
            client.set_terminated(child_id)
    client.log_artifacts(mlflow_run, str(directory), artifact_path="run")


def finish(directory: Path, mlflow_run: str, metaflow_run: str) -> Report:
    """Hash saved artifacts and record the completed provenance manifest."""
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(mlflow_run_id=mlflow_run, metaflow_run_id=metaflow_run, input_policy=STATIC_INPUT_POLICY,
                    artifacts={str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob('*')) if p.is_file() and p != path})
    path.write_bytes(canonical(manifest))
    # The final provenance record also belongs in tracking, after identifiers are known.
    tracking_client().log_artifact(mlflow_run, str(path), artifact_path="run")
    return manifest


def tracking_client() -> MlflowClient:
    """Open the local SQLite MLflow store and create its directory if needed."""
    from mlflow import MlflowClient
    tracking = data_root() / "tracking"
    tracking.mkdir(parents=True, exist_ok=True)
    return MlflowClient(tracking_uri=f"sqlite:///{tracking / 'mlflow.db'}")


def _start_tracking(client: MlflowClient, directory: Path, config: RunConfig) -> str:
    name = "germany-luxembourg-local"
    experiment = client.get_experiment_by_name(name)
    experiment_id = experiment.experiment_id if experiment else client.create_experiment(
        name, artifact_location=(data_root() / "tracking/artifacts").as_uri())
    manifest = json.loads((directory / "manifest.json").read_text())
    label = "Exploratory prices/calendar baseline" if manifest["exploratory"] else "Prices/calendar baseline"
    run = client.create_run(experiment_id, tags={
        "mlflow.runName": f"{label} · {config.evaluation_start} to {config.end_exclusive} (exclusive)",
        "mlflow.note.content": "Local monthly expanding evaluation. Acceptance is a separate review decision. Duration spans orchestration, input loading, evaluation and result recording.",
        "record_type": "execution", "execution_role": "evaluation",
        "timing_semantics": "orchestration_and_computation",
        "snapshot_id": config.snapshot_id, "code_revision": manifest["code_revision"],
        "model_method": config.model_method,
        "forecast_run": manifest["run_id"], "exploratory": str(manifest["exploratory"]),
        "experiment_fingerprint": manifest["experiment_fingerprint"],
    })
    try:
        for key in ("train_start", "evaluation_start", "end_exclusive"):
            client.log_param(run.info.run_id, key, getattr(config, key).isoformat())
        for key, value in asdict(config.catboost).items():
            client.log_param(run.info.run_id, key, value)
        if "proposal" in manifest:
            proposal = manifest["proposal"]
            path = directory / "proposal.md"
            if digest(path) != proposal["sha256"]:
                raise ValueError("Frozen evaluation proposal checksum mismatch")
            client.set_tag(run.info.run_id, "proposal_path", proposal["wiki_path"])
            client.set_tag(run.info.run_id, "proposal_revision", proposal["git_revision"])
            client.log_artifact(run.info.run_id, str(path), artifact_path="research")
        client.log_artifact(run.info.run_id, str(directory / "manifest.json"), artifact_path="start")
    except BaseException:
        client.set_terminated(run.info.run_id, status="FAILED")
        raise
    return run.info.run_id
