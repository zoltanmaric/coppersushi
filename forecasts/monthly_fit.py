"""Fit and publish the model bundle for one delivery month."""
import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory

from forecasts.config import RunConfig, SnapshotId
from forecasts.dataset import ROOT, cutoff, digest
from forecasts.coverage import STATIC_INPUT_POLICY
from forecasts.features import build_features
from forecasts.snapshot import InputReader, canonical, identity, read_local
from forecasts.training import fit_month


def main() -> None:
    """Publish a new monthly model bundle from local, validated training inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-day", required=True, type=_fit_day, help="First delivery day, YYYY-MM-01")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("run-config.json"))
    args = parser.parse_args()
    config = RunConfig.from_dict(json.loads(args.config.read_text()))
    run_id = fit_bundle(args.fit_day, args.snapshot, config, args.output)
    print(f"Published fit {run_id} at {args.output}")


def fit_bundle(fit_day: date, snapshot: Path, config: RunConfig, output: Path) -> str:
    """Fit through the prior delivery day at the first issue cutoff and publish once."""
    if fit_day.day != 1 or fit_day <= config.train_start:
        raise ValueError("Fit day must be the first day of a month after training starts")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Fit output already exists: {output}")
    snapshot_manifest, tables = read_local(snapshot)
    config = replace(config, snapshot_id=SnapshotId(snapshot_manifest["snapshot_id"]))
    reader = InputReader(tables)
    manifest = {
        "kind": "monthly_fit",
        "model_method": config.model_method,
        "fit_day": fit_day.isoformat(),
        "fit_cutoff_utc": cutoff(fit_day).isoformat(),
        "code_revision": _git("rev-parse", "HEAD"),
        "exploratory": bool(_git("status", "--porcelain", "--untracked-files=normal")),
        "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in sorted((ROOT / "forecasts").glob("*.py"))},
        "project_sha256": digest(ROOT / "pyproject.toml"),
        "lock_sha256": digest(ROOT / "pixi.lock"),
        "environment": {
            "python": platform.python_version(), "system": platform.system(), "machine": platform.machine(),
            "packages": {name: version(name) for name in ("catboost", "numpy", "pandera", "polars", "pyarrow")},
        },
        "config": config.to_dict(),
    }
    print(f"Building training features for {fit_day}", flush=True)
    features = build_features(reader, config.train_start, fit_day, complete_from=config.train_start)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".forecast-fit-", dir=output.parent) as temporary:
        staging = Path(temporary) / "bundle"
        model_dir = staging / "models" / fit_day.isoformat()
        print(f"Fitting models and reference for {fit_day}", flush=True)
        fitted = fit_month(reader, features, fit_day, config, model_dir)
        (staging / "config.json").write_bytes(canonical(config.to_dict()))
        (staging / "snapshot-manifest.json").write_bytes(canonical(snapshot_manifest))
        artifacts = {str(path.relative_to(staging)): digest(path) for path in staging.rglob("*") if path.is_file()}
        manifest.update(input_policy=STATIC_INPUT_POLICY, training_rows=fitted.training_rows,
                        expected_training_rows=features.height,
                        created_at=datetime.now(timezone.utc).isoformat(), artifacts=artifacts)
        run_id = identity(manifest)[:24]
        (staging / "manifest.json").write_bytes(canonical(dict(manifest, run_id=run_id)))
        _publish(staging, output)
    return run_id


def _fit_day(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value or parsed.day != 1:
        raise argparse.ArgumentTypeError("Fit day must use YYYY-MM-01")
    return parsed


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _publish(staging: Path, output: Path) -> None:
    # Reserve the path exclusively before moving the complete directory into place.
    # The empty reservation has no manifest and cannot be read as a bundle.
    output.mkdir()
    try:
        staging.rename(output)
    except BaseException:
        # A signal can arrive after the rename; preserve a bundle already published.
        if staging.exists():
            output.rmdir()
        raise


if __name__ == "__main__":
    main()
