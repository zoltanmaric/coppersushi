"""Exercise immutable issue authority and trusted remote timing."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from pathlib import Path
from threading import Lock
from typing import Any
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from botocore.exceptions import ClientError

from coppersushi.pipelines.market_data.resolution import Evidence, FORECAST_POLICY, PublishedPrice
from forecasts.config import MODEL_METHOD, QUANTILES, RunConfig
from forecasts.inputs.fresh_sources import required_lag_dates
from forecasts.inputs.snapshot import canonical, identity
from forecasts.market import cutoff, quarters
from forecasts.model.coverage import STATIC_INPUT_POLICY
from forecasts.operations import jobs
from forecasts.operations.artifacts import Artifacts, MissingArtifact, ObjectPin


class VersionedS3:
    """Minimal S3 with versioned reads and atomic If-None-Match writes."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.objects: dict[tuple[str, str], list[tuple[str, bytes, datetime]]] = {}
        self.lock = Lock()

    def put_object(self, *, Bucket: str, Key: str, Body: bytes,
                   IfNoneMatch: str, ChecksumSHA256: str) -> dict:
        assert IfNoneMatch == "*" and ChecksumSHA256
        with self.lock:
            if (Bucket, Key) in self.objects:
                raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
            pin = self.stage(Bucket, Key, Body)
        return {"VersionId": pin.version_id}

    def get_object(self, *, Bucket: str, Key: str, VersionId: str | None = None) -> dict:
        versions = self.objects.get((Bucket, Key), [])
        hits = [entry for entry in reversed(versions) if VersionId is None or entry[0] == VersionId]
        if not hits:
            raise ClientError({"Error": {"Code": "NoSuchVersion" if VersionId else "NoSuchKey"}}, "GetObject")
        version, raw, timestamp = hits[0]
        return {"VersionId": version, "Body": BytesIO(raw), "LastModified": timestamp}

    def stage(self, bucket: str, key: str, data: bytes) -> ObjectPin:
        versions = self.objects.setdefault((bucket, key), [])
        version = str(len(versions) + 1)
        versions.append((version, data, self.now))
        return ObjectPin(bucket=bucket, key=key, version_id=version, sha256=hashlib.sha256(data).hexdigest())


class TestOperations(TestCase):
    def setUp(self) -> None:
        self.day = date(2026, 12, 1)
        self.cutoff = cutoff(self.day)
        self.deadline = self.cutoff + timedelta(minutes=30)
        self.s3 = VersionedS3(self.cutoff)
        self.bucket = "operations"
        self.trace = {"workflow": "daily", "task": "task-123"}
        config = json.loads((Path(__file__).parents[2] / "run-config.json").read_bytes())
        self.config = RunConfig.from_dict(config)
        snapshot_id = config["snapshot_id"]
        pins = {}
        for name in ("manifest.json", "prices.parquet"):
            pins[name] = self.s3.stage(self.bucket, f"snapshots/{snapshot_id}/{name}", b"input")
        self.settings = jobs.Settings(bucket=self.bucket, archive_bucket="archive", snapshot_id=snapshot_id,
                                      snapshot_files=pins, publication_time="11:30", image_digest=f"sha256:{'a' * 64}",
                                      config=self.s3.stage(self.bucket, "inputs/run-config.json", canonical(config)))
        self.store = Artifacts(self.s3, self.bucket, None)
        self.authority = self._publish_fit_pointer(self.settings)
        s3 = patch.object(jobs.boto3, "client", return_value=self.s3)
        s3.start()
        self.addCleanup(s3.stop)
        clock = patch.object(jobs, "_now", side_effect=lambda: self.s3.now)
        clock.start()
        self.addCleanup(clock.stop)

    def test_conditional_witness_and_read_require_matching_version(self) -> None:
        self._publish_issue()
        with self.assertRaisesRegex(MissingArtifact, r"receipts/2026-12-01.json"):
            jobs.read(self.settings, self.day)
        with ThreadPoolExecutor(max_workers=2) as pool:
            observed = list(pool.map(lambda _: jobs.witness(self.settings, self.day, self.trace), range(2)))
        self.assertEqual(observed[0]["availability"], observed[1]["availability"])
        self.assertEqual(len(self.s3.objects[self.bucket, "receipts/2026-12-01.json"]), 1)

        self.s3.now = self.deadline + timedelta(hours=2)
        accepted = jobs.read(self.settings, self.day)
        self.assertEqual(accepted["run_id"], self.authority.run_id)
        self.assertEqual(accepted["availability"]["edition_version_id"], "1")
        changed = self._edition()
        changed["quarters"][-1]["reference"][-1] += 1
        self.s3.stage(self.bucket, "issues/2026-12-01.json", canonical(changed))
        with self.assertRaisesRegex(ValueError, "receipt version, digest"):
            jobs.read(self.settings, self.day)

    def test_late_publication_or_first_get_leave_dated_misses(self) -> None:
        for delay in ("write", "read"):
            with self.subTest(delay=delay):
                self.s3.objects.pop((self.bucket, "issues/2026-12-01.json"), None)
                self.s3.now = self.deadline if delay == "write" else self.cutoff
                self._publish_issue()
                self.s3.now = self.deadline + timedelta(seconds=1)
                expression = "Invalid S3 publication" if delay == "write" else "first validated read finished after"
                with self.assertRaisesRegex(ValueError, expression):
                    jobs.witness(self.settings, self.day, self.trace)
                with self.assertRaisesRegex(MissingArtifact, "receipts/"):
                    jobs.check(self.settings, self.day, self.trace)
        misses = [json.loads(versions[0][1]) for (bucket, key), versions in self.s3.objects.items()
                  if bucket == self.bucket and key.startswith("attempts/2026-12-01/") and key.endswith("/result.json")]
        self.assertEqual(len(misses), 4)
        self.assertTrue(all(item["status"] == "failed" for item in misses))

    def test_fit_commits_pointer_after_complete_verified_bundle(self) -> None:
        day = self.day
        self.s3.objects.pop((self.bucket, f"fits/{day:%Y-%m}.json"))
        snapshot_id = self.settings.snapshot_id
        prefix = f"snapshots/{snapshot_id}"
        prices = self.s3.stage(self.bucket, f"{prefix}/prices.parquet", b"snapshot prices")
        snapshot = canonical({"snapshot_id": snapshot_id, "files": {"prices": {
            "file": "prices.parquet", "key": prices.key, "sha256": prices.sha256,
        }}})
        manifest = self.s3.stage(self.bucket, f"{prefix}/manifest.json", snapshot)
        settings = self.settings.model_copy(update={"snapshot_files": {"manifest.json": manifest, "prices.parquet": prices}})
        self.s3.stage(self.bucket, prices.key, b"later prices")

        def fake_fit(fit_day: date, pinned_snapshot: Path, config: RunConfig, output: Path, **kwargs: Any) -> str:
            self.assertEqual((pinned_snapshot / "manifest.json").read_bytes(), snapshot)
            self.assertEqual((pinned_snapshot / "prices.parquet").read_bytes(), b"snapshot prices")
            self.assertEqual(config, self.config)
            self.assertEqual(fit_day, day)
            self.assertEqual(kwargs["archive_bucket"], settings.archive_bucket)
            run_id, files = self._bundle_files(settings)
            for name, raw in files.items():
                candidate = output / name
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_bytes(raw)
            return run_id

        with (patch.object(jobs, "fit_bundle", side_effect=fake_fit) as scientific_fit,
              patch.object(jobs, "checkout_identity", return_value=("a" * 40, False))):
            first = jobs.fit(settings, day, self.trace)
            second = jobs.fit(settings, day, self.trace)
        scientific_fit.assert_called_once()
        self.assertEqual(first["fit"], second["fit"])
        self.assertEqual(first["model_hashes"], second["model_hashes"])
        key = self.bucket, f"fits/{day:%Y-%m}.json"
        authority = jobs.FitAuthority.model_validate_json(self.s3.objects[key][0][1])
        self.assertEqual(authority.snapshot_files["prices.parquet"].version_id, prices.version_id)
        self.assertEqual(authority.run_id, first["run_id"])
        self.assertTrue(all(self.store.pinned(pin).pin == pin for pin in authority.files.values()))

    def test_fit_artifacts_resolve_pinned_versions_during_issue(self) -> None:
        name = f"models/{self.day}/prices.cbm"
        original_pin = self.authority.files[name]
        self.s3.stage(self.bucket, original_pin.key, b"unapproved later version")

        def fake_issue(day: date, snapshot: Path | None, run: Path, output: Path, **kwargs: Any) -> bool:
            self.assertEqual((run / name).read_bytes(), b"bundle artifact")
            self.assertEqual(day, self.day)
            self.assertIsNone(snapshot)
            self.assertEqual(kwargs["publication_deadline"], self.deadline)
            output.write_bytes(canonical(self._edition()))
            return True

        self.s3.now = self.cutoff + timedelta(seconds=1)
        with (patch.object(jobs.daily, "issue_day", side_effect=fake_issue),
              ThreadPoolExecutor(max_workers=2) as pool):
            first, second = pool.map(lambda _: jobs.issue(self.settings, self.day, self.trace), range(2))
        self.assertNotEqual(first["won"], second["won"])
        self.assertEqual(first["issue"], second["issue"])

        self.s3.objects.pop((self.bucket, original_pin.key))
        with self.assertRaisesRegex(MissingArtifact, r"prices.cbm version 1"):
            jobs.issue(self.settings, self.day, self.trace)

    def test_put_that_completes_after_deadline_never_becomes_authoritative(self) -> None:
        def fake_issue(day: date, snapshot: Path | None, run: Path, output: Path, **kwargs: Any) -> bool:
            output.write_bytes(canonical(self._edition()))
            return True

        put = self.s3.put_object

        def slow_put(**request: Any) -> dict:
            if request["Key"].startswith("issues/"):
                self.assertLess(self.s3.now, self.deadline)
                self.s3.now = self.deadline + timedelta(seconds=1)
            return put(**request)

        self.s3.now = self.deadline - timedelta(seconds=1)
        with (patch.object(jobs.daily, "issue_day", side_effect=fake_issue),
              patch.object(self.s3, "put_object", side_effect=slow_put),
              self.assertRaisesRegex(ValueError, "S3 issue publication missed")):
            jobs.issue(self.settings, self.day, self.trace)
        with self.assertRaisesRegex(ValueError, "Invalid S3 publication"):
            jobs.witness(self.settings, self.day, self.trace)
        self.assertNotIn((self.bucket, f"receipts/{self.day}.json"), self.s3.objects)

    def test_replay_requires_its_namespace_and_exact_dst_grid(self) -> None:
        for day, count in ((date(2026, 3, 29), 92), (date(2026, 10, 25), 100)):
            with self.subTest(day=day):
                self.day = day
                replay = self.settings.model_copy(update={"replay": "parity", "archive_bucket": None})
                self.authority = self._publish_fit_pointer(replay)
                edition = self._edition(replay=True)
                path = f"replays/parity/issues/{day}.json"
                self.s3.stage(self.bucket, path, canonical(edition))
                self.assertEqual(len(jobs.read(replay, day)["quarters"]), count)
                self.assertNotIn((self.bucket, f"issues/{day}.json"), self.s3.objects)
                edition["quarters"].pop()
                self.s3.stage(self.bucket, path, canonical(edition))
                with self.assertRaisesRegex(ValueError, "missing quarters"):
                    jobs.read(replay, day)

    def _bundle_files(self, settings: jobs.Settings) -> tuple[str, dict[str, bytes]]:
        day = self.day.replace(day=1)
        rows = sum(1 for _ in quarters(self.config.train_start, day))
        model_dir = f"models/{day}"
        files = {name: b"bundle artifact" for name in
                 ("snapshot-manifest.json", f"{model_dir}/reference.json",
                  f"{model_dir}/failures.json", f"{model_dir}/prices.cbm")}
        files["config.json"] = canonical(self.config.to_dict())
        if settings.archive_bucket is not None:
            files.update({"coverage.json": b"coverage", "selections.parquet": b"selections"})
        checksums = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
        manifest = {"kind": "monthly_fit", "fit_day": day.isoformat(), "fit_cutoff_utc": cutoff(day).isoformat(),
                    "code_revision": "a" * 40, "exploratory": False, "input_policy": STATIC_INPUT_POLICY,
                    "artifacts": checksums, "config": self.config.to_dict(), "model_method": MODEL_METHOD,
                    "training_rows": rows, "expected_training_rows": rows}
        run_id = identity(manifest)[:24]
        files["manifest.json"] = canonical(dict(manifest, run_id=run_id))
        return run_id, files

    def _publish_fit_pointer(self, settings: jobs.Settings) -> jobs.FitAuthority:
        day = self.day.replace(day=1)
        run_id, files = self._bundle_files(settings)
        store = Artifacts(self.s3, self.bucket, settings.replay)
        pins = {name: store.retain(f"bundles/{run_id}/{name}", raw) for name, raw in files.items()}
        authority = jobs.FitAuthority(fit_day=day, fit_cutoff=cutoff(day), run_id=run_id,
                                     image_digest=settings.image_digest, revision="a" * 40,
                                     snapshot_id=settings.snapshot_id, snapshot_files=settings.snapshot_files,
                                     config=settings.config, archive_bucket=settings.archive_bucket, files=pins, trace=self.trace)
        store.create(f"fits/{day:%Y-%m}.json", canonical(authority.model_dump(mode="json")))
        return authority

    def _publish_issue(self) -> None:
        self.store.create(f"issues/{self.day}.json", canonical(self._edition()))

    def _edition(self, *, replay: bool = False) -> dict:
        day = self.day
        selected = cutoff(day)
        prices = [0.0] * len(QUANTILES)
        edition = {"delivery_date": day.isoformat(), "fit_month": day.replace(day=1).isoformat(),
                   "created_at": selected.isoformat(), "input_cutoff": selected.isoformat(),
                   "training_snapshot_id": self.settings.snapshot_id, "run_id": self.authority.run_id,
                   "run_manifest_sha256": self.authority.files["manifest.json"].sha256,
                   "prediction_revision": "a" * 40, "pixi_lock_sha256": "b" * 64, "method": MODEL_METHOD,
                   "source_sha256": {"daily.py": "c" * 64}, "quantiles": QUANTILES,
                   "quarters": [{"delivery_utc": ts.isoformat(), "prices": prices.copy(), "reference": prices.copy()}
                                for ts in quarters(day, day + timedelta(days=1))]}
        if replay:
            edition.update(status="reconstructed", mode="reconstruction", issued_at=None,
                           deadline=selected.isoformat(), snapshot_id=self.settings.snapshot_id)
        else:
            evidence = [
                PublishedPrice(zone="DE-LU", interval=ts, policy_id=FORECAST_POLICY.id, price=Decimal(40), evidence=(
                    Evidence(publisher="entsoe", attempt_id=UUID(int=lag.toordinal()), edition_key=f"edition-{lag}",
                             interval=ts, zone="DE-LU", destination=None, value=Decimal(40),
                             received_at=selected, visible_at=selected, source_updated_at=None, upstream_source=None),
                )).model_dump(mode="json")
                for lag in required_lag_dates(day)
                for ts in quarters(lag, lag + timedelta(days=1))
            ]
            edition.update(status="issued", mode="live", issued_at=selected.isoformat(),
                           deadline=self.deadline.isoformat(), input_manifest={
                               "policy": FORECAST_POLICY.id, "cutoff": selected.isoformat(), "prices": evidence})
        return edition
