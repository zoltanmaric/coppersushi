"""Adversarial selector and publication checks using small invented input histories."""
import base64
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as pa
import pyarrow.parquet as pq

from forecasts.dataset import PAYLOADS, cutoff, digest, stamp
from forecasts.schemas import SCHEMAS, VERSION, describe, validate
from forecasts.snapshot import InputReader, canonical, identity, load, publish, select_records
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


class MemoryStore:
    """Only the object operations used by the real upload/download helpers."""
    def __init__(self):
        self.objects = {}
        self.interrupt_key = None

    def aws(self, profile, region, service, operation, *args):
        def option(name):
            return args[args.index(name) + 1]
        if operation == "list-objects-v2":
            return {"Contents": [{"Key": k} for k in self.objects if k.startswith(option("--prefix"))]}
        key = option("--key")
        if operation == "put-object":
            if key == self.interrupt_key:
                raise RuntimeError("interrupted")
            if key in self.objects and option("--if-none-match") == "*":
                raise FileExistsError(key)
            self.objects[key] = Path(option("--body")).read_bytes()
            return {}
        payload = self.objects[key]  # Missing objects fail, including unpublished manifests.
        if operation == "get-object":
            Path(args[-1]).write_bytes(payload)
            return {}
        if operation == "head-object":
            return {"ContentLength": len(payload), "ChecksumSHA256": base64.b64encode(hashlib.sha256(payload).digest()).decode(), "VersionId": "fixture"}
        raise AssertionError(f"Unexpected object operation: {operation}")


def write_snapshot(directory):
    """Write a small valid snapshot from the same invented selector history."""
    records = history()
    files, raw = {}, {}
    for name in SCHEMAS:
        path = directory / f"{name}.parquet"
        table = validate(name, pa.Table.from_pylist(records[name], schema=SCHEMAS[name]))
        pq.write_table(table, path)
        files[name] = {"file": path.name, "sha256": digest(path), "bytes": path.stat().st_size,
                       "rows": table.num_rows, "schema": describe(name)}
        archive = directory / PAYLOADS[name]
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"invented raw input")
        metadata = directory / f"{name}-retrieval.json"
        metadata.write_text('{}')
        raw[name] = {"key": f"raw/{name}/fixture/input", "sha256": digest(archive),
                     "metadata_key": f"raw/{name}/fixture/retrieval.json", "metadata_sha256": digest(metadata)}
    manifest = {"schema_version": VERSION, "files": files, "raw": raw}
    snapshot_id = identity(manifest)
    for name, entry in files.items():
        entry["key"] = f"snapshots/{snapshot_id}/{name}.parquet"
    manifest["snapshot_id"] = snapshot_id
    (directory / "manifest.json").write_bytes(canonical(manifest))
    return manifest


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

    def test_interrupted_publication_cannot_load(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory() as temporary, patch("forecasts.storage.aws", store.aws), patch("forecasts.snapshot.verify_bucket"):
            directory = Path(temporary)
            manifest = write_snapshot(directory)
            store.interrupt_key = manifest["files"]["weather"]["key"]
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                publish("fixture", "eu-west-1", "fixture-bucket", directory, directory)
            self.assertIn(manifest["files"]["prices"]["key"], store.objects)
            self.assertNotIn(f"snapshots/{manifest['snapshot_id']}/manifest.json", store.objects)
            with self.assertRaises(KeyError):
                load("fixture", "eu-west-1", "fixture-bucket", manifest["snapshot_id"], directory / "partial-load")

    def test_complete_publication_and_retry_load_identical_content(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory() as temporary, patch("forecasts.storage.aws", store.aws), patch("forecasts.snapshot.verify_bucket"):
            directory = Path(temporary)
            manifest = write_snapshot(directory)
            publish("fixture", "eu-west-1", "fixture-bucket", directory, directory)
            original = dict(store.objects)
            publish("fixture", "eu-west-1", "fixture-bucket", directory, directory)
            self.assertEqual(store.objects, original)
            destination = directory / "loaded"
            loaded, tables = load("fixture", "eu-west-1", "fixture-bucket", manifest["snapshot_id"], destination)
            self.assertEqual(loaded, manifest)
            for name in SCHEMAS:
                self.assertEqual(tables[name].num_rows, manifest["files"][name]["rows"])
                self.assertEqual((destination / f"{name}.parquet").read_bytes(), (directory / f"{name}.parquet").read_bytes())

    def test_conflicting_retry_preserves_published_content(self):
        store = MemoryStore()
        with tempfile.TemporaryDirectory() as temporary, patch("forecasts.storage.aws", store.aws), patch("forecasts.snapshot.verify_bucket"):
            directory = Path(temporary)
            manifest = write_snapshot(directory)
            publish("fixture", "eu-west-1", "fixture-bucket", directory, directory)
            original = dict(store.objects)
            changed = directory / "changed.parquet"
            changed.write_bytes(b"different content")
            with self.assertRaisesRegex(ValueError, "checksum/size"):
                put_verified("fixture", "eu-west-1", "fixture-bucket", manifest["files"]["prices"]["key"], changed)
            self.assertEqual(store.objects, original)
            loaded, _ = load("fixture", "eu-west-1", "fixture-bucket", manifest["snapshot_id"], directory / "loaded")
            self.assertEqual(loaded, manifest)


if __name__ == "__main__":
    unittest.main()
