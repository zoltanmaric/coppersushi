"""Freeze a local experiment and reproduce an accepted run from its preserved artifacts."""
from __future__ import annotations

from dataclasses import asdict
from contextlib import contextmanager
from collections.abc import Iterator

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import tempfile
import subprocess
import sys
import tarfile
import uuid
from typing import Any, TYPE_CHECKING

from forecasts.config import RunConfig
from forecasts.contracts import Report

if TYPE_CHECKING:
    from mlflow import MlflowClient

from forecasts.dataset import ROOT, digest
from forecasts.snapshot import canonical, load

DATA_ROOT = Path(os.environ.get("FORECAST_DATA_ROOT", ROOT / "data/forecasts")).resolve()
RUNS = DATA_ROOT / "runs"


APPROACHES = {
    "prices": ("CatBoost · prices + calendar", "Uses earlier prices and calendar information."),
    "weather": ("CatBoost · prices + calendar + weather", "Adds forecast weather to earlier prices and calendar information."),
    "demand": ("CatBoost · prices + calendar + weather + demand", "Adds forecast demand to the price, calendar and weather inputs."),
    "reference": ("Benchmark · historical prices + past-error intervals", "Averages yesterday and last week's same-clock prices, with missing-history fallbacks and training-only error intervals."),
    "system": ("System · input-based fallback selection", "Selects demand, then weather, then prices/calendar, then benchmark according to source availability and prediction success."),
}


def main() -> None:
    """Dispatch a new local run or reproduction from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--config", type=Path, default=ROOT / "forecasts/run-config.json")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--exploratory", action="store_true")
    p = sub.add_parser("reproduce")
    p.add_argument("run_id")
    p = sub.add_parser("replay", help=argparse.SUPPRESS)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    for p in (sub.choices["reproduce"], sub.choices["replay"]):
        p.add_argument("--profile", required=True)
        p.add_argument("--bucket", required=True)
        p.add_argument("--region", default="eu-west-1")
    args = parser.parse_args()
    if args.command == "run":
        directory, _ = prepare(args.config, args.exploratory)
        print(f"Frozen run {directory.name}", flush=True)
        run_flow(directory, args.snapshot)
    elif args.command == "reproduce":
        reproduce(args.run_id, args.profile, args.bucket, args.region)
    else:
        replay(args.source, args.destination, args.profile, args.bucket, args.region)


def prepare(config_path: Path, exploratory: bool = False) -> tuple[Path, RunConfig]:
    """Freeze an attempt; accepted runs require committed code and the exact lock.

    Reject unrestorable environments before creating a run. Exploratory runs
    may use checkout changes and extra packages, and cannot be reproduced as accepted.
    """
    config = RunConfig.from_dict(json.loads(config_path.read_text()))
    code = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=normal"))
    if dirty and not exploratory:
        raise ValueError("Accepted runs require committed code; use --exploratory for development")
    environment = _environment()
    lock = ((ROOT / "forecasts/requirements-lock.txt").read_bytes() if exploratory else
            subprocess.check_output(["git", "-C", str(ROOT), "show", f"{code}:forecasts/requirements-lock.txt"]))
    if not exploratory:
        _validate_lock(lock.decode(), environment["packages"])
    manifest = {"code_revision": code, "exploratory": exploratory, "config": config.to_dict(),
                "environment": environment, "lock_sha256": hashlib.sha256(lock).hexdigest()}
    directory = RUNS / uuid.uuid4().hex[:24]
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "config.json").write_bytes(canonical(config.to_dict()))
    (directory / "requirements-lock.txt").write_bytes(lock)
    with (directory / "code.tar").open('wb') as archive:
        subprocess.run(["git", "-C", str(ROOT), "archive", code, "forecasts"], stdout=archive, check=True)
    manifest["code_sha256"] = digest(directory / "code.tar")
    manifest["experiment_fingerprint"] = hashlib.sha256(canonical(manifest)).hexdigest()
    manifest["run_id"] = directory.name
    (directory / "manifest.json").write_bytes(canonical(manifest))
    return directory, config


def run_flow(directory: Path, snapshot: Path) -> None:
    """Execute accepted runs from their archive; keep exploratory runs in checkout.

    Output, Metaflow metadata and tracking live outside the extracted code.
    Record success, failure or interruption in the selected local MLflow store.
    """
    directory = directory.resolve()
    config = RunConfig.from_dict(json.loads((directory / "config.json").read_text()))
    manifest = json.loads((directory / "manifest.json").read_text())
    with _execution_code(directory, manifest) as code:
        env = os.environ.copy()
        env.update(METAFLOW_DEFAULT_DATASTORE="local", METAFLOW_DEFAULT_METADATA="local",
                   METAFLOW_DATASTORE_SYSROOT_LOCAL=str(DATA_ROOT / "metaflow"),
                   METAFLOW_USER="forecast-local", PYTHONPATH=str(code),
                   FORECAST_DATA_ROOT=str(DATA_ROOT))
        mlflow_run = _start_tracking(directory, config)
        client = tracking_client()
        try:
            subprocess.run([sys.executable, "-m", "forecasts.flow", "run", "--config", str(directory / "config.json"),
                            "--snapshot", str(snapshot.resolve()), "--output", str(directory),
                            "--mlflow-run", mlflow_run], cwd=code, env=env, check=True)
        except BaseException as error:
            interrupted = isinstance(error, (KeyboardInterrupt, SystemExit)) or (
                isinstance(error, subprocess.CalledProcessError) and error.returncode in (-2, -15, 130, 143))
            client.set_tag(mlflow_run, "failure_type", type(error).__name__)
            client.set_terminated(mlflow_run, status="KILLED" if interrupted else "FAILED")
            raise
        else:
            client.set_terminated(mlflow_run)


def reproduce(run_id: str, profile: str, bucket: str, region: str) -> Path:
    """Restore and verify a saved run in a new, retained attempt directory."""
    if len(run_id) != 24 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError("Expected a 24-character accepted run identifier")
    source = RUNS / run_id
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["exploratory"]:
        raise ValueError("Exploratory runs cannot satisfy accepted reproduction")
    for name, expected in manifest["artifacts"].items():
        if digest(source / name) != expected:
            raise ValueError(f"Preserved artifact checksum mismatch: {name}")
    if _environment()["python"] != manifest["environment"]["python"]:
        raise ValueError(f"Use Python {manifest['environment']['python']} to restore this environment")
    for key in ('system', 'machine'):
        if _environment()[key] != manifest['environment'][key]:
            raise ValueError("Reproduction requires the recorded platform")
    destination = DATA_ROOT / "reproductions" / run_id / uuid.uuid4().hex[:24]
    destination.mkdir(parents=True, exist_ok=False)
    attempt = {"attempt_id": destination.name, "source_run_id": run_id, "status": "restoring"}
    status = destination / "attempt.json"
    status.write_bytes(canonical(attempt))
    print(f"Reproduction attempt {destination}", flush=True)
    try:
        code = destination / "code"
        with tarfile.open(source / "code.tar") as archive:
            archive.extractall(code, filter="data")
        python = destination / "venv/bin/python"
        subprocess.run([sys.executable, "-m", "venv", str(destination / "venv")], check=True)
        subprocess.run([str(python), "-m", "pip", "--isolated", "install", "--index-url", "https://pypi.org/simple",
                        "-r", str(code / "forecasts/requirements-lock.txt")], check=True)
        attempt["status"] = "replaying"
        status.write_bytes(canonical(attempt))
        env = os.environ.copy()
        env.update(PYTHONPATH=str(code), FORECAST_DATA_ROOT=str(DATA_ROOT))
        subprocess.run([str(python), "-m", "forecasts.run", "replay", "--source", str(source.resolve()),
                        "--destination", str(destination / "result"), "--profile", profile, "--bucket", bucket,
                        "--region", region], cwd=code, env=env, check=True)
        verification = json.loads((destination / "result/verification.json").read_text())
        if (verification.get("run_id") != run_id or not verification.get("predictions_match")
                or not verification.get("scores_match")):
            raise ValueError("Reproduction did not verify the requested run")
    except BaseException as error:
        attempt.update(status="interrupted" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed",
                       error_type=type(error).__name__)
        status.write_bytes(canonical(attempt))
        raise
    attempt["status"] = "verified"
    status.write_bytes(canonical(attempt))
    return destination


def replay(source: Path, destination: Path, profile: str, bucket: str, region: str) -> None:
    """Reload the S3 snapshot and verify predictions and scores from saved models."""
    import numpy as np
    import pyarrow.parquet as pq
    from forecasts.evaluation import evaluate
    from forecasts.snapshot import InputReader
    manifest = json.loads((source / "manifest.json").read_text())
    if _environment() != manifest["environment"]:
        raise ValueError("Restored dependency environment differs from the accepted run")
    if digest(ROOT / "forecasts/requirements-lock.txt") != manifest["lock_sha256"]:
        raise ValueError("Restored dependency lock differs")
    config = RunConfig.from_dict(manifest["config"])
    snapshot = destination / "snapshot"
    _, tables = load(profile, region, bucket, config.snapshot_id, snapshot)
    report = evaluate(InputReader(tables), config, destination, restore_models=source / "models")
    expected = pq.read_table(source / "predictions.parquet").to_pydict()
    actual = pq.read_table(destination / "predictions.parquet").to_pydict()
    tolerance = config.tolerance
    for name in expected:
        if '_q' in name or '_raw_q' in name or name == 'target':
            np.testing.assert_allclose(np.array(actual[name], dtype=float), np.array(expected[name], dtype=float),
                                       atol=tolerance.absolute, rtol=tolerance.relative, equal_nan=True)
        elif actual[name] != expected[name]:
            raise ValueError(f"Prediction metadata differs: {name}")
    original_report = json.loads((source / "report.json").read_text())
    def compare(a: Any, b: Any) -> None:
        if isinstance(a, dict):
            if a.keys() != b.keys():
                raise ValueError("Reproduced report fields differ")
            for key in a:
                compare(a[key], b[key])
        elif isinstance(a, list):
            if len(a) != len(b):
                raise ValueError("Reproduced report lengths differ")
            for left, right in zip(a, b):
                compare(left, right)
        elif isinstance(a, (float, int)):
            np.testing.assert_allclose(a, b, atol=tolerance.absolute, rtol=tolerance.relative)
        elif a != b:
            raise ValueError("Reproduced report metadata differs")
    compare(json.loads(json.dumps(report)), original_report)
    (destination / "verification.json").write_text(json.dumps({"run_id": manifest["run_id"], "predictions_match": True,
                                                               "scores_match": True, "tolerance": asdict(tolerance)}, indent=2))
    print(f"Verified reproduction {manifest['run_id']}", flush=True)


def tracking_client() -> MlflowClient:
    """Open the local SQLite MLflow store and create its directory if needed."""
    from mlflow import MlflowClient
    tracking = DATA_ROOT / "tracking"
    tracking.mkdir(parents=True, exist_ok=True)
    return MlflowClient(tracking_uri=f"sqlite:///{tracking / 'mlflow.db'}")


def track(directory: Path, config: RunConfig, report: Report, metaflow_run: str, mlflow_run: str) -> str:
    """Record comparison children and artifacts under the active execution; return its ID."""
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
    return mlflow_run


def finish(directory: Path, mlflow_run: str, metaflow_run: str) -> dict[str, Any]:
    """Hash saved artifacts and record the completed provenance manifest."""
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(mlflow_run_id=mlflow_run, metaflow_run_id=metaflow_run,
                    artifacts={str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob('*')) if p.is_file() and p != path})
    path.write_bytes(canonical(manifest))
    # The final provenance record also belongs in tracking, after identifiers are known.
    tracking_client().log_artifact(mlflow_run, str(path), artifact_path="run")
    return manifest


def _start_tracking(directory: Path, config: RunConfig) -> str:
    client = tracking_client()
    name = "germany-luxembourg-local"
    experiment = client.get_experiment_by_name(name)
    experiment_id = experiment.experiment_id if experiment else client.create_experiment(
        name, artifact_location=(DATA_ROOT / "tracking/artifacts").as_uri())
    manifest = json.loads((directory / "manifest.json").read_text())
    label = "Exploratory quantile evaluation" if manifest["exploratory"] else "Quantile evaluation"
    run = client.create_run(experiment_id, tags={
        "mlflow.runName": f"{label} · {config.evaluation_start} to {config.end_exclusive} (exclusive)",
        "mlflow.note.content": "Local monthly expanding evaluation. Acceptance is a separate review decision. Duration spans orchestration, input loading, evaluation and result recording.",
        "record_type": "execution", "execution_role": "evaluation",
        "timing_semantics": "orchestration_and_computation",
        "snapshot_id": config.snapshot_id, "code_revision": manifest["code_revision"],
        "forecast_run": manifest["run_id"], "exploratory": str(manifest["exploratory"]),
        "experiment_fingerprint": manifest.get("experiment_fingerprint", manifest["run_id"]),
    })
    try:
        for key in ("train_start", "evaluation_start", "end_exclusive"):
            client.log_param(run.info.run_id, key, getattr(config, key).isoformat())
        for key, value in asdict(config.catboost).items():
            client.log_param(run.info.run_id, key, value)
        client.log_artifact(run.info.run_id, str(directory / "manifest.json"), artifact_path="start")
    except BaseException:
        client.set_terminated(run.info.run_id, status="FAILED")
        raise
    return run.info.run_id


@contextmanager
def _execution_code(directory: Path, manifest: Report) -> Iterator[Path]:
    if manifest["exploratory"]:
        yield ROOT
        return
    if _environment() != manifest["environment"]:
        raise ValueError("Execution environment changed after preparation")
    if digest(directory / "code.tar") != manifest["code_sha256"]:
        raise ValueError("Frozen code archive differs from the prepared run")
    with tempfile.TemporaryDirectory(prefix="forecast-code-") as temporary:
        code = Path(temporary)
        with tarfile.open(directory / "code.tar") as archive:
            archive.extractall(code, filter="data")
        lock = code / "forecasts/requirements-lock.txt"
        if digest(lock) != manifest["lock_sha256"]:
            raise ValueError("Frozen code and dependency lock disagree")
        _validate_lock(lock.read_text(), manifest["environment"]["packages"])
        yield code


def _validate_lock(text: str, packages: dict[str, str]) -> None:
    locked = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, separator, version = line.strip().partition("==")
        if not separator or not version or any(c.isspace() for c in version):
            raise ValueError("Accepted execution requires a complete name==version lock")
        locked[re.sub(r"[-_.]+", "-", name.lower())] = version
    installed = {re.sub(r"[-_.]+", "-", name.lower()): version for name, version in packages.items()}
    if installed != locked:
        differences = sorted(name for name in installed.keys() | locked.keys()
                             if installed.get(name) != locked.get(name))
        raise ValueError("Environment does not match the restorable lock: " + ", ".join(differences)
                         + ". Use a dedicated environment installed from requirements-lock.txt.")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def _environment() -> dict[str, Any]:
    return {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine(),
            "packages": {d.metadata["Name"].lower(): d.version for d in importlib.metadata.distributions()}}


if __name__ == "__main__":
    main()
