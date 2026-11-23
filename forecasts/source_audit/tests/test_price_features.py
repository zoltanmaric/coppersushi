"""Coverage diagnostic regressions for price lags and the local calendar."""
from collections.abc import Mapping
from datetime import date, datetime, timedelta
import unittest

from pandera.typing.polars import DataFrame
import polars as pl
import pyarrow as pa

from forecasts.inputs.prices import PriceHistory
from forecasts.inputs.schemas import SCHEMAS
from forecasts.inputs.selection import select_records
from forecasts.inputs.sources import stamp
from forecasts.inputs.tests.test_snapshot import history
from forecasts.source_audit.dataset import holidays, replay_snapshot
from forecasts.source_audit.price_features import build_price_features


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
    def test_post_cutoff_revisions_do_not_change_replayed_features(self) -> None:
        records = history()
        day = date(2026, 3, 29)
        original = {name: records[name] for name in SCHEMAS}
        enlarged = {name: records[name] + records["append"][name] for name in SCHEMAS}
        before = select_records(original, day)
        self.assertEqual(before, select_records(enlarged, day))
        self.assertEqual(before["weather"][0]["version_id"], "weather-before-future-valid")
        rows = []
        for source in (original, enlarged):
            tables = {name: pa.Table.from_pylist(source[name], schema=schema) for name, schema in SCHEMAS.items()}
            replayed = replay_snapshot(tables, day, day + timedelta(days=1))
            retrospective = {"price_eur_mwh", "target_missing", "demand_archive_versions", "demand_archived_latest_update_utc"}
            rows.append([{key: value for key, value in row.items() if key not in retrospective}
                         for row in replayed])
        self.assertEqual(rows[0], rows[1])

    def test_unknown_weather_location_does_not_enter_selection(self) -> None:
        records = history()
        day = date(2026, 3, 29)
        original = {name: records[name] for name in SCHEMAS}
        extra = dict(records["append"]["weather"][0], location="unconfigured-location")
        enlarged = {**original, "weather": [*original["weather"], extra]}
        self.assertEqual(select_records(original, day), select_records(enlarged, day))
