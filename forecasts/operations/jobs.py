"""Run the forecast fit, issue, and independent S3 read steps."""
import argparse
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Annotated, Any
from uuid import uuid4

import boto3
from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints, model_validator

from forecasts import daily
from forecasts.config import MODEL_METHOD, RunConfig
from forecasts.inputs.snapshot import canonical, identity
from forecasts.market import BERLIN, cutoff, quarters
from forecasts.model.coverage import STATIC_INPUT_POLICY
from forecasts.monthly_fit import fit_bundle
from forecasts.operations.artifacts import Artifacts, MissingArtifact, Nonempty, ObjectPin, RunId, Sha256, StoredObject, sha256, under
from forecasts.provenance import checkout_identity

type Trace = Mapping[str, Any]
type Report = dict[str, Any]
type ImageDigest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class Settings(BaseModel):
    """Fixed AWS execution inputs supplied to the workflow and authorized reader."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    bucket: Nonempty
    archive_bucket: Nonempty | None = None
    snapshot_id: Sha256
    snapshot_files: dict[str, ObjectPin]
    config: ObjectPin
    image_digest: ImageDigest
    replay: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")] | None = None
    publication_time: Annotated[str, StringConstraints(pattern=r"^(?:1[1-9]|2[0-3]):[0-5][0-9]$")] | None = None

    @model_validator(mode="after")
    def validate_policy(self) -> "Settings":
        prefix = f"snapshots/{self.snapshot_id}/"
        names = set(self.snapshot_files)
        if names not in ({"manifest.json", "prices.parquet"},
                         {"manifest.json", "prices.parquet", "weather.parquet", "demand.parquet"}):
            raise ValueError("Pin the snapshot manifest and every snapshot table")
        if any(pin.key != prefix + name for name, pin in self.snapshot_files.items()):
            raise ValueError("Snapshot pins must use canonical keys for the selected snapshot")
        if self.replay is None and self.archive_bucket is None:
            raise ValueError("Production requires the market archive")
        return self

    def deadline(self, delivery_day: date) -> datetime:
        """Resolve the explicit preceding-day Berlin publication SLA to UTC."""
        if self.publication_time is None:
            if self.replay is None:
                raise ValueError(f"Live issuance for {delivery_day} needs an agreed Berlin publication time")
            return cutoff(delivery_day)
        return datetime.combine(delivery_day - timedelta(days=1), time.fromisoformat(self.publication_time),
                                BERLIN).astimezone(timezone.utc)


class FitAuthority(BaseModel):
    """Immutable monthly index linking one checked model bundle and its inputs."""

    model_config = ConfigDict(extra="forbid")
    fit_day: date
    fit_cutoff: AwareDatetime
    run_id: RunId
    revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
    image_digest: ImageDigest
    snapshot_id: Sha256
    snapshot_files: dict[str, ObjectPin]
    config: ObjectPin
    archive_bucket: Nonempty | None
    files: dict[str, ObjectPin]
    trace: dict[str, Any]


class ReadReceipt(BaseModel):
    """The first complete validated S3 GET of an immutable live issue."""

    model_config = ConfigDict(extra="forbid")
    date: date
    edition_version_id: Nonempty
    edition_sha256: Sha256
    published_at: AwareDatetime
    observed_at: AwareDatetime
    trace: dict[str, Any]


def fit(settings: Settings, fit_day: date, trace: Trace) -> Report:
    """Fit with pinned inputs and create the immutable delivery-month pointer last."""
    store = _store(settings)
    with _attempt(store, settings, fit_day, "fit", trace) as report, TemporaryDirectory() as temporary:
        if fit_day.day != 1:
            raise ValueError(f"Fit date must be the first day of a delivery month: {fit_day}")
        if settings.replay is None and _now() < cutoff(fit_day):
            raise ValueError(f"Production fit cutoff has not arrived for {fit_day}")
        try:
            pointer, authority, _ = _resolve_fit(store, settings, fit_day)
        except MissingArtifact as error:
            if error.key != store.key(_fit_path(fit_day)):
                raise
        else:
            report.update(_fit_report(pointer, authority))
            return report

        root = Path(temporary)
        snapshot = _snapshot(store, settings, root / "snapshot")
        config = RunConfig.from_dict(json.loads(store.pinned(settings.config).data))
        if config.snapshot_id != settings.snapshot_id:
            raise ValueError("Pinned run configuration names a different snapshot")
        bundle = root / "bundle"
        coverage = root / "coverage" if settings.archive_bucket is not None else None
        try:
            run_id = fit_bundle(fit_day, snapshot, config, bundle, archive_bucket=settings.archive_bucket,
                                coverage_output=coverage)
        finally:
            if coverage is not None and coverage.exists():
                for path in coverage.iterdir():
                    pin = store.retain(f"{report['attempt_path']}/{path.name}", path.read_bytes())
                    report.setdefault("coverage", {})[path.name] = pin.model_dump(mode="json")
        raw = (bundle / "manifest.json").read_bytes()
        manifest = _manifest(raw, fit_day, run_id, settings)
        if manifest["config"] != config.to_dict() or manifest["code_revision"] != report["revision"]:
            raise ValueError("New fit manifest disagrees with the pinned configuration or source revision")
        actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*") if path.is_file()}
        if actual != manifest["artifacts"].keys() | {"manifest.json"}:
            raise ValueError("Fit manifest must enumerate the complete bundle")
        files = {}
        for name in sorted(actual):
            data = under(bundle, name).read_bytes()
            expected = sha256(raw) if name == "manifest.json" else manifest["artifacts"][name]
            if sha256(data) != expected:
                raise ValueError(f"Fit bundle artifact checksum changed: {name}")
            files[name] = store.retain(f"bundles/{run_id}/{name}", data)
        authority = FitAuthority(fit_day=fit_day, fit_cutoff=cutoff(fit_day), run_id=run_id,
                                 revision=manifest["code_revision"], image_digest=settings.image_digest,
                                 snapshot_id=settings.snapshot_id, snapshot_files=settings.snapshot_files,
                                 config=settings.config, archive_bucket=settings.archive_bucket, files=files, trace=dict(trace))
        store.create(_fit_path(fit_day), canonical(authority.model_dump(mode="json")))
        winner, accepted, _ = _resolve_fit(store, settings, fit_day)
        report.update(_fit_report(winner, accepted), candidate_run_id=run_id)
        return report


def issue(settings: Settings, delivery_day: date, trace: Trace) -> Report:
    """Use the delivery month's exact fit to issue an immutable forecast candidate."""
    store = _store(settings)
    with _attempt(store, settings, delivery_day, "issue", trace) as report, TemporaryDirectory() as temporary:
        deadline = settings.deadline(delivery_day)
        live = settings.replay is None
        if live and _now() >= deadline:
            raise ValueError(f"Publication deadline already elapsed for {delivery_day}: {deadline.isoformat()}")
        fit_day = delivery_day.replace(day=1)
        pointer, authority, manifest = _resolve_fit(store, settings, fit_day)
        report.update(_fit_report(pointer, authority))
        root = Path(temporary)
        bundle = root / "bundle"
        for name, pin in authority.files.items():
            path = under(bundle, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(manifest.data if name == "manifest.json" else store.pinned(pin).data)
        snapshot = _snapshot(store, settings, root / "snapshot") if settings.archive_bucket is None else None
        output = root / "edition.json"
        try:
            issued = daily.issue_day(delivery_day, snapshot, bundle, output, replay=not live,
                                     archive_bucket=settings.archive_bucket,
                                     publication_deadline=deadline if live else None)
        except daily.RequiredPricesUnavailable as error:
            report["input_manifest"] = error.input_manifest
            raise
        raw = output.read_bytes()
        if not issued:
            report["scientific_miss"] = json.loads(raw)
            raise ValueError(f"Issue missed for {delivery_day}: {report['scientific_miss']['reason']}")
        _validate_edition(raw, settings, delivery_day, authority)
        if live and _now() >= deadline:
            raise ValueError(f"Publication deadline elapsed before S3 PUT for {delivery_day}")
        version = store.create(_issue_path(delivery_day), raw)
        winner = store.get(_issue_path(delivery_day))
        _validate_edition(winner.data, settings, delivery_day, authority)
        report.update(candidate_sha256=sha256(raw), issue=winner.pin.model_dump(mode="json"),
                      issue_published_at=winner.published_at.isoformat(), won=version == winner.pin.version_id)
        if version is not None and winner.pin != ObjectPin(bucket=settings.bucket, key=winner.pin.key,
                                                         version_id=version, sha256=sha256(raw)):
            raise ValueError(f"Published issue version or content changed for {delivery_day}")
        if live and winner.published_at >= deadline:
            raise ValueError(f"S3 issue publication missed the deadline for {delivery_day}")
        return report


def witness(settings: Settings, delivery_day: date, trace: Trace) -> Report:
    """Witness the first valid live issue with reader credentials, or read a replay."""
    store = _store(settings)
    with _attempt(store, settings, delivery_day, "witness", trace) as report:
        issue_object, edition, fit_report = _read_candidate(store, settings, delivery_day)
        observed = _now()
        report.update(fit_report, issue=issue_object.pin.model_dump(mode="json"),
                      issue_published_at=issue_object.published_at.isoformat(), observed_at=observed.isoformat())
        if settings.replay is None:
            # A prior authorized witness remains valid when called again after the deadline.
            try:
                evidence = _receipt(store, settings, delivery_day, issue_object, edition)
            except MissingArtifact:
                _validate_remote(settings, delivery_day, edition, issue_object, observed)
                receipt = ReadReceipt(date=delivery_day, edition_version_id=issue_object.pin.version_id,
                                      edition_sha256=issue_object.pin.sha256, published_at=issue_object.published_at,
                                      observed_at=observed, trace=dict(trace))
                store.create(_receipt_path(delivery_day), canonical(receipt.model_dump(mode="json")))
                evidence = _receipt(store, settings, delivery_day, issue_object, edition)
            report["receipt"] = evidence
        return _reader_payload(issue_object, fit_report, report.get("receipt"))


def read(settings: Settings, delivery_day: date) -> Report:
    """Read by delivery date and require an on-time matching witness in production."""
    store = _store(settings)
    issue_object, edition, fit_report = _read_candidate(store, settings, delivery_day)
    evidence = None if settings.replay is not None else _receipt(store, settings, delivery_day, issue_object, edition)
    return _reader_payload(issue_object, fit_report, evidence)


def check(settings: Settings, delivery_day: date, trace: Trace) -> Report:
    """Record the deadline outcome independently of the scheduled producer."""
    store = _store(settings)
    with _attempt(store, settings, delivery_day, "check", trace) as report:
        if settings.replay is not None or _now() < settings.deadline(delivery_day):
            raise ValueError("Availability checks require a live deadline that has elapsed")
        data = read(settings, delivery_day)
        report["receipt"] = data["availability"]
        return report


def main() -> None:
    """Read or check a delivery date using the configured AWS credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fit", "issue", "witness", "read", "check"))
    parser.add_argument("--settings-json", required=True)
    parser.add_argument("--delivery-date", required=True, type=date.fromisoformat)
    parser.add_argument("--trace-json", default="{}")
    args = parser.parse_args()
    settings = Settings.model_validate_json(args.settings_json)
    if args.action == "read":
        result = read(settings, args.delivery_date)
    else:
        operation = {"fit": fit, "issue": issue, "witness": witness, "check": check}[args.action]
        result = operation(settings, args.delivery_date, json.loads(args.trace_json))
    print(json.dumps(result, allow_nan=False))


def _store(settings: Settings) -> Artifacts:
    return Artifacts(boto3.client("s3"), settings.bucket, settings.replay)


def _fit_path(day: date) -> str:
    return f"fits/{day:%Y-%m}.json"


def _issue_path(day: date) -> str:
    return f"issues/{day.isoformat()}.json"


def _receipt_path(day: date) -> str:
    return f"receipts/{day.isoformat()}.json"


def _snapshot(store: Artifacts, settings: Settings, directory: Path) -> Path:
    directory.mkdir()
    manifest = store.pinned(settings.snapshot_files["manifest.json"]).data
    data = json.loads(manifest)
    expected = {file["file"]: (file["key"], file["sha256"]) for file in data["files"].values()}
    supplied = {name: (pin.key, pin.sha256) for name, pin in settings.snapshot_files.items() if name != "manifest.json"}
    if data["snapshot_id"] != settings.snapshot_id or supplied != expected:
        raise ValueError("Pinned snapshot inventory does not match its manifest")
    (directory / "manifest.json").write_bytes(manifest)
    for name in expected:
        under(directory, name).write_bytes(store.pinned(settings.snapshot_files[name]).data)
    return directory


def _resolve_fit(store: Artifacts, settings: Settings, fit_day: date) -> tuple[StoredObject, FitAuthority, StoredObject]:
    pointer = store.get(_fit_path(fit_day))
    authority = FitAuthority.model_validate_json(pointer.data)
    if (authority.fit_day != fit_day or authority.fit_cutoff != cutoff(fit_day)
            or authority.snapshot_id != settings.snapshot_id or authority.snapshot_files != settings.snapshot_files
            or authority.archive_bucket != settings.archive_bucket or authority.config != settings.config):
        raise ValueError(f"Fit pointer has different inputs or a wrong cutoff for {fit_day}")
    for name, pin in authority.files.items():
        under(Path("."), name)
        if pin.bucket != settings.bucket or pin.key != store.key(f"bundles/{authority.run_id}/{name}"):
            raise ValueError(f"Fit artifact refers outside its authority namespace: {name}")
    manifest = store.pinned(authority.files["manifest.json"])
    data = _manifest(manifest.data, fit_day, authority.run_id, settings)
    expected = {name: pin.sha256 for name, pin in authority.files.items() if name != "manifest.json"}
    if data["artifacts"] != expected or data["code_revision"] != authority.revision:
        raise ValueError(f"Fit pointer and manifest disagree for {fit_day}")
    return pointer, authority, manifest


def _manifest(raw: bytes, fit_day: date, run_id: str, settings: Settings) -> Report:
    manifest = json.loads(raw)
    config = RunConfig.from_dict(manifest["config"])
    actual = {key: value for key, value in manifest.items() if key != "run_id"}
    expected_rows = sum(1 for _ in quarters(config.train_start, fit_day))
    if (manifest["kind"] != "monthly_fit" or manifest["run_id"] != run_id or identity(actual)[:24] != run_id
            or manifest["fit_day"] != fit_day.isoformat() or manifest["fit_cutoff_utc"] != cutoff(fit_day).isoformat()
            or manifest["exploratory"] is not False or manifest["input_policy"] != STATIC_INPUT_POLICY
            or manifest["model_method"] != MODEL_METHOD or config.snapshot_id != settings.snapshot_id
            or expected_rows <= 0 or manifest["training_rows"] != expected_rows
            or manifest["expected_training_rows"] != expected_rows):
        raise ValueError(f"Invalid monthly fit manifest for {fit_day}")
    model_dir = f"models/{fit_day.isoformat()}"
    required = {"config.json", "snapshot-manifest.json", f"{model_dir}/reference.json",
                f"{model_dir}/failures.json", *(f"{model_dir}/{name}.cbm" for name in config.features)}
    if settings.archive_bucket is not None:
        required.update(("coverage.json", "selections.parquet"))
    if (set(manifest["artifacts"]) != required
            or manifest["artifacts"]["config.json"] != sha256(canonical(config.to_dict()))):
        raise ValueError(f"Incomplete monthly bundle artifacts for {fit_day}")
    return manifest


def _fit_report(pointer: StoredObject, authority: FitAuthority) -> Report:
    return {"fit": pointer.pin.model_dump(mode="json"), "run_id": authority.run_id,
            "run_manifest_sha256": authority.files["manifest.json"].sha256,
            "fit_image_digest": authority.image_digest,
            "model_hashes": {name: pin.sha256 for name, pin in authority.files.items() if name.endswith(".cbm")}}


def _validate_edition(raw: bytes, settings: Settings, day: date, fit: FitAuthority) -> daily.IssuedEdition | daily.ReconstructedEdition:
    edition: daily.IssuedEdition | daily.ReconstructedEdition
    if settings.replay is None:
        edition = daily.validate_issued_edition(raw, delivery_date=day, publication_deadline=settings.deadline(day))
    else:
        edition = daily.validate_reconstructed_edition(raw, delivery_date=day)
        expected_snapshot = settings.snapshot_id if settings.archive_bucket is None else None
        if edition.snapshot_id != expected_snapshot:
            raise ValueError(f"Unexpected replay snapshot for {day}")
    if (edition.run_id != fit.run_id or edition.run_manifest_sha256 != fit.files["manifest.json"].sha256
            or edition.training_snapshot_id != fit.snapshot_id):
        raise ValueError(f"Issue for {day} disagrees with its immutable fit")
    grid = [row.delivery_utc for row in edition.quarters]
    if grid != list(quarters(day, day + timedelta(days=1))) or any(ts.utcoffset() != timedelta(0) for ts in grid):
        raise ValueError(f"Forecast must preserve the exact ordered UTC quarter grid for {day}")
    return edition


def _read_candidate(store: Artifacts, settings: Settings, day: date) -> tuple[StoredObject, daily.IssuedEdition | daily.ReconstructedEdition, Report]:
    # Resolve the fit before the final GET so processing the forecast and its receipt can
    # begin as soon as the response body has been consumed.
    pointer, fit, _ = _resolve_fit(store, settings, day.replace(day=1))
    candidate = store.get(_issue_path(day))
    edition = _validate_edition(candidate.data, settings, day, fit)
    return candidate, edition, _fit_report(pointer, fit)


def _validate_remote(settings: Settings, day: date, edition: daily.IssuedEdition | daily.ReconstructedEdition, issue_object: StoredObject,
                     observed: datetime) -> None:
    if not isinstance(edition, daily.IssuedEdition):
        raise ValueError(f"A live read requires an issued forecast for {day}")
    # S3's LastModified has second precision. The SLA and server timestamps are
    # compared conservatively, and a full validated GET has its own precise time.
    if (issue_object.published_at >= settings.deadline(day)
            or issue_object.published_at < edition.issued_at.replace(microsecond=0)):
        raise ValueError(f"Invalid S3 publication time for {day}: {issue_object.published_at.isoformat()}")
    daily.validate_publication_times(edition, published_at=issue_object.published_at, first_observed_at=observed)


def _receipt(store: Artifacts, settings: Settings, day: date, issue_object: StoredObject, edition: daily.IssuedEdition | daily.ReconstructedEdition) -> Report:
    stored = store.get(_receipt_path(day))
    receipt = ReadReceipt.model_validate_json(stored.data)
    if (receipt.date != day or receipt.edition_version_id != issue_object.pin.version_id
            or receipt.edition_sha256 != issue_object.pin.sha256 or receipt.published_at != issue_object.published_at):
        raise ValueError(f"Availability receipt version, digest or publication time disagrees for {day}")
    _validate_remote(settings, day, edition, issue_object, receipt.observed_at)
    return dict(receipt.model_dump(mode="json"), receipt_version_id=stored.pin.version_id)


def _reader_payload(issue_object: StoredObject, fit_report: Report, receipt: Report | None) -> Report:
    data = json.loads(issue_object.data)
    data["fit_receipt"] = fit_report
    if receipt is not None:
        data["availability"] = receipt
    return data


@contextmanager
def _attempt(store: Artifacts, settings: Settings, day: date, step: str, trace: Trace) -> Iterator[Report]:
    started = monotonic()
    path = f"attempts/{day.isoformat()}/{step}-{uuid4()}"
    report = {"day": day.isoformat(), "step": step, "trace": dict(trace), "attempt_path": path,
              "batch_job_id": os.environ.get("AWS_BATCH_JOB_ID"),
              "batch_job_attempt": os.environ.get("AWS_BATCH_JOB_ATTEMPT"),
              "image_digest": settings.image_digest, "snapshot_id": settings.snapshot_id,
              "snapshot_files": {name: pin.model_dump(mode="json") for name, pin in settings.snapshot_files.items()},
              "config": settings.config.model_dump(mode="json"), "started_at": _now().isoformat()}
    store.retain(f"{path}/started.json", canonical(report))
    try:
        report["revision"], _ = checkout_identity()
        yield report
    except Exception as error:
        report.update(status="failed", reason=str(error), error_type=type(error).__name__)
        raise
    else:
        report["status"] = "complete"
    finally:
        report.update(finished_at=_now().isoformat(), wall_seconds=monotonic() - started,
                      cgroup_peak_bytes=_cgroup_peak())
        store.retain(f"{path}/result.json", canonical(report))


def _cgroup_peak() -> int | None:
    for path in (Path("/sys/fs/cgroup/memory.peak"), Path("/sys/fs/cgroup/memory/memory.max_usage_in_bytes")):
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            continue
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


if __name__ == "__main__":
    main()
