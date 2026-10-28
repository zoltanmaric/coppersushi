"""Price contracts and revision ambiguity at the table boundary."""
from datetime import date
import unittest

import polars as pl
import pyarrow as arrow
from pandera.errors import SchemaError

from forecasts.dataset import cutoff, stamp
from forecasts.prices import PriceVersions, build_price_features, read_prices, select_history, snapshot_schema
from forecasts.tests.test_snapshot import history


class PriceTableTests(unittest.TestCase):
    def test_values_nullability_timezone_and_keys(self) -> None:
        base = read_prices(arrow.Table.from_pylist(history()["prices"], schema=snapshot_schema()))
        for value in [-100.0, None]:
            PriceVersions.validate(base.with_columns(pl.lit(value, dtype=pl.Float64).alias("price_eur_mwh")))
        for value in [float("nan"), float("inf"), float("-inf")]:
            with self.subTest(value=value), self.assertRaises(SchemaError):
                PriceVersions.validate(base.with_columns(pl.lit(value).alias("price_eur_mwh")))
        with self.assertRaises(SchemaError):
            PriceVersions.validate(base.with_columns(pl.col("valid_utc").dt.replace_time_zone(None)))
        with self.assertRaises(SchemaError):
            PriceVersions.validate(pl.concat([base, base]))

    def test_revision_selection_keeps_exact_cutoff_and_rejects_conflicting_ties(self) -> None:
        day = date(2026, 3, 29)
        base = history()["prices"][0]
        rows = [dict(base, version_id="old", price_eur_mwh=-20.0),
                dict(base, version_id="exact", source_update_utc=cutoff(day), price_eur_mwh=10.0),
                dict(base, version_id="late", source_update_utc=stamp("2026-03-28T10:00:01Z"), price_eur_mwh=999.0)]
        frame = read_prices(arrow.Table.from_pylist(rows, schema=snapshot_schema()))
        self.assertEqual(select_history(frame, day, cutoff(day))["version_id"].to_list(), ["exact"])
        conflict = dict(rows[1], version_id="conflict", price_eur_mwh=None)
        frame = read_prices(arrow.Table.from_pylist(rows+[conflict], schema=snapshot_schema()))
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            select_history(frame, day, cutoff(day))

    def test_empty_history_preserves_delivery_rows_with_missing_features(self) -> None:
        delivery = [stamp("2026-03-29T00:00:00Z"), stamp("2026-03-29T01:00:00Z")]
        result = build_price_features({}, delivery)
        self.assertEqual(result["delivery_utc"].to_list(), delivery)
        self.assertTrue(all(result[name].null_count() == 2 for name in result.columns[1:]))
        self.assertEqual(build_price_features({}, []).height, 0)

    def test_autumn_daily_summary_counts_both_physical_quarters(self) -> None:
        prices = {stamp("2025-10-26T00:00:00Z"): 0.0, stamp("2025-10-26T01:00:00Z"): 20.0,
                  stamp("2025-10-26T02:00:00Z"): 40.0}
        result = build_price_features(prices, [stamp("2025-10-27T01:00:00Z")]).row(0, named=True)
        self.assertEqual(result["price_lag_1"], 10.0)
        self.assertEqual(result["price_day_1_mean"], 20.0)
        self.assertEqual(result["price_day_1_min"], 0.0)
        self.assertEqual(result["price_day_1_max"], 40.0)
