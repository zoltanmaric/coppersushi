"""Price lags, summaries and calendar fields on the Berlin delivery grid."""
from collections.abc import Mapping
from datetime import date, datetime
import unittest

import polars as pl
import pyarrow as pa
from polars.testing import assert_frame_equal
from forecasts.inputs.schemas import SCHEMAS, validate
from forecasts.inputs.selection import InputReader, select_records
from forecasts.inputs.tests.test_snapshot import history
from forecasts.model.features import build_day_features
from pandera.typing.polars import DataFrame

from forecasts.inputs.prices import PriceHistory
from forecasts.inputs.sources import stamp
from forecasts.model.calendar import holidays
from forecasts.model.price_features import build_price_features


def price_history(values: Mapping[datetime, float | None]) -> DataFrame[PriceHistory]:
    """Build a validated selected-value table for synthetic feature tests."""
    return PriceHistory.validate(pl.DataFrame(
        {"valid_utc": list(values), "price_eur_mwh": list(values.values())},
        schema={"valid_utc": pl.Datetime("us", "UTC"), "price_eur_mwh": pl.Float64}))


class PriceFeatureTests(unittest.TestCase):
    def test_empty_history_preserves_delivery_rows_with_missing_features(self) -> None:
        delivery = [stamp("2026-03-29T00:00:00Z"), stamp("2026-03-29T01:00:00Z")]
        result = build_price_features(price_history({}), delivery)
        self.assertEqual(result["delivery_utc"].to_list(), delivery)
        self.assertTrue(all(result[name].null_count() == 2 for name in result.columns[1:]))
        self.assertEqual(build_price_features(price_history({}), []).height, 0)

    def test_autumn_daily_summary_counts_both_physical_quarters(self) -> None:
        prices = {stamp("2025-10-26T00:00:00Z"): 0.0, stamp("2025-10-26T01:00:00Z"): 20.0,
                  stamp("2025-10-26T02:00:00Z"): 40.0}
        result = build_price_features(price_history(prices), [stamp("2025-10-27T01:00:00Z")]).row(0, named=True)
        self.assertEqual(result["price_lag_1"], 10.0)
        self.assertEqual(result["price_day_1_mean"], 20.0)
        self.assertEqual(result["price_day_1_min"], 0.0)
        self.assertEqual(result["price_day_1_max"], 40.0)

    def test_spring_lag_leaves_nonexistent_quarters_empty(self) -> None:
        delivery = [stamp("2026-03-30T00:00:00Z"), stamp("2026-03-30T01:00:00Z")]
        prices = {stamp("2026-03-29T01:00:00Z"): 50.0}
        values = build_price_features(price_history(prices), delivery)["price_lag_1"].to_list()
        self.assertEqual(values, [None, 50])


class CalendarTests(unittest.TestCase):
    def test_nationwide_holidays(self) -> None:
        days = holidays(2026)
        for day in ["2026-04-03", "2026-04-06", "2026-05-14", "2026-05-25", "2026-10-03"]:
            self.assertIn(date.fromisoformat(day), days)
        self.assertNotIn(date(2026, 1, 6), days)
        self.assertEqual(len(days), 9)


class FeatureSelectionTests(unittest.TestCase):
    def test_post_cutoff_history_does_not_change_selected_versions_or_features(self) -> None:
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
        assert_frame_equal(build_day_features(InputReader(original_tables), day),
                           build_day_features(InputReader(enlarged_tables), day))

    def test_rejected_new_weather_location_does_not_expand_feature_inventory(self) -> None:
        records = history()
        original = {n: records[n] for n in SCHEMAS}
        extra = dict(records["append"]["weather"][0], location="unconfigured-location")
        enlarged = {n: records[n] + ([extra] if n == "weather" else []) for n in SCHEMAS}
        before = InputReader({n: pa.Table.from_pylist(original[n], schema=SCHEMAS[n]) for n in SCHEMAS})
        after = InputReader({n: pa.Table.from_pylist(enlarged[n], schema=SCHEMAS[n]) for n in SCHEMAS})
        assert_frame_equal(build_day_features(before, date(2026, 3, 29)),
                           build_day_features(after, date(2026, 3, 29)))
