"""Issue deadlines and physical delivery quarters across Berlin clock changes."""
from datetime import date, timedelta
import unittest

from forecasts.market import cutoff, quarters


class MarketTests(unittest.TestCase):
    def test_issue_cutoff_uses_preceding_days_offset(self) -> None:
        expected = {"2026-03-29": "2026-03-28T10:00:00+00:00", "2026-03-30": "2026-03-29T09:00:00+00:00",
                    "2025-10-26": "2025-10-25T09:00:00+00:00", "2025-10-27": "2025-10-26T10:00:00+00:00"}
        for day, value in expected.items():
            self.assertEqual(cutoff(date.fromisoformat(day)).isoformat(), value)

    def test_clock_change_days_retain_all_utc_quarters(self) -> None:
        for day, count in [(date(2025, 10, 26), 100), (date(2026, 3, 29), 92)]:
            times = list(quarters(day, day + timedelta(days=1)))
            self.assertEqual(len(times), count)
            self.assertEqual(len(set(times)), count)
            self.assertTrue(all(b - a == timedelta(minutes=15) for a, b in zip(times, times[1:])))
