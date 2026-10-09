"""Adversarial selector and publication checks using small invented input histories."""
import base64
from datetime import date
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa

from forecasts.dataset import cutoff, digest, stamp
from forecasts.schemas import SCHEMAS, validate
from forecasts.snapshot import InputReader, load, publish, select_records
from forecasts.storage import put_verified

FIXTURES = Path(__file__).parent / "fixtures"


def history():
    result = json.loads((FIXTURES / "candidate-history.json").read_text())
    for group in [result, result["append"]]:
        for source in SCHEMAS:
            for row in group[source]:
                for key in ["valid_utc", "source_valid_utc", "source_update_utc", "retrieved_at_utc"]:
                    if key in row:
                        row[key] = stamp(row[key]) if row[key] else None
    return result


class SnapshotTests(unittest.TestCase):
    def test_post_cutoff_history_does_not_change_selected_versions_or_features(self):
        records = history()
        original = {n: records[n] for n in SCHEMAS}
        enlarged = {n: records[n] + records["append"][n] for n in SCHEMAS}
        day = date(2026, 3, 29)
        before = select_records(original, day)
        after = select_records(enlarged, day)
        self.assertEqual(before, after)
        self.assertEqual(before["weather"][0]["version_id"], "weather-before-future-valid")
        original_tables = {n: validate(n, pa.Table.from_pylist(original[n], schema=SCHEMAS[n])) for n in SCHEMAS}
        enlarged_tables = {n: validate(n, pa.Table.from_pylist(enlarged[n], schema=SCHEMAS[n])) for n in SCHEMAS}
        self.assertEqual(InputReader(original_tables).features(day), InputReader(enlarged_tables).features(day))

    def test_live_selection_requires_retrieval_by_issue_time(self):
        records = history()
        day = date(2026, 3, 29)
        before = select_records({n: records[n] for n in SCHEMAS}, day, live=True, issue_time=cutoff(day))
        self.assertEqual(before["prices"], [])  # Retrospective price retrieval is not witnessed live input.
        self.assertEqual(len(before["weather"]), 1)
        self.assertEqual(len(before["demand"]), 1)

    def test_live_selection_uses_actual_issue_before_the_deadline(self):
        records = history()
        tables = {n: records[n] for n in SCHEMAS}
        day = date(2026, 3, 29)
        selected = select_records(tables, day, live=True, issue_time=stamp("2026-03-28T09:00:00Z"))
        self.assertEqual(selected["demand"], [])  # Retrieved at 09:30, after actual issue but before deadline.
        self.assertEqual(len(selected["weather"]), 1)
        with self.assertRaisesRegex(ValueError, "actual timezone-aware"):
            select_records(tables, day, live=True)
        with self.assertRaisesRegex(ValueError, "after.*deadline"):
            select_records(tables, day, live=True, issue_time=stamp("2026-03-28T10:00:01Z"))

    def test_rejected_new_weather_location_does_not_expand_feature_inventory(self):
        records = history()
        original = {n: records[n] for n in SCHEMAS}
        extra = dict(records["append"]["weather"][0], location="unconfigured-location")
        enlarged = {n: records[n] + ([extra] if n == "weather" else []) for n in SCHEMAS}
        before = InputReader({n: pa.Table.from_pylist(original[n], schema=SCHEMAS[n]) for n in SCHEMAS})
        after = InputReader({n: pa.Table.from_pylist(enlarged[n], schema=SCHEMAS[n]) for n in SCHEMAS})
        self.assertEqual(before.features(date(2026, 3, 29)), after.features(date(2026, 3, 29)))

    def test_schema_rejects_null_keys_and_duplicates(self):
        rows = history()["prices"]
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate("prices", pa.Table.from_pylist(rows + rows, schema=SCHEMAS["prices"]))
        rows[0]["valid_utc"] = None
        with self.assertRaisesRegex(ValueError, "Required"):
            validate("prices", pa.Table.from_pylist(rows, schema=SCHEMAS["prices"]))

    def test_schema_rejects_incompatible_weather_units(self):
        rows = history()["weather"]
        rows[0]["unit"] = "°F"
        with self.assertRaisesRegex(ValueError, "units"):
            validate("weather", pa.Table.from_pylist(rows, schema=SCHEMAS["weather"]))

    def test_missing_manifest_rejects_partial_upload_before_file_reads(self):
        with tempfile.TemporaryDirectory() as directory, patch("forecasts.snapshot.get_verified", side_effect=subprocess.CalledProcessError(1, "get-object")) as get:
            with self.assertRaises(subprocess.CalledProcessError):
                load("fixture", "eu-west-1", "fixture-bucket", "a" * 64, Path(directory))
            self.assertEqual(get.call_count, 1)
            self.assertTrue(get.call_args.args[3].endswith("/manifest.json"))

    def test_existing_object_mismatch_is_not_overwritten(self):
        path = FIXTURES / "prices.json"
        def response(*args):
            if args[2:4] == ("s3api", "list-objects-v2"):
                return {"Contents": [{"Key": "snapshots/fixture/prices.parquet"}]}
            return {"ContentLength": path.stat().st_size, "ChecksumSHA256": base64.b64encode(bytes(32)).decode(), "VersionId": "original"}
        with patch("forecasts.storage.aws", side_effect=response) as calls:
            with self.assertRaisesRegex(ValueError, "checksum/size"):
                put_verified("fixture", "eu-west-1", "fixture-bucket", "snapshots/fixture/prices.parquet", path)
            self.assertTrue(all("put-object" not in call.args for call in calls.call_args_list))

    def test_publication_writes_manifest_after_all_verified_objects(self):
        # Small source fixtures stand in for local inputs; read_local validation is tested separately.
        path = FIXTURES / "prices.json"
        manifest = {"snapshot_id": "fixture", "raw": {"prices": {"key": "raw/prices/fixture/input", "sha256": digest(path), "metadata_key": "raw/prices/fixture/retrieval.json", "metadata_sha256": digest(path)}},
                    "files": {"prices": {"key": "snapshots/fixture/prices.parquet", "file": "prices.parquet"}}}
        with patch("forecasts.snapshot.read_local", return_value=(manifest, {})), patch("forecasts.snapshot.verify_bucket"), patch("forecasts.snapshot.digest", return_value=digest(path)), patch("forecasts.snapshot.PAYLOADS", {"prices": "prices.json"}), patch("forecasts.snapshot.put_verified") as put:
            publish("fixture", "eu-west-1", "fixture-bucket", FIXTURES, FIXTURES)
            self.assertTrue(put.call_args.args[3].endswith("/manifest.json"))
            self.assertEqual(put.call_count, 4)
        with patch("forecasts.snapshot.read_local", return_value=(manifest, {})), patch("forecasts.snapshot.verify_bucket"), patch("forecasts.snapshot.digest", return_value=digest(path)), patch("forecasts.snapshot.PAYLOADS", {"prices": "prices.json"}), patch("forecasts.snapshot.put_verified", side_effect=RuntimeError("interrupted")) as put:
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                publish("fixture", "eu-west-1", "fixture-bucket", FIXTURES, FIXTURES)
            self.assertTrue(all(not call.args[3].endswith("manifest.json") for call in put.call_args_list))


if __name__ == "__main__":
    unittest.main()
