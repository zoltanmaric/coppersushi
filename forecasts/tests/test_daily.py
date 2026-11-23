"""Saved daily forecast artifacts are checked before loading the input snapshot."""
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TextIO
import unittest
from unittest.mock import patch

import numpy as np

from forecasts.contracts import DayForecast
from forecasts.daily import issue_day
from forecasts.coverage import STATIC_INPUT_POLICY
from forecasts.dataset import cutoff, digest, quarters


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
        model = patch("forecasts.training.CatBoostRegressor.load_model")
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
        ), patch("forecasts.daily.InputReader") as reader:
            clock.now.return_value = cutoff(day) - timedelta(minutes=1)
            reader.return_value.features.side_effect = ValueError("Missing eligible prices")
            for replay in (False, True):
                with self.subTest(replay=replay), self.assertRaisesRegex(ValueError, "Missing eligible prices"):
                    issue_day(day, self.saved_run / "snapshot", self.saved_run,
                              self.saved_run / "output.json", replay=replay)
                reader.return_value.features.assert_called_with(
                    day, live=not replay, issue_time=clock.now.return_value, require_complete=True,
                )
                self.assertFalse((self.saved_run / "output.json").exists())

    def test_live_deadline_covers_staging_and_local_publication(self) -> None:
        day = date(2026, 1, 1)
        deadline = cutoff(day)
        output = self.saved_run / "output.json"
        self.manifest()
        quantiles = np.zeros((1, 5))
        forecast = DayForecast({}, {"prices": quantiles, "reference": quantiles}, {}, {}, "prices", "")
        files = set(self.saved_run.iterdir())
        dump, link = json.dump, os.link
        with patch("forecasts.daily.datetime", wraps=datetime) as clock, patch(
            "forecasts.daily.read_local", return_value=({"snapshot_id": "unused"}, {}),
        ), patch("forecasts.daily.InputReader") as reader, patch("forecasts.daily.predict_day", return_value=forecast):
            reader.return_value.features.return_value = {"delivery_utc": [next(quarters(day, day + timedelta(days=1)))]}
            for step, error in (("staging", "before live forecast publication"),
                                ("link", "publication crossed the deadline")):
                with self.subTest(step=step):
                    clock.now.return_value = deadline - timedelta(seconds=1)

                    def stage(data: object, artifact: TextIO, *, allow_nan: bool) -> None:
                        dump(data, artifact, allow_nan=allow_nan)
                        if step == "staging":
                            clock.now.return_value = deadline + timedelta(seconds=1)

                    def publish(source: str, target: Path) -> None:
                        link(source, target)
                        clock.now.return_value = deadline + timedelta(seconds=1)

                    with patch("forecasts.daily.json.dump", side_effect=stage), patch(
                        "forecasts.daily.os.link", side_effect=publish,
                    ) as publication, self.assertRaisesRegex(ValueError, error):
                        issue_day(day, self.saved_run / "snapshot", self.saved_run, output, replay=False)
                    self.assertEqual(publication.call_count, int(step == "link"))
                    self.assertEqual(set(self.saved_run.iterdir()), files)
