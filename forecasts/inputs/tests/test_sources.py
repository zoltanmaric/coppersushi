"""Load and select country-demand versions from an archived provider extract."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from forecasts.inputs.selection import select_demand
from forecasts.inputs.sources import load_demand, stamp
from forecasts.market import cutoff

FIXTURES = Path(__file__).parent / "fixtures"


class SourceArchiveTests(unittest.TestCase):
    def test_demand_latest_usable_version_and_exact_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demand.zip"
            with ZipFile(path, "w") as archive:
                archive.write(FIXTURES / "demand.csv", "2026_03_DayAheadTotalLoadForecast_6.1.B_r3.csv")
            demand = load_demand(path, date(2026, 3, 29), date(2026, 3, 30))
        self.assertEqual(len(demand[stamp("2026-03-29T00:00:00Z")]), 3)
        value, updated, reason = select_demand(demand[stamp("2026-03-29T00:00:00Z")], cutoff(date(2026, 3, 29)))
        self.assertEqual((value, updated, reason), (1100, stamp("2026-03-28T10:00:00Z"), "usable"))
        self.assertIsNone(select_demand(demand[stamp("2026-03-29T00:15:00Z")], cutoff(date(2026, 3, 29)))[0])
        self.assertEqual(select_demand([], cutoff(date(2026, 3, 29)))[2], "absent")
