from datetime import date, timedelta
import json
import unittest

import polars as pl
import pyarrow as pa

from coppersushi.pipelines.market_data.test_editions import ArchiveS3, DAY, QUARTER, price, publish
from forecasts.inputs.availability import available_at, timing_rejections
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
        next_quarter = QUARTER + timedelta(minutes=15)
        first = publish(store, "entsoe", "DE-LU", [price("40"), price("42").model_copy(update={"interval": next_quarter})])
        second = publish(store, "smard", "DE-LU", [price("41")])
        inputs = reader(store)
        audit = inputs.audit()
        failed = audit.filter(pl.col("source") == "error").sort("cutoff")
        self.assertEqual(failed["valid_utc"].to_list(), [QUARTER, QUARTER])
        self.assertEqual(failed["cutoff"].to_list(), [cutoff(ISSUE_DAY), cutoff(FIT_DAY)])
        for evidence in failed["archive_evidence"]:
            self.assertEqual({row["attempt_id"] for row in json.loads(evidence)},
                             {str(first.attempt_id), str(second.attempt_id)})
        usable = audit.filter(pl.col("valid_utc") == next_quarter)
        self.assertEqual(usable["source"].to_list(), ["archive", "archive"])
        self.assertEqual(usable["price_eur_mwh"].to_list(), [42., 42.])
        fallback = audit.filter(pl.col("valid_utc") == next_quarter + timedelta(minutes=15))
        self.assertEqual(fallback["source"].to_list(), ["snapshot", "snapshot"])
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

    def test_snapshot_rejections_retain_versions_clocks_and_reasons(self) -> None:
        deadline = cutoff(ISSUE_DAY)
        late = deadline + timedelta(seconds=1)
        base = dict(valid_utc=QUARTER, price_eur_mwh=12.0, raw_key="frozen-source",
                    version_id="late-update", source_update_utc=late, retrieved_at_utc=None,
                    timing_evidence="documented")
        variants = [base,
                    dict(base, version_id="late-receipt", timing_evidence="witnessed", retrieved_at_utc=late),
                    dict(base, version_id="no-receipt", source_update_utc=None, timing_evidence="witnessed"),
                    dict(base, version_id="unknown", source_update_utc=None, timing_evidence="unknown"),
                    dict(base, version_id="null", source_update_utc=None, price_eur_mwh=None)]
        inputs = TrainingEditions(ArchiveS3(), "test", "frozen-id",
                                  pa.Table.from_pylist(variants, schema=SCHEMAS["prices"]), ISSUE_DAY, FIT_DAY)
        audit = inputs.feature_audit(ISSUE_DAY, deadline)
        failed = audit.filter(pl.col("valid_utc") == QUARTER).row(0, named=True)
        self.assertEqual((failed["source"], failed["snapshot_id"], failed["cutoff"]), ("missing", "frozen-id", deadline))
        candidates = {row["version_id"]: row for row in json.loads(failed["snapshot_rejections"])}
        self.assertEqual({k: v["reasons"] for k, v in candidates.items()}, {
            "late-update": ["source update after cutoff"], "late-receipt": ["source update after cutoff", "receipt after cutoff"],
            "no-receipt": ["required receipt missing"], "unknown": ["unknown timing evidence"], "null": ["null price"]})
        self.assertEqual(candidates["late-update"]["source_update_utc"], late.isoformat())
        self.assertEqual(candidates["late-receipt"]["retrieved_at_utc"], late.isoformat())
        self.assertIsNone(candidates["no-receipt"]["retrieved_at_utc"])
        self.assertEqual(candidates["unknown"]["raw_key"], "frozen-source")
        absent = audit.filter(pl.col("valid_utc") == QUARTER + timedelta(minutes=15)).row(0, named=True)
        self.assertIsNone(absent["snapshot_rejections"])
        self.assertIn("no candidate for interval", absent["reason"])


    def test_missing_timing_evidence_excludes_a_raw_record(self) -> None:
        frame = pl.DataFrame({"timing_evidence": [None], "source_update_utc": [None], "retrieved_at_utc": [None]},
                             schema={"timing_evidence": pl.String, "source_update_utc": pl.Datetime("us", "UTC"),
                                     "retrieved_at_utc": pl.Datetime("us", "UTC")})
        deadline = cutoff(ISSUE_DAY)
        self.assertFalse(frame.select(available_at(deadline, live=False)).item())
        self.assertEqual(frame.select(timing_rejections(deadline, live=False)).to_series().to_list(),
                         [["unknown timing evidence"]])
