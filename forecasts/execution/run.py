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
import tempfile
import subprocess
import sys
import tarfile
import uuid
from typing import Any

from forecasts.config import RunConfig
from forecasts.execution import data_root
from forecasts.execution.tracking import record_execution
from forecasts.inputs.input_types import Report
from forecasts.inputs.selection import InputReader
from forecasts.inputs.snapshot import canonical, load, read_local
from forecasts.provenance import ROOT, digest


def main() -> None:
    """Dispatch a new local run or reproduction from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--config", type=Path, default=ROOT / "forecasts/run-config.json")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--proposal", type=Path, help="Committed evaluation proposal under wiki/price-forecasting/research")
    p.add_argument("--exploratory", action="store_true")
    p = sub.add_parser("reproduce")
    p.add_argument("run_id")
    p = sub.add_parser("replay", help=argparse.SUPPRESS)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--destination", type=Path, required=True)
    for p in (sub.choices["reproduce"], sub.choices["replay"]):
        transport = p.add_mutually_exclusive_group(required=True)
        transport.add_argument("--snapshot", type=Path, help="A verified local copy of the saved input snapshot")
        transport.add_argument("--profile", help="User-local AWS profile for the saved S3 snapshot")
        p.add_argument("--bucket", help="Private bucket for the saved S3 snapshot")
        p.add_argument("--region", default="eu-west-1")
    args = parser.parse_args()
    if args.command == "run":
        directory, _ = prepare(args.config, args.exploratory, proposal=args.proposal)
        print(f"Frozen run {directory.name}", flush=True)
        run_flow(directory, args.snapshot)
    else:
        if bool(args.profile) != bool(args.bucket):
            parser.error("Provide --snapshot or both --profile and --bucket")
        if args.command == "reproduce":
            reproduce(args.run_id, args.profile, args.bucket, args.region, snapshot=args.snapshot)
        else:
            replay(args.source, args.destination, args.profile, args.bucket, args.region, snapshot=args.snapshot)


def prepare(config_path: Path, exploratory: bool = False, *,
            proposal: Path | None = None) -> tuple[Path, RunConfig]:
    """Freeze committed code and environment definitions for a new attempt.

    Accepted execution restores Pixi's runtime from this archive, independently
    of the launcher's packages. Exploratory execution uses the current checkout.
    """
    config = RunConfig.from_dict(json.loads(config_path.read_text()))
    code = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=normal"))
    if dirty and not exploratory:
        raise ValueError("Accepted runs require committed code; use --exploratory for development")
    if not exploratory and proposal is None:
        raise ValueError("Accepted runs require a committed research proposal; pass --proposal")
    definitions = {
        name: ((ROOT / name).read_bytes() if exploratory else
               subprocess.check_output(["git", "-C", str(ROOT), "show", f"{code}:{name}"]))
        for name in ("pyproject.toml", "pixi.lock")}
    manifest = {"code_revision": code, "exploratory": exploratory, "config": config.to_dict(),
                "model_method": config.model_method,
                "environment_manager": "pixi", "runtime_environment": "runtime",
                "platform": {"system": platform.system(), "machine": platform.machine()},
                "project_sha256": hashlib.sha256(definitions["pyproject.toml"]).hexdigest(),
                "lock_sha256": hashlib.sha256(definitions["pixi.lock"]).hexdigest()}
    if proposal is not None:
        research = ROOT / "wiki/price-forecasting/research"
        proposal = proposal.resolve()
        if proposal.parent != research or proposal.suffix != ".md" or proposal.name == "index.md":
            raise ValueError("Expected a proposal in wiki/price-forecasting/research")
        relative = proposal.relative_to(ROOT).as_posix()
        proposal_bytes = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{code}:{relative}"])
        manifest["proposal"] = {"wiki_path": relative, "git_revision": code,
                                "sha256": hashlib.sha256(proposal_bytes).hexdigest()}
    directory = data_root() / "runs" / uuid.uuid4().hex[:24]
    directory.mkdir(parents=True, exist_ok=False)
    if proposal is not None:
        (directory / "proposal.md").write_bytes(proposal_bytes)
    (directory / "config.json").write_bytes(canonical(config.to_dict()))
    for name, content in definitions.items():
        (directory / name).write_bytes(content)
    with (directory / "code.tar").open('wb') as archive:
        subprocess.run(["git", "-C", str(ROOT), "archive", code], stdout=archive, check=True)
    manifest["code_sha256"] = digest(directory / "code.tar")
    manifest["experiment_fingerprint"] = hashlib.sha256(canonical(manifest)).hexdigest()
    manifest["run_id"] = directory.name
    (directory / "manifest.json").write_bytes(canonical(manifest))
    return directory, config


def run_flow(directory: Path, snapshot: Path) -> None:
    """Execute accepted runs from their archive; keep exploratory runs in checkout.

    Output, Metaflow metadata and tracking live outside the extracted code.
    Start MLflow tracking after runtime setup; record workflow completion or failure.
    """
    directory = directory.resolve()
    config = RunConfig.from_dict(json.loads((directory / "config.json").read_text()))
    manifest = json.loads((directory / "manifest.json").read_text())
    with _execution_code(directory, manifest) as code:
        env = _code_environment(code)
        env.update(METAFLOW_DEFAULT_DATASTORE="local", METAFLOW_DEFAULT_METADATA="local",
                   METAFLOW_DATASTORE_SYSROOT_LOCAL=str(Path(env["FORECAST_DATA_ROOT"]) / "metaflow"),
                   METAFLOW_USER="forecast-local")
        command = ([sys.executable] if manifest["exploratory"] else
                   _restore_runtime(code, manifest, env))
        manifest["environment"] = _environment() if manifest["exploratory"] else _probe_environment(command, code, env)
        if not manifest["exploratory"]:
            manifest["pixi_version"] = subprocess.check_output(["pixi", "--version"], text=True).strip()
        (directory / "manifest.json").write_bytes(canonical(manifest))
        with record_execution(directory, config) as mlflow_run:
            flow_module = _archived_module(code, "flow")
            subprocess.run([*command, "-m", flow_module, "run", "--config", str(directory / "config.json"),
                            "--snapshot", str(snapshot.resolve()), "--output", str(directory),
                            "--mlflow-run", mlflow_run], cwd=code, env=env, check=True)


def reproduce(run_id: str, profile: str | None = None, bucket: str | None = None,
              region: str = "eu-west-1", *, snapshot: Path | None = None) -> Path:
    """Restore and verify a saved run in a new, retained attempt directory."""
    if len(run_id) != 24 or any(c not in '0123456789abcdef' for c in run_id):
        raise ValueError("Expected a 24-character accepted run identifier")
    source = data_root() / "runs" / run_id
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["exploratory"]:
        raise ValueError("Exploratory runs cannot satisfy accepted reproduction")
    if snapshot is not None and "model_method" not in manifest:
        raise ValueError("This archived run requires S3 reproduction; supply --profile and --bucket")
    if snapshot is not None:
        inputs = ["--snapshot", str(snapshot.resolve())]
    elif profile and bucket:
        inputs = ["--profile", profile, "--bucket", bucket, "--region", region]
    else:
        raise ValueError("Provide a local snapshot or an S3 profile and bucket")
    destination = data_root() / "reproductions" / run_id / uuid.uuid4().hex[:24]
    destination.mkdir(parents=True, exist_ok=False)
    attempt = {"attempt_id": destination.name, "source_run_id": run_id, "status": "restoring"}
    status = destination / "attempt.json"
    status.write_bytes(canonical(attempt))
    print(f"Reproduction attempt {destination}", flush=True)
    try:
        for name, expected in manifest["artifacts"].items():
            if digest(source / name) != expected:
                raise ValueError(f"Preserved artifact checksum mismatch: {name}")
        for key in ('system', 'machine'):
            if _environment()[key] != manifest['environment'][key]:
                raise ValueError("Reproduction requires the recorded platform")
        code = destination / "code"
        with tarfile.open(source / "code.tar") as archive:
            archive.extractall(code, filter="data")
        env = _code_environment(code)
        command = _restore_runtime(code, manifest, env)
        if _probe_environment(command, code, env) != manifest["environment"]:
            raise ValueError("Restored dependency environment differs from the accepted run")
        attempt["status"] = "replaying"
        status.write_bytes(canonical(attempt))
        run_module = _archived_module(code, "run")
        subprocess.run([*command, "-m", run_module, "replay", "--source", str(source.resolve()),
                        "--destination", str(destination / "result"), *inputs], cwd=code, env=env, check=True)
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


def replay(source: Path, destination: Path, profile: str | None, bucket: str | None,
           region: str, *, snapshot: Path | None = None) -> None:
    """Verify the frozen inputs, predictions and scores from saved models."""
    import numpy as np
    import pyarrow.parquet as pq
    from forecasts.evaluation.workflow import evaluate
    manifest = json.loads((source / "manifest.json").read_text())
    if _environment() != manifest["environment"]:
        raise ValueError("Restored dependency environment differs from the accepted run")
    _validate_definitions(ROOT, manifest)
    config = RunConfig.from_dict(manifest["config"])
    if snapshot is not None:
        snapshot_manifest, tables = read_local(snapshot)
        if snapshot_manifest["snapshot_id"] != config.snapshot_id:
            raise ValueError("Reproduction requires the saved run's input snapshot")
    elif profile and bucket:
        _, tables = load(profile, region, bucket, config.snapshot_id, destination / "snapshot")
    else:
        raise ValueError("Provide a local snapshot or an S3 profile and bucket")
    report = evaluate(InputReader(tables), config, destination, restore_models=source / "models")
    expected = pq.read_table(source / "predictions.parquet").to_pydict()
    actual = pq.read_table(destination / "predictions.parquet").to_pydict()
    if actual.keys() != expected.keys():
        raise ValueError("Reproduced prediction fields differ")
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


@contextmanager
def _execution_code(directory: Path, manifest: Report) -> Iterator[Path]:
    if manifest["exploratory"]:
        yield ROOT
        return
    if digest(directory / "code.tar") != manifest["code_sha256"]:
        raise ValueError("Frozen code archive differs from the prepared run")
    with tempfile.TemporaryDirectory(prefix="forecast-code-") as temporary:
        code = Path(temporary)
        with tarfile.open(directory / "code.tar") as archive:
            archive.extractall(code, filter="data")
        _validate_definitions(code, manifest)
        yield code


def _restore_runtime(code: Path, manifest: Report, env: dict[str, str]) -> list[str]:
    """Install only the preserved runtime; never resolve a new dependency set."""
    _validate_definitions(code, manifest)
    if manifest["runtime_environment"] != "runtime":
        raise ValueError("Accepted execution requires the runtime environment")
    subprocess.run(["pixi", "install", "--locked", "--environment", "runtime",
                    "--manifest-path", str(code / "pyproject.toml"), "--no-config"],
                   cwd=code, env=env, check=True)
    return ["pixi", "run", "--locked", "--environment", "runtime",
            "--manifest-path", str(code / "pyproject.toml"), "--no-config", "python", "-s"]


def _validate_definitions(code: Path, manifest: Report) -> None:
    definitions = {"pyproject.toml": "project_sha256", "pixi.lock": "lock_sha256"}
    for name, field in definitions.items():
        if digest(code / name) != manifest[field]:
            raise ValueError(f"Frozen dependency definition differs: {name}")


def _code_environment(code: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONUSERBASE", "VIRTUAL_ENV"):
        env.pop(key, None)
    env.update(PYTHONPATH=str(code), PYTHONNOUSERSITE="1", FORECAST_DATA_ROOT=str(data_root()))
    return env


def _probe_environment(command: list[str], code: Path, env: dict[str, str]) -> Report:
    module = _archived_module(code, "run")
    probe = f"import json; from {module} import _environment; print(json.dumps(_environment()))"
    return json.loads(subprocess.check_output([*command, "-c", probe], cwd=code, env=env, text=True))


def _archived_module(code: Path, name: str) -> str:
    """Use the implementation from the frozen layout, including pre-move archives."""
    if (code / "forecasts" / "execution" / f"{name}.py").is_file():
        return f"forecasts.execution.{name}"
    return f"forecasts.{name}"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def _environment() -> dict[str, Any]:
    return {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine(),
            "packages": {d.metadata["Name"].lower(): d.version for d in importlib.metadata.distributions()}}


if __name__ == "__main__":
    main()
