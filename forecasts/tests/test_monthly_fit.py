"""The quarterly coverage audit is durable even when the fit cannot start."""
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import polars as pl
import pyarrow as pa

from coppersushi.pipelines.market_data.test_editions import ArchiveS3, DAY, price, publish
from forecasts.config import RunConfig
from forecasts.inputs.schemas import SCHEMAS
from forecasts.monthly_fit import fit_bundle


class MonthlyCoverageTests(unittest.TestCase):
    def test_failed_audit_keeps_all_selections_without_publishing(self) -> None:
        config = RunConfig.from_dict(json.loads((Path(__file__).parents[1] / "run-config.json").read_bytes()))
        fit_day = date(2026, 11, 1)
        prices = pa.table({"prices": []})
        audit = pl.DataFrame({"valid_utc": ["a", "b", "c"], "source": ["snapshot", "missing", "error"],
                              "reason": [None, "absent", "conflicting editions"]})
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            coverage = root / "audit"
            with patch("forecasts.monthly_fit.read_local", return_value=(
                {"snapshot_id": str(config.snapshot_id)}, {"prices": prices}
            )), patch("forecasts.monthly_fit.boto3.client"), patch(
                "forecasts.monthly_fit.TrainingEditions"
            ) as editions, patch("forecasts.monthly_fit.fit_month") as train:
                editions.return_value.audit.return_value = audit
                with self.assertRaisesRegex(ValueError, "2 ineligible selections"):
                    fit_bundle(fit_day, root / "snapshot", config, root / "model",
                               archive_bucket="market", coverage_output=coverage)
                train.assert_not_called()
            self.assertFalse((root / "model").exists())
            self.assertTrue(pl.read_parquet(coverage / "selections.parquet").equals(audit))
            summary = json.loads((coverage / "coverage.json").read_bytes())
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["fit_cutoff_utc"], "2026-10-31T10:00:00+00:00")
            self.assertEqual(summary["source_counts"], {"snapshot": 1, "missing": 1, "error": 1})

    def test_missing_receipt_metadata_reaches_quarterly_report(self) -> None:
        config = RunConfig.from_dict(json.loads((Path(__file__).parents[1] / "run-config.json").read_bytes()))
        config = replace(config, history_start=DAY - timedelta(days=14), train_start=DAY,
                         evaluation_start=date(2026, 12, 1), end_exclusive=date(2027, 1, 1))
        store = ArchiveS3()
        receipt = publish(store, "smard", "DE-LU", [price()])
        key = f"market-data/attempts/{receipt.attempt_id}"
        store.metadata[key].clear()
        prices = pa.Table.from_pylist([], schema=SCHEMAS["prices"])
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            coverage = root / "audit"
            with patch("forecasts.monthly_fit.read_local", return_value=(
                {"snapshot_id": str(config.snapshot_id)}, {"prices": prices}
            )), patch("forecasts.monthly_fit.boto3.client", return_value=store), patch(
                "forecasts.monthly_fit.datetime", wraps=datetime
            ) as clock:
                clock.now.return_value = datetime(2026, 12, 1, tzinfo=UTC)
                with self.assertRaisesRegex(ValueError, "ineligible selections"):
                    fit_bundle(date(2026, 12, 1), root / "snapshot", config, root / "model",
                               archive_bucket="market", coverage_output=coverage)
            self.assertFalse((root / "model").exists())
            audit = pl.read_parquet(coverage / "selections.parquet")
            failed = audit.filter((pl.col("source") == "error") & (pl.col("purpose") == "label"))
            self.assertEqual(failed.height, 96)
            for row in failed.iter_rows(named=True):
                self.assertIn(f"Missing receipt metadata at {key}", row["reason"])
                self.assertIn(DAY.isoformat(), row["reason"])
                self.assertIn(row["cutoff"].isoformat(), row["reason"])

    def test_overlapping_outputs_are_rejected_before_reading_sources(self) -> None:
        config = RunConfig.from_dict(json.loads((Path(__file__).parents[1] / "run-config.json").read_bytes()))
        with TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            for coverage in (bundle, bundle / "audit", bundle.parent):
                with self.subTest(coverage=coverage), self.assertRaisesRegex(ValueError, "cannot contain"):
                    fit_bundle(date(2026, 11, 1), bundle / "snapshot", config, bundle,
                               archive_bucket="market", coverage_output=coverage)
            self.assertFalse(bundle.exists())
