"""Price refresh requires every quarter of the requested Berlin delivery days."""
from datetime import date
import unittest

from forecasts.dataset import quarters
from forecasts.fresh_sources import require_coverage


class FreshSourceTests(unittest.TestCase):
    def test_requires_all_100_clock_change_quarters(self) -> None:
        start, end = date(2026, 10, 25), date(2026, 10, 26)
        prices = dict.fromkeys(quarters(start, end), 5.0)
        self.assertEqual(len(prices), 100)
        require_coverage(start, end, prices)
        prices.pop(max(prices))
        with self.assertRaisesRegex(ValueError, "Missing 1 price quarters"):
            require_coverage(start, end, prices)
