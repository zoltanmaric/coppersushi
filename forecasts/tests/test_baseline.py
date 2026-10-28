"""Optional regression against the fixed historical input snapshot, not new data."""
from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
import unittest

from forecasts.dataset import summarize
from forecasts.snapshot import InputReader, read_local


class BaselineCoverageTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("FORECAST_BASELINE_SNAPSHOT"),
                         "Set FORECAST_BASELINE_SNAPSHOT to the recorded snapshot directory")
    def test_recorded_snapshot_retains_its_audited_coverage(self) -> None:
        expected = json.loads((Path(__file__).parent / "fixtures/baseline-coverage.json").read_text())
        manifest, tables = read_local(Path(os.environ["FORECAST_BASELINE_SNAPSHOT"]))
        self.assertEqual(manifest["snapshot_id"], expected["snapshot_id"])
        reader = InputReader(tables)
        rows = reader.replay(date(2025, 10, 1), date(2026, 10, 1))
        self.assertEqual(summarize(rows, reader.weather_fields), expected["counts"])
        daily: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in rows:
            daily[row["delivery_date"]][0] += 1
            daily[row["delivery_date"]][1] += row["demand_available"]
        self.assertEqual(dict(daily), expected["daily_demand"])
