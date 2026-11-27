"""Issue or read a day-ahead forecast edition."""
import argparse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, field_validator, model_validator,
)

from coppersushi.pipelines.market_data.resolution import (
    FORECAST_POLICY, ConflictingPrices, DerivedPrice, PolicyId, PublishedPrice,
)
from forecasts.config import MODEL_METHOD, QUANTILES, RunConfig
from forecasts.inputs.fresh_sources import required_lag_dates
from forecasts.model.contracts import Reference
from forecasts.model.coverage import STATIC_INPUT_POLICY
from forecasts.provenance import digest, source_hashes
from forecasts.market import BERLIN, cutoff, quarters, require_quarters
from forecasts.model.prediction import predict_day
from forecasts.inputs.input_types import Report
from forecasts.inputs.market_archive import ArchiveHistory
from forecasts.inputs.selection import InputReader, PriceHistoryReader
from forecasts.inputs.snapshot import read_local
from forecasts.model.features import build_day_features
from forecasts.model.training import load_models


def main() -> None:
    """Issue from archived editions or explicitly reconstruct a frozen snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read", type=Path, metavar="EDITION", help="Read the edition and record first observed availability")
    parser.add_argument("--delivery-date", type=date.fromisoformat)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--snapshot", type=Path, help="Frozen historical snapshot; requires --replay")
    source.add_argument("--archive-bucket", help="Private market archive; defaults to COPPERSUSHI_CACHE_BUCKET")
    parser.add_argument("--run", type=Path, help="Saved monthly fits and their manifest")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", action="store_true", help="Reconstruct at the historical cutoff")
    args = parser.parse_args()
    if args.read:
        if any((args.delivery_date, args.snapshot, args.archive_bucket, args.run, args.output, args.replay)):
            parser.error("--read accepts only the edition path")
        print(json.dumps(read_edition(args.read), allow_nan=False))
        return
    if not all((args.delivery_date, args.run, args.output)):
        parser.error("Issuance requires --delivery-date, --run and --output")
    if args.snapshot and not args.replay:
        parser.error("--snapshot requires --replay")
    bucket = None if args.snapshot else args.archive_bucket or os.environ.get("COPPERSUSHI_CACHE_BUCKET")
    if not (args.snapshot or bucket):
        parser.error("Set --archive-bucket or COPPERSUSHI_CACHE_BUCKET, or explicitly replay a snapshot")
    try:
        issued = issue_day(args.delivery_date, args.snapshot, args.run, args.output,
                           replay=args.replay, archive_bucket=bucket)
    except RequiredPricesUnavailable as error:
        print(json.dumps({"status": "retryable", "reason": str(error), "input_manifest": error.input_manifest}),
              file=sys.stderr)
        raise SystemExit(1) from error
    if not issued:
        raise SystemExit(1)


class RequiredPricesUnavailable(ValueError):
    """A retryable issue attempt, with every selected or unavailable input."""

    def __init__(self, message: str, input_manifest: Report) -> None:
        super().__init__(message)
        self.input_manifest = input_manifest


def issue_day(day: date, snapshot: Path | None, run: Path, output: Path, *, replay: bool,
              archive_bucket: str | None = None) -> bool:
    """Publish a local forecast file once, by the live deadline when applicable."""
    started = datetime.now(timezone.utc)
    deadline = cutoff(day)
    issue_date = deadline.astimezone(BERLIN).date()
    if (snapshot is None) == (archive_bucket is None):
        raise ValueError("Choose exactly one issue input: market archive or snapshot")
    if snapshot is not None and not replay:
        raise ValueError("Live issuance requires the market archive")
    if archive_bucket and replay and started < deadline:
        raise ValueError("Archive replay requires a delivery day whose issue cutoff has passed")
    if not replay and started.astimezone(BERLIN).date() < issue_date:
        raise ValueError("Live issue opens on the day before delivery")
    input_cutoff = deadline if replay else min(started, deadline)
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
    fit_manifest_digest = digest(run / "manifest.json")
    reader: PriceHistoryReader
    input_evidence: Report

    mode = "reconstruction" if replay else "live"

    def missed_edition(reason: str, evidence: Report) -> Report:
        return {
            "delivery_date": day.isoformat(), "status": "missed", "mode": mode,
            "recorded_at": datetime.now(timezone.utc).isoformat(), "deadline": deadline.isoformat(),
            "input_cutoff": input_cutoff.isoformat(), "run_id": manifest.run_id, "fit_month": fold.isoformat(),
            "run_manifest_sha256": fit_manifest_digest, "reason": reason, **evidence,
        }

    def record_miss(reason: str, evidence: Report) -> bool:
        _write_edition(output, missed_edition(reason, evidence))
        return False

    if archive_bucket is not None:
        try:
            archive = ArchiveHistory(archive_bucket, day, input_cutoff)
            missing = archive.missing()
            if missing and input_cutoff < deadline:
                if datetime.now(timezone.utc) < deadline:
                    raise RequiredPricesUnavailable(
                        f"{len(missing)} required price quarters unavailable by {input_cutoff}",
                        archive.input_manifest(),
                    )
                input_cutoff = deadline
                archive = ArchiveHistory(archive_bucket, day, input_cutoff)
                missing = archive.missing()
        except ConflictingPrices as conflict:
            return record_miss("conflicting_price_evidence", {"input_manifest": {
                "policy": FORECAST_POLICY.id,
                "cutoff": input_cutoff.isoformat(),
                "prices": [{
                    "kind": "conflict",
                    "zone": conflict.zone,
                    "interval": conflict.interval.isoformat(),
                    "implied_price": str(conflict.implied_price) if conflict.implied_price is not None else None,
                    "evidence": [row.model_dump(mode="json") for row in conflict.evidence],
                }],
            }})
        input_evidence = {"input_manifest": archive.input_manifest()}
        if missing:
            return record_miss("required_prices_unavailable_at_cutoff", input_evidence)
        if not replay and datetime.now(timezone.utc) > deadline:
            return record_miss("issuance_window_passed", input_evidence)
        reader = archive
    else:
        assert snapshot is not None
        snapshot_manifest, tables = read_local(snapshot)
        input_evidence = {"snapshot_id": snapshot_manifest["snapshot_id"]}
        reader = InputReader(tables)
    rows = build_day_features(reader, day, live=not replay, issue_time=input_cutoff if not replay else started,
                              require_complete=True)
    forecast = predict_day(rows, models, reference, config)
    created = datetime.now(timezone.utc)
    if not replay and created > deadline:
        return record_miss("deadline_passed_during_prediction", input_evidence)
    source = Path(__file__).resolve().parent
    payload = {
        "delivery_date": day.isoformat(), "status": "reconstructed" if replay else "issued",
        "mode": mode,
        "created_at": created.isoformat(), "deadline": deadline.isoformat(),
        "input_cutoff": input_cutoff.isoformat(),
        **input_evidence, "training_snapshot_id": config.snapshot_id,
        "run_id": manifest.run_id, "fit_month": fold.isoformat(),
        "run_manifest_sha256": fit_manifest_digest,
        "prediction_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, text=True).strip(),
        "source_sha256": source_hashes(source),
        "pixi_lock_sha256": digest(source.parent / "pixi.lock"),
        "quantiles": config.quantiles, "method": forecast.selected_model,
        "quarters": [{"delivery_utc": ts.isoformat(), "prices": prices.tolist(), "reference": ref.tolist()}
                     for ts, prices, ref in zip(rows["delivery_utc"], forecast.ordered[forecast.selected_model],
                                                forecast.ordered["reference"], strict=True)],
    }
    payload["issued_at"] = None if replay else datetime.now(timezone.utc).isoformat()
    if replay:
        _write_edition(output, payload)
        return True
    return _publish_live(output, payload, deadline, lambda reason: missed_edition(reason, input_evidence))


def read_edition(output: Path) -> Report:
    """Validate the published edition before recording first observed availability."""
    with output.open("rb") as source:
        raw = source.read()
        state = os.fstat(source.fileno())
        if state.st_nlink != 1 or not os.path.samestat(state, output.stat()):
            raise ValueError(f"Forecast publication is unfinished or changed during read: {output}")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("status") not in ("issued", "reconstructed", "missed"):
        raise ValueError("Invalid forecast edition")
    if data["status"] == "issued":
        _IssuedEdition.model_validate_json(raw)
        receipt = output.with_name(f"{output.name}.availability.json")
        sha256 = hashlib.sha256(raw).hexdigest()
        try:
            _write_edition(receipt, {"edition_sha256": sha256,
                                     "first_observed_at": datetime.now(timezone.utc).isoformat()})
        except FileExistsError:
            pass
        evidence = _Availability.model_validate_json(receipt.read_bytes())
        if evidence.edition_sha256 != sha256:
            raise ValueError("Availability receipt does not match the forecast edition")
        data["availability"] = evidence.model_dump(mode="json")
    return data


def _publish_live(output: Path, payload: Report, deadline: datetime,
                  missed: Callable[[str], Report]) -> bool:
    """Keep the staged link until the final publication attempt has been timed."""
    with _stage_edition(output, payload) as staged:
        if datetime.now(timezone.utc) <= deadline:
            os.link(staged, output)
            if datetime.now(timezone.utc) <= deadline:
                return True
            # A reader cannot witness the provisional edition while the staging link exists.
            with _stage_edition(output, missed("deadline_passed_during_publication")) as failure:
                os.replace(failure, output)
            return False
    _write_edition(output, missed("deadline_passed_before_publication"))
    return False


def _write_edition(output: Path, payload: Report) -> None:
    with _stage_edition(output, payload) as staged:
        os.link(staged, output)


@contextmanager
def _stage_edition(output: Path, payload: Report) -> Iterator[str]:
    with NamedTemporaryFile(mode="w", dir=output.parent, delete=False) as staging:
        path = Path(staging.name)
        try:
            json.dump(payload, staging, allow_nan=False)
            staging.close()
            yield staging.name
        except BaseException:
            # An interrupted publisher must leave any provisional edition unreadable.
            if path.exists() and path.stat().st_nlink == 1:
                path.unlink()
            raise
        else:
            path.unlink(missing_ok=True)


type _Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
type _Nonempty = Annotated[str, StringConstraints(pattern=r"\S")]
type _QuantileValues = Annotated[list[FiniteFloat], Field(min_length=len(QUANTILES), max_length=len(QUANTILES))]
type _SelectedPrice = Annotated[PublishedPrice | DerivedPrice, Field(discriminator="kind")]


class _QuarterForecast(BaseModel):
    """Model and reference quantiles for one physical delivery quarter."""

    model_config = ConfigDict(strict=True, extra="forbid")

    delivery_utc: AwareDatetime
    prices: _QuantileValues
    reference: _QuantileValues

    @field_validator("prices", "reference")
    @classmethod
    def check_order(cls, values: list[float]) -> list[float]:
        if any(lower > upper for lower, upper in zip(values, values[1:])):
            raise ValueError("Forecast quantiles must be nondecreasing")
        return values


class _InputManifest(BaseModel):
    """Resolved lag prices and the cutoff used to select them."""

    model_config = ConfigDict(strict=True, extra="forbid")

    policy: PolicyId
    cutoff: AwareDatetime
    prices: list[_SelectedPrice]


class _IssuedEdition(BaseModel):
    """The live forecast file whose first read can establish availability."""

    model_config = ConfigDict(strict=True, extra="forbid")

    status: Literal["issued"]
    mode: Literal["live"]
    delivery_date: date
    created_at: AwareDatetime
    issued_at: AwareDatetime
    deadline: AwareDatetime
    input_cutoff: AwareDatetime
    input_manifest: _InputManifest
    training_snapshot_id: _Digest
    run_id: _Nonempty
    fit_month: date
    run_manifest_sha256: _Digest
    prediction_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    source_sha256: Annotated[dict[_Nonempty, _Digest], Field(min_length=1)]
    pixi_lock_sha256: _Digest
    quantiles: list[FiniteFloat]
    method: str
    quarters: list[_QuarterForecast]

    @model_validator(mode="after")
    def check_edition(self) -> "_IssuedEdition":
        day = self.delivery_date
        if self.fit_month != day.replace(day=1):
            raise ValueError("Fit month must match the forecast delivery date")
        if self.deadline != cutoff(day) or not self.input_cutoff <= self.created_at <= self.issued_at <= self.deadline:
            raise ValueError("Issued forecast times do not meet the delivery deadline")
        if self.method != MODEL_METHOD or tuple(self.quantiles) != QUANTILES:
            raise ValueError("Issued forecast must use the configured method and quantiles")
        require_quarters((row.delivery_utc for row in self.quarters), day, day + timedelta(days=1), "Forecast")
        self._check_inputs()
        return self

    def _check_inputs(self) -> None:
        day = self.delivery_date
        inputs = self.input_manifest
        if inputs.policy != FORECAST_POLICY.id or inputs.cutoff != self.input_cutoff:
            raise ValueError("Price evidence policy or cutoff does not match the forecast decision")
        expected = {interval for lag in required_lag_dates(day) for interval in quarters(lag, lag + timedelta(days=1))}
        if len(inputs.prices) != len(expected) or {price.interval for price in inputs.prices} != expected:
            raise ValueError("Price evidence must cover exactly the required Berlin lag quarters")
        for price in inputs.prices:
            if price.zone != "DE-LU" or price.policy_id != inputs.policy or not price.evidence:
                raise ValueError(f"Missing or inapplicable price evidence for {price.interval}")
            for row in price.evidence:
                if (not row.edition_key.strip() or row.publisher not in FORECAST_POLICY.publishers
                        or row.interval != price.interval or row.received_at > row.visible_at
                        or row.available_at > inputs.cutoff):
                    raise ValueError(f"Ineligible price evidence for {price.interval}")


class _Availability(BaseModel):
    """First successful read of the content identified by its digest."""

    model_config = ConfigDict(extra="forbid")
    edition_sha256: _Digest
    first_observed_at: AwareDatetime


class _RunManifest(BaseModel):
    """The saved run fields needed to identify and verify a monthly fit."""

    model_config = ConfigDict(strict=True)
    run_id: _Nonempty
    artifacts: dict[str, _Digest]
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
    offsets: _QuantileValues
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
