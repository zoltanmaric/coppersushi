"""Price refresh requires every quarter of the requested Berlin delivery days."""
from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest

from forecasts.market import quarters
from forecasts.inputs.snapshot import collect
from forecasts.inputs.sources import PAYLOADS
from forecasts.inputs.fresh_sources import require_coverage


class FreshSourceTests(unittest.TestCase):
    def test_requires_all_100_clock_change_quarters(self) -> None:
        start, end = date(2026, 10, 25), date(2026, 10, 26)
        prices = dict.fromkeys(quarters(start, end), 5.0)
        self.assertEqual(len(prices), 100)
        require_coverage(start, end, prices)
        prices.pop(max(prices))
        with self.assertRaisesRegex(ValueError, "Missing 1 price quarters"):
            require_coverage(start, end, prices)

    def test_daily_snapshot_checks_only_required_dates(self) -> None:
        day = date(2026, 11, 25)
        required = [date(2026, 11, d) for d in (11, 18, 23, 24)]
        series = [[int(t.timestamp() * 1000), 47.0] for d in required
                  for t in quarters(d, d + timedelta(days=1))]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / PAYLOADS["prices"]
            archive_path.parent.mkdir(parents=True)

            def save_source() -> None:
                with ZipFile(archive_path, "w") as archive:
                    archive.writestr("prices/week.json", json.dumps({"series": series}))
                    archive.writestr("retrieval.json", '{"retrieved_at_utc":"2026-11-24T09:00:00Z"}')

            save_source()
            manifest = collect(root, root / "issue", delivery_date=day)
            self.assertEqual(manifest["required_dates_berlin"], [d.isoformat() for d in required])
            with self.assertRaisesRegex(ValueError, "Missing"):
                collect(root, root / "training", period=(min(required), day))
            series.pop()
            save_source()
            with self.assertRaisesRegex(ValueError, "Missing 1 price quarters"):
                collect(root, root / "missing", delivery_date=day)
