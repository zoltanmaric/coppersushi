"""Issue one delivery day's prices from a fixed monthly model and input snapshot."""
import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile

from forecasts.config import RunConfig
from forecasts.dataset import BERLIN, cutoff, digest
from forecasts.prediction import predict_day
from forecasts.snapshot import InputReader, read_local
from forecasts.tables import feature_table
from forecasts.training import load_models


def main() -> None:
    """Write one forecast to a new JSON file. Historical replay is explicit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-date", type=date.fromisoformat, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True, help="Saved monthly fits and their manifest")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", action="store_true", help="Reconstruct using historical timing assumptions")
    args = parser.parse_args()
    issue_day(args.delivery_date, args.snapshot, args.run, args.output, replay=args.replay)


def issue_day(day: date, snapshot: Path, run: Path, output: Path, *, replay: bool) -> None:
    """Verify inputs and the month's fit, select eligible features, and publish once."""
    started = datetime.now(timezone.utc)
    deadline = cutoff(day)
    issue_date = deadline.astimezone(BERLIN).date()
    if not replay and (started > deadline or started.astimezone(BERLIN).date() != issue_date):
        raise ValueError("Live issue must be on the day before delivery, by the forecast deadline")
    manifest = json.loads((run / "manifest.json").read_text())
    fold = day.replace(day=1)
    model_dir = run / "models" / fold.isoformat()
    config_file = run / "config.json"
    failures_file = model_dir / "failures.json"
    reference_file = model_dir / "reference.json"

    def verify(path: Path) -> None:
        if digest(path) != manifest["artifacts"][str(path.relative_to(run))]:
            raise ValueError(f"Run artifact checksum mismatch: {path.name}")

    for path in (config_file, failures_file, reference_file):
        verify(path)
    config = RunConfig.from_dict(json.loads(config_file.read_text()))
    failures = json.loads(failures_file.read_text())
    for name in config.features:
        if name not in failures:
            verify(model_dir / f"{name}.cbm")
    models, _ = load_models(model_dir, config)
    reference = json.loads(reference_file.read_text())
    snapshot_manifest, tables = read_local(snapshot)
    rows = feature_table(InputReader(tables).features(day, live=not replay, issue_time=started))
    forecast = predict_day(rows, models, reference, config)
    created = datetime.now(timezone.utc)
    if not replay and created > deadline:
        raise ValueError("Deadline passed during computation")
    source = Path(__file__).resolve().parent
    payload = {
        "delivery_date": day.isoformat(), "mode": "reconstruction" if replay else "live",
        "created_at": created.isoformat(), "deadline": deadline.isoformat(),
        "input_cutoff": (deadline if replay else started).isoformat(),
        "snapshot_id": snapshot_manifest["snapshot_id"], "training_snapshot_id": config.snapshot_id,
        "run_id": manifest["run_id"], "fit_month": fold.isoformat(),
        "run_manifest_sha256": digest(run / "manifest.json"),
        "prediction_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True).strip(),
        "source_sha256": {path.name: digest(path) for path in sorted(source.glob("*.py"))},
        "pixi_lock_sha256": digest(source.parent / "pixi.lock"),
        "quantiles": config.quantiles, "method": forecast.selected_model,
        "fallback_reason": forecast.fallback_reason, "prediction_failures": forecast.failures,
        "quarters": [{"delivery_utc": ts.isoformat(), "system": system.tolist(), "reference": ref.tolist()}
                     for ts, system, ref in zip(rows["delivery_utc"], forecast.ordered["system"],
                                                forecast.ordered["reference"], strict=True)],
    }
    with NamedTemporaryFile(mode="w", dir=output.parent, delete_on_close=False) as staging:
        json.dump(payload, staging, allow_nan=False)
        staging.close()
        os.link(staging.name, output)


if __name__ == "__main__":
    main()
