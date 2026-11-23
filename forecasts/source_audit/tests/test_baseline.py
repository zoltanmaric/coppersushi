"""Optional regression against the fixed historical input snapshot, not new data."""
from collections import defaultdict
from datetime import date
import json
import os
from pathlib import Path
import unittest

from forecasts.inputs.input_config import WEATHER_FIELDS
from forecasts.inputs.snapshot import read_local
from forecasts.source_audit.dataset import replay_snapshot, summarize


class BaselineCoverageTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("FORECAST_BASELINE_SNAPSHOT"),
                         "Set FORECAST_BASELINE_SNAPSHOT to the recorded snapshot directory")
    def test_recorded_snapshot_retains_its_audited_coverage(self) -> None:
        expected = json.loads((Path(__file__).parent / "fixtures/baseline-coverage.json").read_text())
        manifest, tables = read_local(Path(os.environ["FORECAST_BASELINE_SNAPSHOT"]))
        self.assertEqual(manifest["snapshot_id"], expected["snapshot_id"])
        rows = replay_snapshot(tables, date(2025, 10, 1), date(2026, 10, 1))
        self.assertEqual(summarize(rows, WEATHER_FIELDS), expected["counts"])
        daily: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in rows:
            daily[row["delivery_date"]][0] += 1
            daily[row["delivery_date"]][1] += row["demand_available"]
        self.assertEqual(dict(daily), expected["daily_demand"])
