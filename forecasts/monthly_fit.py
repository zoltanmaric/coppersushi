"""Fit and publish the model bundle for one delivery month."""
import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import shutil
from tempfile import TemporaryDirectory

import boto3
import polars as pl

from coppersushi.pipelines.market_data.resolution import FORECAST_POLICY
from forecasts.config import RunConfig, SnapshotId
from forecasts.provenance import ROOT, checkout_identity, digest, source_hashes
from forecasts.market import cutoff
from forecasts.model.coverage import STATIC_INPUT_POLICY
from forecasts.model.features import build_features
from forecasts.inputs.input_types import Report
from forecasts.inputs.selection import InputReader, PriceHistoryReader
from forecasts.inputs.training_editions import TrainingEditions
from forecasts.inputs.snapshot import canonical, identity, read_local
from forecasts.model.training import fit_month


def main() -> None:
    """Publish a new monthly model bundle from local, validated training inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit-day", required=True, type=_fit_day, help="First delivery day, YYYY-MM-01")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="New model bundle directory")
    parser.add_argument("--archive-bucket", help="Select witnessed free-source prices before frozen rows")
    parser.add_argument("--coverage-output", type=Path, help="New directory for the quarterly input audit")
    parser.add_argument("--audit-only", action="store_true", help="Audit archive and frozen selections without fitting")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("run-config.json"))
    args = parser.parse_args()
    config = RunConfig.from_dict(json.loads(args.config.read_text()))
    if bool(args.archive_bucket) != bool(args.coverage_output):
        parser.error("--archive-bucket and --coverage-output are required together")
    if args.audit_only:
        if not args.archive_bucket or args.output is not None:
            parser.error("--audit-only requires --archive-bucket and --coverage-output, without --output")
        _validate_fit_day(args.fit_day, config)
        _audit_inputs(args.fit_day, config, args.snapshot, args.archive_bucket, args.coverage_output)
        print(f"Quarterly coverage recorded at {args.coverage_output}")
        return
    if args.output is None:
        parser.error("fitting requires --output")
    run_id = fit_bundle(args.fit_day, args.snapshot, config, args.output,
                        archive_bucket=args.archive_bucket, coverage_output=args.coverage_output)
    print(f"Published fit {run_id} at {args.output}")


def fit_bundle(fit_day: date, snapshot: Path, config: RunConfig, output: Path, *,
               archive_bucket: str | None = None, coverage_output: Path | None = None) -> str:
    """Fit through the prior delivery day at the first issue cutoff and publish once."""
    _validate_fit_day(fit_day, config)
    if (archive_bucket is None) != (coverage_output is None):
        raise ValueError("Archive training requires both a market data bucket and coverage output")
    if coverage_output is not None:
        bundle, coverage = output.resolve(), coverage_output.resolve()
        if bundle.is_relative_to(coverage) or coverage.is_relative_to(bundle):
            raise ValueError("Bundle and coverage directories must be separate and cannot contain one another")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Fit output already exists: {output}")
    reader: PriceHistoryReader
    if archive_bucket is not None and coverage_output is not None:
        if cutoff(fit_day) > datetime.now(timezone.utc):
            raise ValueError(f"Fit cutoff {cutoff(fit_day).isoformat()} has not arrived. Use --audit-only for a preflight")
        snapshot_manifest, reader = _audit_inputs(fit_day, config, snapshot, archive_bucket, coverage_output)
    else:
        snapshot_manifest, tables = read_local(snapshot)
        reader = InputReader(tables)
    config = replace(config, snapshot_id=SnapshotId(snapshot_manifest["snapshot_id"]))
    packages = ["forecasts"]
    if archive_bucket is not None:
        packages.append("coppersushi/pipelines/market_data")
    code_hashes = {f"{package}/{name}": checksum for package in packages
                   for name, checksum in source_hashes(ROOT / package).items()}
    if archive_bucket is not None:
        market_day = "coppersushi/pipelines/market_day.py"
        code_hashes[market_day] = digest(ROOT / market_day)
    revision, exploratory = checkout_identity()
    manifest = {
        "kind": "monthly_fit",
        "model_method": config.model_method,
        "fit_day": fit_day.isoformat(),
        "fit_cutoff_utc": cutoff(fit_day).isoformat(),
        "code_revision": revision,
        "exploratory": exploratory,
        "source_sha256": code_hashes,
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
        if coverage_output is not None:
            for name in ("selections.parquet", "coverage.json"):
                shutil.copyfile(coverage_output / name, staging / name)
        artifacts = {str(path.relative_to(staging)): digest(path) for path in staging.rglob("*") if path.is_file()}
        manifest.update(input_policy=STATIC_INPUT_POLICY, training_rows=fitted.training_rows,
                        expected_training_rows=features.height,
                        created_at=datetime.now(timezone.utc).isoformat(), artifacts=artifacts)
        run_id = identity(manifest)[:24]
        (staging / "manifest.json").write_bytes(canonical(dict(manifest, run_id=run_id)))
        _publish(staging, output)
    return run_id


def _audit_inputs(fit_day: date, config: RunConfig, snapshot: Path,
                  bucket: str, output: Path) -> tuple[Report, TrainingEditions]:
    """Persist the complete quarterly selection inventory before admitting rows to a fit."""
    output.mkdir(parents=True, exist_ok=False)
    observed = datetime.now(timezone.utc)
    summary: Report = {
        "observed_at_utc": observed.isoformat(), "fit_cutoff_elapsed": cutoff(fit_day) <= observed,
        "archive_bucket": bucket, "archive_policy": FORECAST_POLICY.id, "snapshot_id": config.snapshot_id,
        "history_start": config.history_start.isoformat(), "train_start": config.train_start.isoformat(),
        "fit_day": fit_day.isoformat(), "fit_cutoff_utc": cutoff(fit_day).isoformat(),
    }
    try:
        manifest, tables = read_local(snapshot)
        if manifest["snapshot_id"] != config.snapshot_id:
            raise ValueError(f"Expected frozen snapshot {config.snapshot_id}, got {manifest['snapshot_id']}")
        reader = TrainingEditions(boto3.client("s3"), bucket, config.snapshot_id, tables["prices"],
                                  config.train_start, fit_day, history_start=config.history_start)
        audit = reader.audit()
        audit.write_parquet(output / "selections.parquet")
        counts = audit.group_by("source").len().sort("source")
        rejected = audit.filter(pl.col("source").is_in(["error", "missing"])).height
        summary.update(source_counts=dict(counts.iter_rows()), rejected_selections=rejected)
        if rejected:
            raise ValueError(f"{rejected} ineligible selections for {fit_day}. See {output / 'selections.parquet'}")
    except Exception as error:
        (output / "coverage.json").write_bytes(canonical(dict(summary, status="failed", reason=str(error))))
        raise
    (output / "coverage.json").write_bytes(canonical(dict(summary, status="complete")))
    return manifest, reader


def _validate_fit_day(fit_day: date, config: RunConfig) -> None:
    if fit_day.day != 1 or fit_day <= config.train_start:
        raise ValueError("Fit day must be the first day of a month after training starts")


def _fit_day(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value or parsed.day != 1:
        raise argparse.ArgumentTypeError("Fit day must use YYYY-MM-01")
    return parsed


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
