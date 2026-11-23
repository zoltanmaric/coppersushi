"""Saved daily forecast artifacts are checked before loading the input snapshot."""
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from forecasts.daily import issue_day
from forecasts.dataset import digest


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
        self.write("failures.json", {"prices": "fit failed", "weather": "fit failed", "demand": "fit failed"})

    def write(self, name: str, data: object) -> None:
        (self.month / name).write_text(json.dumps(data))

    def manifest(self, **overrides: object) -> None:
        fields: dict[str, object] = {
            "run_id": "old-run", "environment": {"legacy": True},
            "artifacts": {p.relative_to(self.saved_run).as_posix(): digest(p)
                          for p in self.saved_run.rglob("*") if p.is_file() and p.name != "manifest.json"},
        }
        fields.update(overrides)
        (self.saved_run / "manifest.json").write_text(json.dumps(fields))

    def issue(self, day: date = date(2026, 1, 1)) -> None:
        issue_day(day, self.saved_run / "snapshot", self.saved_run,
                  self.saved_run / "output.json", replay=True)

    def test_valid_artifacts_accept_legacy_manifest_metadata(self) -> None:
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
        self.write("failures.json", {"weather": "fit failed", "demand": "fit failed"})
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

    def test_standalone_november_fit_uses_bundle_month_outside_original_evaluation(self) -> None:
        self.month.rename(self.month.with_name("2026-11-01"))
        self.manifest(kind="monthly_fit", fit_day="2026-11-01")
        with patch("forecasts.daily.read_local", side_effect=RuntimeError("Reached snapshot")):
            with self.assertRaisesRegex(RuntimeError, "Reached snapshot"):
                self.issue(date(2026, 11, 24))
        for fit_day in (None, "2026-10-01", "2026-11-02"):
            with self.subTest(fit_day=fit_day):
                self.manifest(kind="monthly_fit", fit_day=fit_day)
                with self.assertRaisesRegex(ValueError, "Bundle fit day must match"):
                    self.issue(date(2026, 11, 24))
