"""Freeze a local experiment and reproduce an accepted run from its preserved artifacts."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

from forecasts.dataset import ROOT, digest
from forecasts.snapshot import canonical, load, read_local

RUNS = ROOT / "data/forecasts/runs"


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def environment():
    return {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine(),
            "packages": {d.metadata["Name"].lower(): d.version for d in importlib.metadata.distributions()}}


def prepare(config_path, exploratory=False):
    from forecasts.evaluation import FEATURES
    config = json.loads(config_path.read_text())
    config["features"] = FEATURES
    code = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    if dirty and not exploratory:
        raise ValueError("Accepted runs require committed code; use --exploratory for development")
    manifest = {"code_revision": code, "exploratory": dirty or exploratory, "config": config,
                "environment": environment(), "lock_sha256": digest(ROOT / "forecasts/requirements-lock.txt")}
    run_id = hashlib.sha256(canonical(manifest)).hexdigest()[:24]
    directory = RUNS / run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest["run_id"] = run_id
    (directory / "manifest.json").write_bytes(canonical(manifest))
    (directory / "config.json").write_bytes(canonical(config))
    shutil.copyfile(ROOT / "forecasts/requirements-lock.txt", directory / "requirements-lock.txt")
    with (directory / "code.tar").open('wb') as archive:
        subprocess.run(["git", "-C", str(ROOT), "archive", code, "forecasts"], stdout=archive, check=True)
    return directory, config


def track(directory, config, report, metaflow_run):
    import mlflow
    tracking = ROOT / "data/forecasts/tracking"
    tracking.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{tracking / 'mlflow.db'}")
    name = "germany-luxembourg-local"
    experiment = mlflow.get_experiment_by_name(name)
    experiment_id = experiment.experiment_id if experiment else mlflow.create_experiment(name, artifact_location=(tracking / "artifacts").as_uri())
    manifest = json.loads((directory / "manifest.json").read_text())
    with mlflow.start_run(experiment_id=experiment_id, run_name=manifest["run_id"]) as parent:
        mlflow.set_tags({"snapshot_id": config["snapshot_id"], "code_revision": manifest["code_revision"],
                         "metaflow_run": metaflow_run, "forecast_run": manifest["run_id"],
                         "exploratory": str(manifest["exploratory"])})
        mlflow.log_params({"train_start": config["train_start"], "evaluation_start": config["evaluation_start"],
                           "end_exclusive": config["end_exclusive"], **config["catboost"]})
        for feature_set, scores in report["metrics"].items():
            with mlflow.start_run(experiment_id=experiment_id, run_name=feature_set, nested=True):
                mlflow.set_tags({"feature_set": feature_set, "snapshot_id": config["snapshot_id"], "metaflow_run": metaflow_run})
                mlflow.log_metrics({k: v for k, v in scores.items() if isinstance(v, (float, int))})
                mlflow.log_dict(config["features"].get(feature_set, []), "features.json")
        mlflow.log_artifacts(str(directory), artifact_path="run")
        return parent.info.run_id


def finish(directory, mlflow_run, metaflow_run):
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(mlflow_run_id=mlflow_run, metaflow_run_id=metaflow_run,
                    artifacts={str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob('*')) if p.is_file() and p != path})
    path.write_bytes(canonical(manifest))
    # The final provenance record also belongs in tracking, after identifiers are known.
    import mlflow
    with mlflow.start_run(run_id=mlflow_run):
        mlflow.log_artifact(str(path), artifact_path="run")
    return manifest


def run_flow(directory, snapshot):
    env = os.environ.copy()
    env.update(METAFLOW_DEFAULT_DATASTORE="local", METAFLOW_DEFAULT_METADATA="local",
               METAFLOW_DATASTORE_SYSROOT_LOCAL=str(ROOT / "data/forecasts/metaflow"),
               METAFLOW_USER="forecast-local", PYTHONPATH=str(ROOT))
    subprocess.run([sys.executable, "-m", "forecasts.flow", "run", "--config", str(directory / "config.json"),
                    "--snapshot", str(snapshot.resolve()), "--output", str(directory.resolve())], cwd=ROOT, env=env, check=True)


def reproduce(run_id, profile, bucket, region):
    if len(run_id) != 24 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError("Expected a 24-character accepted run identifier")
    source = RUNS / run_id
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["exploratory"]:
        raise ValueError("Exploratory runs cannot satisfy accepted reproduction")
    for name, expected in manifest["artifacts"].items():
        if digest(source / name) != expected:
            raise ValueError(f"Preserved artifact checksum mismatch: {name}")
    if environment()["python"] != manifest["environment"]["python"]:
        raise ValueError(f"Use Python {manifest['environment']['python']} to restore this environment")
    for key in ('system', 'machine'):
        if environment()[key] != manifest['environment'][key]:
            raise ValueError("Reproduction requires the recorded platform")
    destination = ROOT / "data/forecasts/reproductions" / run_id
    destination.mkdir(parents=True, exist_ok=False)
    archive = source / "code.tar"
    code = destination / "code"
    with tarfile.open(archive) as f:
        f.extractall(code, filter="data")
    python = destination / "venv/bin/python"
    subprocess.run([sys.executable, "-m", "venv", str(destination / "venv")], check=True)
    subprocess.run([str(python), "-m", "pip", "--isolated", "install", "--index-url", "https://pypi.org/simple",
                    "-r", str(code / "forecasts/requirements-lock.txt")], check=True)
    # The restored revision handles input loading and evaluation, not the calling checkout.
    env = os.environ.copy()
    env['PYTHONPATH'] = str(code)
    subprocess.run([str(python), "-m", "forecasts.run", "replay", "--source", str(source),
                    "--destination", str(destination / "result"), "--profile", profile, "--bucket", bucket,
                    "--region", region], cwd=code, env=env, check=True)


def replay(source, destination, profile, bucket, region):
    import numpy as np
    import pyarrow.parquet as pq
    from forecasts.evaluation import evaluate
    from forecasts.snapshot import InputReader
    manifest = json.loads((source / "manifest.json").read_text())
    if environment() != manifest["environment"]:
        raise ValueError("Restored dependency environment differs from the accepted run")
    if digest(ROOT / "forecasts/requirements-lock.txt") != manifest["lock_sha256"]:
        raise ValueError("Restored dependency lock differs")
    snapshot = destination / "snapshot"
    _, tables = load(profile, region, bucket, manifest["config"]["snapshot_id"], snapshot)
    report = evaluate(InputReader(tables), manifest["config"], destination, restore_models=source / "models")
    expected = pq.read_table(source / "predictions.parquet").to_pydict()
    actual = pq.read_table(destination / "predictions.parquet").to_pydict()
    tolerance = manifest["config"]["tolerance"]
    for name in expected:
        if '_q' in name or '_raw_q' in name or name == 'target':
            np.testing.assert_allclose(np.array(actual[name], dtype=float), np.array(expected[name], dtype=float),
                                       atol=tolerance['absolute'], rtol=tolerance['relative'], equal_nan=True)
        elif actual[name] != expected[name]:
            raise ValueError(f"Prediction metadata differs: {name}")
    original_report = json.loads((source / "report.json").read_text())
    def compare(a, b):
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
            np.testing.assert_allclose(a, b, atol=tolerance['absolute'], rtol=tolerance['relative'])
        elif a != b:
            raise ValueError("Reproduced report metadata differs")
    compare(json.loads(json.dumps(report)), original_report)
    (destination / "verification.json").write_text(json.dumps({"run_id": manifest["run_id"], "predictions_match": True,
                                                               "scores_match": True, "tolerance": tolerance}, indent=2))
    print(f"Verified reproduction {manifest['run_id']}", flush=True)


def main():
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
        manifest, _ = read_local(args.snapshot)
        config = json.loads(args.config.read_text())
        if manifest["snapshot_id"] != config["snapshot_id"]:
            parser.error("Snapshot differs from frozen configuration")
        directory, _ = prepare(args.config, args.exploratory)
        print(f"Frozen run {directory.name}", flush=True)
        run_flow(directory, args.snapshot)
    elif args.command == "reproduce":
        reproduce(args.run_id, args.profile, args.bucket, args.region)
    else:
        replay(args.source, args.destination, args.profile, args.bucket, args.region)


if __name__ == "__main__":
    main()
