from datetime import date, timedelta
import json
import unittest

import polars as pl
import pyarrow as pa

from coppersushi.pipelines.market_data.test_editions import ArchiveS3, DAY, QUARTER, price, publish
from forecasts.inputs.schemas import SCHEMAS
from forecasts.inputs.training_editions import TrainingEditions
from forecasts.market import cutoff, quarters

ISSUE_DAY = DAY + timedelta(days=1)
FIT_DAY = ISSUE_DAY + timedelta(days=1)


def reader(store: ArchiveS3, fit_day: date = FIT_DAY, *, conflict: bool = False) -> TrainingEditions:
    prices = [dict(valid_utc=t, price_eur_mwh=3.0, raw_key="frozen", version_id="old",
                   source_update_utc=None, retrieved_at_utc=cutoff(FIT_DAY), timing_evidence="assumed")
              for t in quarters(ISSUE_DAY - timedelta(days=14), fit_day)]
    if conflict:
        prices.append(dict(prices[0], valid_utc=QUARTER, version_id="ambiguous", price_eur_mwh=17.0))
    return TrainingEditions(store, "test", "snapshot-id", pa.Table.from_pylist(prices, schema=SCHEMAS["prices"]),
                            ISSUE_DAY, fit_day)


class TrainingEditionsTests(unittest.TestCase):
    def test_issue_and_two_fits_choose_their_visible_editions(self) -> None:
        store = ArchiveS3()
        store.now = cutoff(ISSUE_DAY) - timedelta(minutes=1)
        first = publish(store, "smard", "DE-LU", [price("40")])
        store.now = cutoff(ISSUE_DAY)
        corrected = publish(store, "smard", "DE-LU", [price("50")])
        store.now = cutoff(FIT_DAY) + timedelta(minutes=2)
        late = publish(store, "smard", "DE-LU", [price("60")])

        inputs = reader(store)
        audit = inputs.audit()
        selected = audit.filter(pl.col("valid_utc") == QUARTER).sort("cutoff")
        self.assertEqual(selected["price_eur_mwh"].to_list(), [40.0, 50.0])
        self.assertEqual([json.loads(row)["evidence"][0]["attempt_id"] for row in selected["archive_evidence"]],
                         [str(first.attempt_id), str(corrected.attempt_id)])
        next_fit = FIT_DAY + timedelta(days=1)
        later = reader(store, next_fit).audit().filter(
            (pl.col("valid_utc") == QUARTER) & (pl.col("cutoff") == cutoff(next_fit)))
        self.assertEqual(later["price_eur_mwh"].to_list(), [60.0])
        self.assertEqual(json.loads(later["archive_evidence"][0])["evidence"][0]["attempt_id"], str(late.attempt_id))
        fallback = audit.filter(pl.col("valid_utc") == QUARTER + timedelta(minutes=15))
        self.assertEqual(fallback["source"].to_list(), ["snapshot", "snapshot"])
        self.assertEqual(fallback["version_id"].to_list(), ["old", "old"])
        self.assertEqual(fallback["snapshot_id"].to_list(), ["snapshot-id", "snapshot-id"])
        self.assertEqual(audit.filter(pl.col("purpose") == "reference").height, 14 * 96)
        early = inputs.feature_audit(ISSUE_DAY, cutoff(ISSUE_DAY) - timedelta(minutes=2), live=True)
        self.assertEqual(early["source"].unique().to_list(), ["missing"])

    def test_archive_conflict_blocks_frozen_fallback(self) -> None:
        store = ArchiveS3()
        publish(store, "entsoe", "DE-LU", [price("40")])
        publish(store, "smard", "DE-LU", [price("41")])
        inputs = reader(store)
        failed = inputs.audit().filter(pl.col("source") == "error")
        self.assertIn("Conflicting SDAC", failed["reason"][0])
        with self.assertRaisesRegex(ValueError, "Conflicting SDAC"):
            inputs.price_history(ISSUE_DAY, cutoff(ISSUE_DAY), earliest_day=DAY)

    def test_unreadable_archive_is_fatal_but_absent_archive_allows_snapshot(self) -> None:
        store = ArchiveS3()
        receipt = publish(store, "smard", "DE-LU", [price("40")])
        key = next(key for key in store.objects if key.endswith(".parquet"))
        store.objects[key] = b"corrupt"
        inputs = reader(store)
        audit = inputs.feature_audit(ISSUE_DAY, cutoff(ISSUE_DAY))
        failed = audit.filter(pl.col("source") == "error")
        self.assertEqual(failed.height, 96)
        self.assertIn(str(receipt.attempt_id), failed["reason"][0])
        self.assertIn(cutoff(ISSUE_DAY).isoformat(), failed["reason"][0])
        self.assertEqual(audit.filter(pl.col("source") == "snapshot").height, 3 * 96)
        with self.assertRaisesRegex(ValueError, "Invalid Parquet"):
            inputs.price_history(ISSUE_DAY, cutoff(ISSUE_DAY), earliest_day=DAY)

    def test_snapshot_conflict_reports_only_the_affected_quarter_and_cutoffs(self) -> None:
        audit = reader(ArchiveS3(), conflict=True).audit()
        failed = audit.filter(pl.col("source") == "error").sort("cutoff")
        self.assertEqual(failed["valid_utc"].to_list(), [QUARTER, QUARTER])
        for row, deadline in zip(failed.iter_rows(named=True), (cutoff(ISSUE_DAY), cutoff(FIT_DAY)), strict=True):
            for detail in (DAY.isoformat(), deadline.isoformat(), "ambiguous", "old", "snapshot-id"):
                self.assertIn(detail, row["reason"])
