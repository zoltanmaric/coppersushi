"""Synthetic boundary cases; no network or downloaded payloads required."""
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from forecasts.dataset import (
    build_rows, cutoff, holidays, load_demand, load_weather, PriceHistory, quarters,
    select_demand, stamp,
)

FIXTURES = Path(__file__).parent / "fixtures"


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.prices = {stamp(t): p for t, p in json.loads((FIXTURES / "prices.json").read_text()).items()}

    def archive(self, directory, fixture, name):
        path = Path(directory) / "fixture.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.write(FIXTURES / fixture, name)
        return path

    def test_issue_cutoff_uses_preceding_days_offset(self):
        expected = {"2026-03-29": "2026-03-28T10:00:00+00:00", "2026-03-30": "2026-03-29T09:00:00+00:00",
                    "2025-10-26": "2025-10-25T09:00:00+00:00", "2025-10-27": "2025-10-26T10:00:00+00:00"}
        for day, value in expected.items():
            self.assertEqual(cutoff(date.fromisoformat(day)).isoformat(), value)

    def test_clock_change_days_retain_all_utc_quarters(self):
        for day, count in [(date(2025, 10, 26), 100), (date(2026, 3, 29), 92)]:
            times = list(quarters(day, day + timedelta(days=1)))
            self.assertEqual(len(times), count)
            self.assertEqual(len(set(times)), count)
            self.assertTrue(all(b - a == timedelta(minutes=15) for a, b in zip(times, times[1:])))

    def test_price_lags_average_repeated_and_leave_nonexistent_quarters(self):
        history = PriceHistory(self.prices)
        self.assertEqual(history.lag(date(2025, 10, 27), 8, 1), 10)
        self.assertIsNone(history.lag(date(2026, 3, 30), 8, 1))
        self.assertEqual(history.lag(date(2026, 3, 30), 12, 1), 50)

    def test_demand_latest_usable_version_and_exact_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.archive(directory, "demand.csv", "2026_03_DayAheadTotalLoadForecast_6.1.B_r3.csv")
            demand = load_demand(path, date(2026, 3, 29), date(2026, 3, 30))
        self.assertEqual(len(demand[stamp("2026-03-29T00:00:00Z")]), 3)
        value, updated, reason = select_demand(demand[stamp("2026-03-29T00:00:00Z")], cutoff(date(2026, 3, 29)))
        self.assertEqual((value, updated, reason), (1100, "2026-03-28T10:00:00+00:00", "usable"))
        self.assertIsNone(select_demand(demand[stamp("2026-03-29T00:15:00Z")], cutoff(date(2026, 3, 29)))[0])
        self.assertEqual(select_demand([], cutoff(date(2026, 3, 29)))[2], "absent")

    def test_weather_shift_repeat_gaps_and_ending_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.archive(directory, "history.json", "history.json")
            weather, metadata = load_weather(path, [["Hamburg", 53.55, 9.99]])
        rows = build_rows(self.prices, weather, {}, date(2026, 3, 29), date(2026, 3, 30))
        first_hour = [r for r in rows if r["delivery_utc"].startswith("2026-03-29T00:")]
        self.assertEqual(len(first_hour), 4)
        self.assertTrue(all(r["shortwave_radiation_hamburg"] == 100 for r in first_hour))
        self.assertTrue(all(r["temperature_2m_hamburg"] == 8 for r in first_hour))
        next_hour = next(r for r in rows if r["delivery_utc"] == "2026-03-29T01:00:00+00:00")
        self.assertEqual(next_hour["shortwave_radiation_hamburg"], 200)
        self.assertEqual(next_hour["wind_speed_120m_hamburg_missing"], 1)
        self.assertEqual(next_hour["weather_source_unavailable"], 0)
        self.assertEqual(metadata["retrieved_at_utc"], "2026-04-01T12:00:00+00:00")

    def test_missing_sources_and_targets_do_not_drop_rows(self):
        rows = build_rows(self.prices, {"wind_speed_120m_hamburg": {}}, {}, date(2026, 3, 29), date(2026, 3, 30))
        self.assertEqual(len(rows), 92)
        self.assertEqual(sum(r["target_missing"] for r in rows), 90)
        self.assertTrue(all(r["demand_source_unavailable"] and r["weather_source_unavailable"] for r in rows))
        self.assertEqual(next(r["price_eur_mwh"] for r in rows if r["delivery_utc"] == "2026-03-29T00:00:00+00:00"), -25)

    def test_later_labels_do_not_change_features(self):
        day = date(2026, 3, 29)
        before = build_rows(self.prices, {}, {}, day, day + timedelta(days=1))
        later_prices = {t: (100000 if t >= stamp("2026-03-29T00:00:00Z") else p) for t, p in self.prices.items()}
        after = build_rows(later_prices, {}, {}, day, day + timedelta(days=1))
        features = [key for key in before[0] if key.startswith(("price_lag_", "price_day_"))]
        self.assertEqual([[r[k] for k in features] for r in before], [[r[k] for k in features] for r in after])

    def test_nationwide_holidays(self):
        days = holidays(2026)
        for day in ["2026-04-03", "2026-04-06", "2026-05-14", "2026-05-25", "2026-10-03"]:
            self.assertIn(date.fromisoformat(day), days)
        self.assertNotIn(date(2026, 1, 6), days)
        self.assertEqual(len(days), 9)


if __name__ == "__main__":
    unittest.main()
