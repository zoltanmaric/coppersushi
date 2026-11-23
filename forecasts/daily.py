"""Issue one delivery day's prices from a fixed monthly model and input snapshot."""
import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, field_validator

from forecasts.config import QUANTILES, RunConfig
from forecasts.contracts import Reference
from forecasts.coverage import STATIC_INPUT_POLICY
from forecasts.dataset import BERLIN, cutoff, digest, quarters
from forecasts.prediction import predict_day
from forecasts.snapshot import InputReader, read_local
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
    manifest = _RunManifest.model_validate_json((run / "manifest.json").read_bytes())
    fold = day.replace(day=1)
    if manifest.input_policy != STATIC_INPUT_POLICY:
        raise ValueError(f"Fit {manifest.run_id} lacks proof of complete historical training; refit {fold}")
    monthly_bundle = manifest.kind == "monthly_fit" or manifest.fit_day is not None
    if monthly_bundle and manifest.fit_day != fold:
        raise ValueError("Bundle fit day must match the first day of the requested delivery month")
    model_dir = run / "models" / fold.isoformat()
    config_file = run / "config.json"
    failures_file = model_dir / "failures.json"
    reference_file = model_dir / "reference.json"

    def verify(path: Path) -> None:
        relative = path.relative_to(run).as_posix()
        expected = manifest.artifacts.get(relative)
        if expected is None:
            raise ValueError(f"Run manifest does not list artifact: {relative}")
        if digest(path) != expected:
            raise ValueError(f"Run artifact checksum mismatch: {path.name}")

    for path in (config_file, failures_file, reference_file):
        verify(path)
    config = RunConfig.from_dict(json.loads(config_file.read_text()))
    if manifest.model_method != config.model_method:
        raise ValueError(f"Fit {manifest.run_id} does not declare the configured method {config.model_method}")
    if not monthly_bundle and not config.evaluation_start <= day < config.end_exclusive:
        raise ValueError("Delivery day is outside the saved monthly fit window")
    if monthly_bundle:
        expected = sum(1 for _ in quarters(config.train_start, fold))
        if (manifest.fit_cutoff_utc != cutoff(fold) or not expected
                or manifest.training_rows != expected or manifest.expected_training_rows != expected):
            raise ValueError(f"Invalid training coverage in fit {manifest.run_id} for {fold}; expected {expected} quarters")
    reference = _SavedReference.model_validate_json(reference_file.read_bytes()).to_reference(config)
    models = load_models(model_dir, config, verify_model=verify)
    snapshot_manifest, tables = read_local(snapshot)
    rows = InputReader(tables).features(day, live=not replay, issue_time=started, require_complete=True)
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
        "run_id": manifest.run_id, "fit_month": fold.isoformat(),
        "run_manifest_sha256": digest(run / "manifest.json"),
        "prediction_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True).strip(),
        "source_sha256": {path.name: digest(path) for path in sorted(source.glob("*.py"))},
        "pixi_lock_sha256": digest(source.parent / "pixi.lock"),
        "quantiles": config.quantiles, "method": forecast.selected_model,
        "quarters": [{"delivery_utc": ts.isoformat(), "prices": prices.tolist(), "reference": ref.tolist()}
                     for ts, prices, ref in zip(rows["delivery_utc"], forecast.ordered[forecast.selected_model],
                                                forecast.ordered["reference"], strict=True)],
    }
    with NamedTemporaryFile(mode="w", dir=output.parent, delete_on_close=False) as staging:
        json.dump(payload, staging, allow_nan=False)
        staging.close()
        os.link(staging.name, output)


class _RunManifest(BaseModel):
    """The saved run fields needed to identify and verify a monthly fit."""

    model_config = ConfigDict(strict=True)
    run_id: Annotated[str, StringConstraints(pattern=r"\S")]
    artifacts: dict[str, Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]]
    kind: str | None = None
    fit_day: date | None = None
    input_policy: str | None = None
    model_method: str | None = None
    fit_cutoff_utc: datetime | None = None
    training_rows: int | None = None
    expected_training_rows: int | None = None


class _SavedReference(BaseModel):
    """Serialized reference calibration with one median per local-clock quarter."""

    model_config = ConfigDict(strict=True, extra="forbid")
    medians: dict[str, FiniteFloat]
    offsets: Annotated[list[FiniteFloat], Field(min_length=len(QUANTILES), max_length=len(QUANTILES))]
    calibration_rows: Annotated[int, Field(gt=0)]
    excluded_rows: Annotated[int, Field(ge=0)]

    @field_validator("medians")
    @classmethod
    def validate_medians(cls, medians: dict[str, float]) -> dict[str, float]:
        if set(medians) != {str(quarter) for quarter in range(96)}:
            raise ValueError("Reference must contain exactly one median for each quarter 0–95")
        return medians

    @field_validator("offsets")
    @classmethod
    def validate_offsets(cls, offsets: list[float]) -> list[float]:
        if any(lower > upper for lower, upper in zip(offsets, offsets[1:])):
            raise ValueError("Reference quantile offsets must be nondecreasing")
        return offsets

    def to_reference(self, config: RunConfig) -> Reference:
        """Produce the domain calibration used by prediction."""
        if self.calibration_rows < config.reference_min_errors:
            raise ValueError("Reference has fewer calibration rows than the fit requires")
        return {"medians": {int(quarter): median for quarter, median in self.medians.items()},
                "offsets": self.offsets, "calibration_rows": self.calibration_rows,
                "excluded_rows": self.excluded_rows}


if __name__ == "__main__":
    main()
