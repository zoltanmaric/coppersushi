"""Saved daily forecast artifacts are checked before loading the input snapshot."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO
import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from typing import TextIO
import unittest
from unittest.mock import patch
from uuid import UUID

import numpy as np

from coppersushi.pipelines.market_data.resolution import (
    FORECAST_POLICY, ConflictingPrices, Evidence, PriceUnavailable, PublishedPrice,
)
from forecasts.config import QUANTILES
from forecasts.inputs.fresh_sources import required_lag_dates
from forecasts.model.contracts import DayForecast
from forecasts.daily import RequiredPricesUnavailable, issue_day, main, read_edition
from forecasts.model.coverage import STATIC_INPUT_POLICY
from forecasts.provenance import digest
from forecasts.market import cutoff, quarters


class SavedArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.saved_run = Path(temporary.name)
        self.month = self.saved_run / "models/2026-01-01"
        self.month.mkdir(parents=True)
        config = Path(__file__).resolve().parents[1] / "run-config.json"
        (self.saved_run / "config.json").write_bytes(config.read_bytes())
        self.medians = {str(quarter): -1.0 for quarter in range(96)}
        self.reference = {"medians": self.medians, "offsets": [-4, -1, 0, 1, 4],
                          "calibration_rows": 1344, "excluded_rows": 0}
        self.write("reference.json", self.reference)
        self.write("failures.json", {})
        (self.month / "prices.cbm").write_bytes(b"prices")
        model = patch("forecasts.model.training.CatBoostRegressor.load_model")
        model.start()
        self.addCleanup(model.stop)

    def write(self, name: str, data: object) -> None:
        (self.month / name).write_text(json.dumps(data))

    def manifest(self, **overrides: object) -> None:
        fields: dict[str, object] = {
            "run_id": "verified-run", "input_policy": STATIC_INPUT_POLICY, "model_method": "prices",
            "environment": {"legacy": True},
            "artifacts": {p.relative_to(self.saved_run).as_posix(): digest(p)
                          for p in self.saved_run.rglob("*") if p.is_file() and p.name != "manifest.json"},
        }
        fields.update(overrides)
        (self.saved_run / "manifest.json").write_text(json.dumps(fields))

    def issue(self, day: date = date(2026, 1, 1)) -> None:
        issue_day(day, self.saved_run / "snapshot", self.saved_run,
                  self.saved_run / "output.json", replay=True)

    def test_valid_artifacts_accept_unneeded_manifest_metadata(self) -> None:
        self.manifest()
        with patch("forecasts.daily.read_local", side_effect=RuntimeError("Reached snapshot")):
            with self.assertRaisesRegex(RuntimeError, "Reached snapshot"):
                self.issue()

    def test_rejects_corrupt_reference_even_when_its_hash_matches(self) -> None:
        cases = (
            ("medians", {"0": 0.0}, "each quarter"),
            ("medians", {**self.medians, "0": float("nan")}, "finite"),
            ("offsets", [-1, 0, 1], "at least 5"),
            ("offsets", [-2, 1, 0, 1, 2], "nondecreasing"),
            ("calibration_rows", 1343, "fewer calibration"),
            ("excluded_rows", -1, "greater than or equal"),
        )
        for field, value, error in cases:
            with self.subTest(field=field, value=value):
                self.write("reference.json", {**self.reference, field: value})
                self.manifest()
                with self.assertRaisesRegex(ValueError, error):
                    self.issue()

    def test_rejects_corrupt_failure_records(self) -> None:
        for failures, error in ((["prices"], "should be an object"),
                                ({"unknown": "fit failed"}, "unknown feature sets")):
            with self.subTest(failures=failures):
                self.write("failures.json", failures)
                self.manifest()
                with self.assertRaisesRegex(ValueError, error):
                    self.issue()

    def test_rejects_unlisted_artifact(self) -> None:
        self.manifest(artifacts={})
        with self.assertRaisesRegex(ValueError, "does not list artifact: config.json"):
            self.issue()

    def test_requires_a_hash_for_each_model_without_a_saved_failure(self) -> None:
        (self.month / "prices.cbm").unlink()
        self.manifest()
        with self.assertRaisesRegex(ValueError, "does not list artifact: models/2026-01-01/prices.cbm"):
            self.issue()

    def test_rejects_delivery_outside_saved_configuration(self) -> None:
        config_file = self.saved_run / "config.json"
        config = json.loads(config_file.read_text())
        config["evaluation_start"] = "2026-02-01"
        config_file.write_text(json.dumps(config))
        self.manifest()
        with self.assertRaisesRegex(ValueError, "outside the saved monthly fit window"):
            self.issue()

    def test_rejects_fit_without_prices_calendar_method(self) -> None:
        self.manifest(model_method=None)
        with self.assertRaisesRegex(ValueError, "does not declare the configured method prices"):
            self.issue()

    def test_standalone_november_fit_uses_bundle_month_outside_original_evaluation(self) -> None:
        self.month.rename(self.month.with_name("2026-11-01"))
        fold = date(2026, 11, 1)
        count = sum(1 for _ in quarters(date(2025, 10, 15), fold))
        self.manifest(kind="monthly_fit", fit_day=fold.isoformat(), fit_cutoff_utc=cutoff(fold).isoformat(),
                      training_rows=count, expected_training_rows=count)
        with patch("forecasts.daily.read_local", side_effect=RuntimeError("Reached snapshot")):
            with self.assertRaisesRegex(RuntimeError, "Reached snapshot"):
                self.issue(date(2026, 11, 24))
        for fit_day in (None, "2026-10-01", "2026-11-02"):
            with self.subTest(fit_day=fit_day):
                self.manifest(kind="monthly_fit", fit_day=fit_day)
                with self.assertRaisesRegex(ValueError, "Bundle fit day must match"):
                    self.issue(date(2026, 11, 24))

    def test_saved_coverage_is_required_and_recomputed(self) -> None:
        self.manifest(input_policy=None)
        with self.assertRaisesRegex(ValueError, "lacks proof of complete historical training"):
            self.issue()
        count = sum(1 for _ in quarters(date(2025, 10, 15), date(2026, 1, 1)))
        self.manifest(kind="monthly_fit", fit_day="2026-01-01", fit_cutoff_utc=cutoff(date(2026, 1, 1)).isoformat(),
                      training_rows=count - 1, expected_training_rows=count)
        with self.assertRaisesRegex(ValueError, "Invalid training coverage"):
            self.issue()

    def test_recorded_fit_failure_cannot_issue(self) -> None:
        self.write("failures.json", {"prices": "training failed"})
        self.manifest()
        with self.assertRaisesRegex(ValueError, "Failed model fits recorded.*prices: training failed"):
            self.issue()

    def test_live_and_replay_require_complete_inputs_before_writing(self) -> None:
        day = date(2026, 1, 1)
        self.manifest()
        with patch("forecasts.daily.datetime", wraps=datetime) as clock, patch(
            "forecasts.daily.read_local", return_value=({"snapshot_id": "unused"}, {}),
        ), patch("forecasts.daily.InputReader") as reader, patch("forecasts.daily.ArchiveHistory") as archive, patch(
            "forecasts.daily.build_day_features",
        ) as features:
            clock.now.return_value = cutoff(day) - timedelta(minutes=1)
            archive.return_value.missing.return_value = []
            features.side_effect = ValueError("Missing eligible prices")
            for replay in (False, True):
                with self.subTest(replay=replay), self.assertRaisesRegex(ValueError, "Missing eligible prices"):
                    issue_day(day, self.saved_run / "snapshot" if replay else None, self.saved_run,
                              self.saved_run / "output.json", replay=replay, archive_bucket=None if replay else "market")
                features.assert_called_with(
                    reader.return_value if replay else archive.return_value, day, live=not replay,
                    issue_time=clock.now.return_value, require_complete=True,
                )
                self.assertFalse((self.saved_run / "output.json").exists())

    def test_live_deadline_covers_prediction_staging_and_final_link(self) -> None:
        day = date(2026, 1, 1)
        deadline = cutoff(day)
        self.manifest()
        quantiles = np.zeros((1, 5))
        forecast = DayForecast({}, {"prices": quantiles, "reference": quantiles}, {}, {}, "prices", "")
        dump, link = json.dump, os.link
        with patch("forecasts.daily.datetime", wraps=datetime) as clock, patch(
            "forecasts.daily.ArchiveHistory",
        ) as archive, patch("forecasts.daily.build_day_features") as features:
            archive.return_value.missing.return_value = []
            archive.return_value.input_manifest.return_value = {}
            features.return_value = {"delivery_utc": [next(quarters(day, day + timedelta(days=1)))]}
            for step, reason in (("prediction", "deadline_passed_during_prediction"),
                                 ("staging", "deadline_passed_before_publication"),
                                 ("link", "deadline_passed_during_publication")):
                with self.subTest(step=step):
                    output = self.saved_run / f"{step}.json"
                    clock.now.return_value = deadline - timedelta(seconds=1)

                    def stage(data: dict[str, object], artifact: TextIO, *, allow_nan: bool) -> None:
                        dump(data, artifact, allow_nan=allow_nan)
                        if step == "staging" and data["status"] == "issued":
                            clock.now.return_value = deadline + timedelta(seconds=1)

                    def predict(*args: object) -> DayForecast:
                        if step == "prediction":
                            clock.now.return_value = deadline + timedelta(seconds=1)
                        return forecast

                    def publish(source: str, target: Path) -> None:
                        status = json.loads(Path(source).read_text())["status"]
                        self.assertEqual(status, "issued" if step == "link" else "missed")
                        link(source, target)
                        if step == "link":
                            with self.assertRaisesRegex(ValueError, "unfinished"):
                                read_edition(target)
                            self.assertFalse(target.with_name(f"{target.name}.availability.json").exists())
                            clock.now.return_value = deadline + timedelta(seconds=1)

                    with (
                        patch("forecasts.daily.json.dump", side_effect=stage),
                        patch("forecasts.daily.predict_day", side_effect=predict),
                        patch("forecasts.daily.os.link", side_effect=publish) as publication,
                    ):
                        with self.assertRaises(SystemExit) as failure:
                            self.issue_from_cli(day, output)
                        self.assertEqual(failure.exception.code, 1)
                    self.assertEqual(publication.call_count, 1)
                    readback = self.read_from_cli(output)
                    self.assertEqual((readback["status"], readback["mode"], readback["reason"]),
                                     ("missed", "live", reason))
                    self.assertNotIn("availability", readback)

    def test_live_output_still_unreadable_at_deadline_is_missed(self) -> None:
        day = date(2026, 1, 1)
        deadline = datetime.now(UTC) + timedelta(seconds=2)
        output = self.saved_run / "output.json"
        receipt = output.with_name(f"{output.name}.availability.json")
        unlink = Path.unlink

        def release(staged: Path, *, missing_ok: bool = False) -> None:
            if not output.exists() or output.stat().st_nlink != 2:
                unlink(staged, missing_ok=missing_ok)
                return
            self.assertLess(datetime.now(UTC), deadline)
            with self.assertRaisesRegex(ValueError, "unfinished"):
                self.read_from_cli(output)
            sleep(max(0, (deadline - datetime.now(UTC)).total_seconds()) + .05)
            with self.assertRaisesRegex(ValueError, "unfinished"):
                self.read_from_cli(output)
            unlink(staged, missing_ok=missing_ok)
            with self.assertRaisesRegex(ValueError, "finished after its deadline"):
                self.read_from_cli(output)
            self.assertFalse(receipt.exists())

        with patch("forecasts.daily.cutoff", return_value=deadline), patch.object(
            Path, "unlink", autospec=True, side_effect=release,
        ):
            with self.assertRaises(SystemExit) as failure:
                self.make_live_edition(day, deadline - timedelta(seconds=1))
            self.assertEqual(failure.exception.code, 1)
            readback = self.read_from_cli(output)
        self.assertEqual((readback["status"], readback["reason"]),
                         ("missed", "deadline_passed_during_publication"))
        self.assertFalse(receipt.exists())

    def test_archive_records_missed_only_after_cutoff(self) -> None:
        day = date(2026, 1, 1)
        deadline = cutoff(day)
        output = self.saved_run / "output.json"
        self.manifest()
        missing = PriceUnavailable(zone="DE-LU", interval=deadline, policy_id=FORECAST_POLICY.id,
                                   attempt_ids=(), reason="No eligible price")
        with patch("forecasts.daily.datetime", wraps=datetime) as clock, patch(
            "forecasts.daily.ArchiveHistory",
        ) as archive:
            archive.return_value.missing.return_value = [missing]
            archive.return_value.input_manifest.return_value = {"prices": [missing.model_dump(mode="json")]}
            clock.now.return_value = deadline - timedelta(seconds=1)
            with self.assertRaisesRegex(RequiredPricesUnavailable, "required price quarters unavailable") as pending:
                issue_day(day, None, self.saved_run, output, replay=False, archive_bucket="market")
            self.assertEqual(pending.exception.input_manifest["prices"], [missing.model_dump(mode="json")])
            self.assertFalse(output.exists())
            clock.now.return_value = deadline + timedelta(seconds=1)
            for replay, mode in ((False, "live"), (True, "reconstruction")):
                with self.subTest(mode=mode):
                    output = self.saved_run / f"{mode}.json"
                    with self.assertRaises(SystemExit) as failure:
                        self.issue_from_cli(day, output, replay=replay)
                    self.assertEqual(failure.exception.code, 1)
                    archive.assert_called_with("market", day, deadline)
                    edition = self.read_from_cli(output)
                    self.assertEqual((edition["status"], edition["mode"]), ("missed", mode))
                    self.assertEqual(edition["reason"], "required_prices_unavailable_at_cutoff")
                    self.assertEqual(edition["input_cutoff"], deadline.isoformat())
                    self.assertEqual(edition["input_manifest"]["prices"], [missing.model_dump(mode="json")])
                    self.assertNotIn("availability", edition)

    def test_live_final_archive_read_uses_the_deadline_cutoff_for_features(self) -> None:
        day = date(2026, 1, 1)
        deadline = cutoff(day)
        self.manifest()
        with (
            patch("forecasts.daily.datetime", wraps=datetime) as clock,
            patch("forecasts.daily.ArchiveHistory") as archive,
            patch("forecasts.daily.build_day_features", side_effect=ValueError("Reached features")) as features,
        ):
            clock.now.side_effect = [deadline - timedelta(seconds=1), deadline, deadline]
            archive.return_value.missing.side_effect = [[object()], []]
            with self.assertRaisesRegex(ValueError, "Reached features"):
                self.issue_from_cli(day, self.saved_run / "output.json")
            archive.assert_called_with("market", day, deadline)
            features.assert_called_once_with(archive.return_value, day, live=True, issue_time=deadline,
                                             require_complete=True)

    def test_archive_conflict_records_a_missed_edition_with_both_receipts(self) -> None:
        day = date(2026, 1, 1)
        deadline = cutoff(day)
        started = deadline - timedelta(seconds=1)
        interval = next(quarters(day - timedelta(days=1), day))
        evidence = tuple(
            Evidence(
                publisher=publisher, attempt_id=UUID(int=number), edition_key=f"manifest-{number}",
                interval=interval, zone="DE-LU", destination=None, value=Decimal(number),
                received_at=started - timedelta(minutes=1), visible_at=started,
                source_updated_at=None, upstream_source=None,
            )
            for number, publisher in enumerate(("entsoe", "smard"), start=1)
        )
        conflict = ConflictingPrices("DE-LU", interval, evidence)
        self.manifest()
        for final_read in (False, True):
            with (
                self.subTest(final_read=final_read),
                patch("forecasts.daily.datetime", wraps=datetime) as clock,
                patch("forecasts.daily.ArchiveHistory") as archive,
                patch("forecasts.daily.build_day_features") as features,
            ):
                output = self.saved_run / f"conflict-{final_read}.json"
                clock.now.return_value = started
                if final_read:
                    archive.return_value.missing.return_value = [PriceUnavailable(
                        zone="DE-LU", interval=interval, policy_id=FORECAST_POLICY.id,
                        attempt_ids=(), reason="No eligible price",
                    )]
                    archive.side_effect = [archive.return_value, conflict]
                    clock.now.side_effect = [started, deadline, deadline]
                else:
                    archive.side_effect = conflict
                with patch("sys.argv", ["daily", "--delivery-date", day.isoformat(), "--archive-bucket", "market",
                                        "--run", str(self.saved_run), "--output", str(output)]):
                    with self.assertRaises(SystemExit) as failure:
                        main()
                self.assertEqual(failure.exception.code, 1)
                selected_at = deadline if final_read else started
                archive.assert_called_with("market", day, selected_at)
                features.assert_not_called()
                edition = read_edition(output)
                self.assertEqual(edition["status"], "missed")
                self.assertEqual(edition["reason"], "conflicting_price_evidence")
                self.assertEqual(edition["delivery_date"], day.isoformat())
                self.assertEqual(edition["input_manifest"], {
                    "policy": FORECAST_POLICY.id, "cutoff": selected_at.isoformat(),
                    "prices": [{
                        "kind": "conflict", "zone": "DE-LU", "interval": interval.isoformat(),
                        "implied_price": None, "evidence": [row.model_dump(mode="json") for row in evidence],
                    }],
                })

    def test_live_cli_edition_is_retrievable_with_its_input_and_model_evidence(self) -> None:
        day = date(2026, 3, 29)  # Berlin changes to summer time on this delivery day.
        deadline = datetime.now(UTC) + timedelta(minutes=5)
        selected_at = deadline - timedelta(seconds=1)
        observed = deadline + timedelta(minutes=1)

        with patch("forecasts.daily.cutoff", return_value=deadline), patch("forecasts.daily.datetime", wraps=datetime) as clock:
            output, selected = self.make_live_edition(day, selected_at)
            clock.now.return_value = observed
            edition = self.read_from_cli(output)
            clock.now.return_value = observed + timedelta(minutes=1)
            self.assertEqual(self.read_from_cli(output), edition)
        self.assertEqual(edition["run_manifest_sha256"], digest(self.saved_run / "manifest.json"))
        self.assertEqual(edition["input_manifest"], selected)
        self.assertEqual(len(edition["quarters"]), 92)
        self.assertLess(datetime.fromisoformat(edition["issued_at"]), deadline)
        self.assertEqual(datetime.fromisoformat(edition["availability"]["first_observed_at"]), observed)
        self.assertEqual(edition["availability"]["edition_sha256"], digest(output))

        changed = json.loads(output.read_text())
        changed["quarters"][0]["prices"] = [1.0] * len(QUANTILES)
        output.write_text(json.dumps(changed))
        with patch("forecasts.daily.cutoff", return_value=deadline), self.assertRaisesRegex(ValueError, "does not match"):
            read_edition(output)

    def test_invalid_issued_edition_cannot_create_read_receipt(self) -> None:
        day = date(2026, 1, 1)
        deadline = datetime.now(UTC) + timedelta(minutes=5)
        with patch("forecasts.daily.cutoff", return_value=deadline):
            output, _ = self.make_live_edition(day, deadline - timedelta(seconds=1))
        valid = json.loads(output.read_text())
        cases = [
            {"status": "issued"},
            {**valid, "delivery_date": "incorrect-date"},
            {**valid, "fit_month": "2026-02-01"},
            {**valid, "run_manifest_sha256": "invalid"},
            {**valid, "input_manifest": {**valid["input_manifest"], "prices": []}},
            {**valid, "quarters": valid["quarters"][1:]},
            {**valid, "quantiles": [0.5]},
        ]
        for column in ("prices", "reference"):
            invalid = copy.deepcopy(valid)
            invalid["quarters"][0][column] = []
            cases.append(invalid)
        ineligible = copy.deepcopy(valid)
        ineligible["input_manifest"]["prices"][0]["evidence"][0]["visible_at"] = valid["deadline"]
        cases.append(ineligible)
        for index, edition in enumerate(cases):
            with self.subTest(case=index):
                output.write_text(json.dumps(edition))
                with patch("forecasts.daily.cutoff", return_value=deadline), self.assertRaises(ValueError):
                    self.read_from_cli(output)
                self.assertFalse(output.with_name(f"{output.name}.availability.json").exists())

    def test_interrupted_publication_cannot_create_read_receipt(self) -> None:
        day = date(2026, 1, 1)
        output = self.saved_run / "output.json"
        link = os.link

        def interrupted(source: str, target: Path) -> None:
            link(source, target)
            raise OSError("publication interrupted after link")

        with patch("forecasts.daily.os.link", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "publication interrupted"):
                self.make_live_edition(day, cutoff(day) - timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.read_from_cli(output)
        self.assertFalse(output.with_name(f"{output.name}.availability.json").exists())

    def make_live_edition(self, day: date, selected_at: datetime) -> tuple[Path, dict[str, object]]:
        fit_month = day.replace(day=1).isoformat()
        if self.month.name != fit_month:
            self.month = self.month.rename(self.month.with_name(fit_month))
        output = self.saved_run / "output.json"
        self.manifest()
        selected = {
            "policy": FORECAST_POLICY.id,
            "cutoff": selected_at.isoformat(),
            "prices": [
                PublishedPrice(zone="DE-LU", interval=interval, policy_id=FORECAST_POLICY.id, price=Decimal(40), evidence=(
                    Evidence(publisher="entsoe", attempt_id=UUID(int=lag.toordinal()), edition_key=f"price-edition-{lag}",
                             interval=interval, zone="DE-LU", destination=None, value=Decimal(40),
                             received_at=selected_at - timedelta(seconds=1), visible_at=selected_at,
                             source_updated_at=None, upstream_source=None),
                )).model_dump(mode="json")
                for lag in required_lag_dates(day)
                for interval in quarters(lag, lag + timedelta(days=1))
            ],
        }
        intervals = list(quarters(day, day + timedelta(days=1)))
        values = np.zeros((len(intervals), len(QUANTILES)))
        forecast = DayForecast({}, {"prices": values, "reference": values}, {}, {}, "prices", "")
        with (
            patch("forecasts.daily.datetime", wraps=datetime) as clock,
            patch("forecasts.daily.ArchiveHistory") as archive,
            patch("forecasts.daily.build_day_features") as features,
            patch("forecasts.daily.predict_day", return_value=forecast),
        ):
            clock.now.return_value = selected_at
            archive.return_value.missing.return_value = []
            archive.return_value.input_manifest.return_value = selected
            features.return_value = {"delivery_utc": intervals}
            self.issue_from_cli(day, output)
        return output, selected

    def issue_from_cli(self, day: date, output: Path, *, replay: bool = False) -> None:
        args = ["daily", "--delivery-date", day.isoformat(), "--archive-bucket", "market",
                "--run", str(self.saved_run), "--output", str(output)]
        if replay:
            args.append("--replay")
        with patch("sys.argv", args):
            main()

    def read_from_cli(self, output: Path) -> dict:
        captured = StringIO()
        with patch("sys.argv", ["daily", "--read", str(output)]), patch("sys.stdout", captured):
            main()
        return json.loads(captured.getvalue())
