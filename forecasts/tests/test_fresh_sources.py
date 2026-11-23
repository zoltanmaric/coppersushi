"""Historical refresh must cover real Berlin quarters with every input source."""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from forecasts.dataset import FIELDS, cutoff, quarters, select_demand
from forecasts.fresh_sources import fetch_sources, require_coverage
from forecasts.input_config import WEATHER_LOCATIONS
from forecasts.input_types import DemandSeries, PriceSeries, WeatherSeries


class FreshSourceTests(unittest.TestCase):
    def test_demands_actual_versions_for_all_100_clock_change_quarters(self) -> None:
        start, end = date(2026, 10, 25), date(2026, 10, 26)
        times = list(quarters(start, end))
        prices: PriceSeries = {t: 5.0 for t in times}
        weather: WeatherSeries = {f"{field}_{loc.name.lower()}": {t: 10.0 for t in times if t.minute == 0}
                                  for loc in WEATHER_LOCATIONS for field in FIELDS}
        # A real later archive revision is retained, but remains ineligible for the earlier replay.
        demand: DemandSeries = {t: [{"updated": cutoff(start) + timedelta(minutes=1), "value": 1000.0,
                                      "source": "monthly archive"}] for t in times}
        require_coverage(start, end, prices, weather, demand)
        self.assertEqual(len(demand), 100)
        self.assertIsNone(select_demand(demand[times[-1]], cutoff(start))[0])
        demand.pop(times[-1])
        with self.assertRaisesRegex(ValueError, "1 Germany demand quarters, 0 price quarters"):
            require_coverage(start, end, prices, weather, demand)

    def test_cannot_continue_after_file_library_download_failure(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            token = root / "token"
            token.write_text("bearer file fixture")
            with patch("forecasts.fresh_sources.access_token", return_value="test-token"), \
                    patch("forecasts.fresh_sources._fetch", side_effect=RuntimeError("File Library denied")), \
                    patch("forecasts.fresh_sources._fetch_prices") as prices, \
                    patch("forecasts.fresh_sources._fetch_weather") as weather:
                with self.assertRaisesRegex(RuntimeError, "File Library denied"):
                    fetch_sources(root / "raw", date(2026, 10, 1), date(2026, 10, 2), token)
                prices.assert_not_called()
                weather.assert_not_called()
