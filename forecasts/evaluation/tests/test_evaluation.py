"""Scores and the complete selection, fit and prediction boundaries."""
from forecasts.evaluation.contracts import BacktestPredictions, Predictions, ScoredPredictions
from forecasts.model.contracts import FloatArray, Reference
from forecasts.inputs.input_types import Row
from forecasts.model.tables import Features
from pandera.errors import SchemaError
import polars as pl
from datetime import date, timedelta
from dataclasses import replace

from forecasts.config import BootstrapSettings, FEATURES, RunConfig
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import scoringrules

from forecasts.inputs.sources import COUNTRY, stamp
from forecasts.market import cutoff, quarters
from forecasts.evaluation.workflow import evaluate
from forecasts.model.features import build_day_features, build_features, feature_matrix
from forecasts.model.prediction import predict_day
from forecasts.model.training import fit_month, select_training_data
from forecasts.inputs.schemas import SCHEMAS, validate
from forecasts.evaluation.scoring import metrics, paired_blocks, score_forecasts, wis
from forecasts.inputs.selection import InputReader, LOCATIONS, select_records

ROOT = Path(__file__).resolve().parents[3]


def config() -> RunConfig:
    c = json.loads((ROOT / 'forecasts/run-config.json').read_text())
    c.update(features=FEATURES, history_start='2026-03-01', train_start='2026-03-15', reference_min_errors=96,
             reference_min_per_quarter=7, evaluation_start='2026-04-01', end_exclusive='2026-05-01')
    c['catboost'].update(iterations=8, depth=2)
    return RunConfig.from_dict(c)


def history(start: date = date(2026, 3, 1), end: date = date(2026, 3, 29)) -> dict[str, list[Row]]:
    records: dict[str, list[Row]] = {n: [] for n in SCHEMAS}
    for i, t in enumerate(quarters(start, end)):
        records['prices'].append(dict(valid_utc=t, source_update_utc=None, retrieved_at_utc=None, timing_evidence='assumed',
                                      version_id=f'price-{i}', raw_key='invented', price_eur_mwh=float(i % 96 - 30 + i // 96)))
    t = stamp('2026-03-29T00:00:00Z')
    common = dict(valid_utc=t, source_update_utc=cutoff(date(2026, 3, 29)) - timedelta(hours=1),
                  retrieved_at_utc=cutoff(date(2026, 3, 29)) - timedelta(minutes=30),
                  timing_evidence='witnessed', version_id='available-future', raw_key='invented')
    records['weather'].append(dict(common, source_valid_utc=t, location=sorted(LOCATIONS)[0], variable='temperature_2m',
                                   value=12., unit='°C', model='icon_eu', lead_hours=48, data_kind='forecast'))
    records['demand'].append(dict(common, area_code=COUNTRY, demand_mw=50000.))
    return records


def reader(records: dict[str, list[Row]]) -> InputReader:
    return InputReader({n: validate(n, pa.Table.from_pylist(v, schema=SCHEMAS[n])) for n, v in records.items()})


class EvaluationTests(unittest.TestCase):
    def test_feature_contract_preserves_clocks_and_rejects_leaked_outcomes(self) -> None:
        table = build_day_features(reader(history()), date(2026, 3, 29))
        self.assertEqual(table.height, 92)
        self.assertEqual(table.schema['delivery_date'], pl.Date)
        self.assertEqual(table.schema['delivery_utc'], pl.Datetime('us', 'UTC'))
        self.assertNotIn('price_eur_mwh', table.columns)
        self.assertNotIn('target_missing', table.columns)
        # Inputs cannot silently become labels or carry a contradictory clock.
        with self.assertRaises(SchemaError):
            Features.validate(table.with_columns(pl.lit(42.).alias('price_eur_mwh')))
        with self.assertRaises(SchemaError):
            Features.validate(table.with_columns(pl.lit(date(2026, 3, 30)).alias('delivery_date')))
        with self.assertRaises(SchemaError):
            Features.validate(table.drop('price_lag_1_missing'))

    def test_wis_known_cases_and_independent_reference(self) -> None:
        q = np.array([[-2., -1., 0., 1., 2.]] * 4)
        y = np.array([0., 3., -3., 1.])
        np.testing.assert_allclose(wis(y, q), [.24, 2.04, 2.04, .44])
        intervals = scoringrules.interval_score(y, q[:, [1, 0]], q[:, [3, 4]],
                                                np.array([.5, .05]), backend='numpy')
        reference = (.5 * abs(y - q[:, 2]) + intervals @ np.array([.25, .025])) / 2.5
        np.testing.assert_allclose(wis(y, q), reference)

    def test_metrics_equal_day_weighting_retains_clock_change_counts(self) -> None:
        y = np.zeros(196)
        q = np.array([[-1, -1, 0, 1, 1]] * 196)
        y[:100] = 2
        result = metrics(y, q, [date(2025, 10, 26)] * 100 + [date(2025, 10, 27)] * 96)
        self.assertAlmostEqual(result['coverage_95'], 96 / 196)
        self.assertEqual(result['daily_coverage_95'], .5)
        self.assertEqual(result['rows'], 196)

    def test_block_comparison_reproducible_and_does_not_bridge_gaps(self) -> None:
        days = [date(2026, 1, d) for d in list(range(1, 8)) + list(range(20, 27))]
        y = np.zeros(14)
        ref = np.zeros((14, 5))
        pred = np.ones((14, 5))
        settings = BootstrapSettings(seed=3, samples=100, block_days=7)
        a = paired_blocks(y, dict(reference=ref, model=pred), days, settings)
        self.assertEqual(a, paired_blocks(y, dict(reference=ref, model=pred), days, settings))
        self.assertEqual(a['model']['ci_95'], [1., 1.])
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            paired_blocks(y[:2], dict(reference=ref[:2]), days[:2], settings)

    def test_late_candidates_do_not_change_selection_fitting_calibration_or_predictions(self) -> None:
        c, before = config(), history()
        fit_day = date(2026, 3, 29)
        after = {n: list(v) for n, v in before.items()}
        late = cutoff(fit_day) + timedelta(hours=1)
        after['prices'].append(dict(before['prices'][1500], source_update_utc=late, version_id='late-revision', price_eur_mwh=99999.))
        after['prices'].append(dict(before['prices'][0], valid_utc=stamp('2026-03-29T00:00:00Z'),
                                    source_update_utc=late, version_id='new-label', price_eur_mwh=99999.))
        after['weather'].append(dict(before['weather'][0], source_update_utc=late, version_id='late-forecast', value=999.))
        after['weather'].append(dict(before['weather'][0], version_id='realised', data_kind='realised', value=999.))
        after['demand'].append(dict(before['demand'][0], source_update_utc=late, version_id='late-demand', demand_mw=999999.))
        self.assertEqual(select_records(before, fit_day), select_records(after, fit_day))
        self.assertEqual(select_records(after, fit_day)['weather'][0]['version_id'], 'available-future')
        outcomes = []
        with tempfile.TemporaryDirectory() as temporary:
            for i, records in enumerate([before, after]):
                r = reader(records)
                features = build_features(r, c.history_start, fit_day, complete_from=c.train_start)
                training = select_training_data(r, features, fit_day, date(2026, 3, 15))
                fitted = fit_month(r, features, fit_day, c, Path(temporary) / str(i))
                self.assertFalse(fitted.failures)
                outcomes.append((feature_matrix(training.rows, FEATURES['prices']), training.targets, fitted.reference,
                                 predict_day(build_day_features(r, fit_day, require_complete=True), fitted.models, fitted.reference, c)))
        np.testing.assert_allclose(outcomes[0][0], outcomes[1][0], equal_nan=True)
        np.testing.assert_array_equal(outcomes[0][1], outcomes[1][1])
        self.assertEqual(outcomes[0][2], outcomes[1][2])
        for name in outcomes[0][3].ordered:
            np.testing.assert_allclose(outcomes[0][3].ordered[name], outcomes[1][3].ordered[name],
                                       atol=c.tolerance.absolute, rtol=c.tolerance.relative)

    def test_saved_models_reproduce_monthly_predictions_and_scoring_truth_flags(self) -> None:
        c = config()
        c = replace(c, history_start=date(2026, 1, 1), train_start=date(2026, 1, 15),
                    evaluation_start=date(2026, 3, 1), end_exclusive=date(2026, 4, 1),
                    bootstrap=replace(c.bootstrap, samples=10))
        records = history(c.history_start, c.end_exclusive)
        r = reader({"prices": records["prices"]})
        with tempfile.TemporaryDirectory() as temporary:
            original, restored = Path(temporary) / 'original', Path(temporary) / 'restored'
            report = evaluate(r, c, original)
            replay = evaluate(r, c, restored, restore_models=original / 'models')
            self.assertEqual(report, replay)
            self.assertEqual(set(report["metrics"]), {"prices", "reference"})
            self.assertEqual(set(report["comparison"]), {"prices"})
            self.assertEqual(report["fallback_rows"], {})
            self.assertEqual({path.name for path in (original / "models").rglob("*.cbm")}, {"prices.cbm"})
            before = pq.read_table(original / 'predictions.parquet').to_pydict()
            self.assertEqual(before, pq.read_table(restored / 'predictions.parquet').to_pydict())
            self.assertEqual(len(before['target']), 2972)
            self.assertTrue(all(v is not None for v in before['target']))
            self.assertEqual(set(before['target_missing']), {0})
            self.assertEqual(report['missing_truth'], 0)
            scored = pl.read_parquet(original / 'predictions.parquet')
            ScoredPredictions.validate(scored)
            rows = Predictions.validate(scored.drop("target", "target_missing"))
            backtest = BacktestPredictions(rows, [], [], {})
            incomplete_truth = dict(r.realized_prices())
            incomplete_truth.pop(rows["delivery_utc"][-1])
            with self.assertRaisesRegex(ValueError, "Realised SMARD prices.*1 missing quarter"):
                score_forecasts(backtest, incomplete_truth, c)
            fallback = Predictions.validate(rows.with_columns(pl.lit("reference").alias("selected_model")))
            with self.assertRaisesRegex(ValueError, "rejects a fallback on 2026-03-01"):
                score_forecasts(replace(backtest, rows=fallback), r.realized_prices(), c)
            missing_input = Predictions.validate(rows.with_columns(
                pl.when(pl.int_range(0, pl.len()) == 0).then(1).otherwise(pl.col("price_lag_1_missing"))
                .alias("price_lag_1_missing")
            ))
            with self.assertRaisesRegex(ValueError, "missing input price_lag_1 on 2026-03-01"):
                score_forecasts(replace(backtest, rows=missing_input), r.realized_prices(), c)
            with self.assertRaises(SchemaError):
                ScoredPredictions.validate(scored.with_columns(pl.lit(1).cast(pl.Int64).alias('target_missing')))
            with self.assertRaises(SchemaError):
                ScoredPredictions.validate(scored.with_columns(pl.lit(float('inf')).alias('prices_q0.5')))
            with self.assertRaises(SchemaError):
                ScoredPredictions.validate(scored.with_columns((pl.col('prices_q0.975') + 1).alias('prices_q0.025')))

    def test_prediction_requires_complete_prices_and_the_selected_model(self) -> None:
        c = config()
        day = date(2026, 3, 29)
        records = history()
        rows = build_day_features(reader(records), day, require_complete=True)
        class Model:
            def predict(self, x: FloatArray) -> FloatArray:
                return np.tile([2., -2., 0., -1., 1.], (len(x), 1))
        reference: Reference = dict(medians={q: -5. for q in range(96)}, offsets=[-2, -1, 0, 1, 2],
                                    calibration_rows=96, excluded_rows=0)
        models = {name: Model() for name in FEATURES}
        forecast = predict_day(rows, models, reference, c)
        self.assertEqual(forecast.selected_model, "prices")
        self.assertEqual(forecast.crossings["prices"], 92)
        self.assertEqual(set(forecast.ordered), {"prices", "reference"})
        self.assertFalse(any(key.startswith(("weather_", "demand_")) for key in rows.columns))
        partial = Features.validate(rows.with_columns(
            pl.when(pl.int_range(0, pl.len()) == 1).then(None).otherwise(pl.col("price_lag_1")).alias("price_lag_1")
        ).with_columns(pl.col("price_lag_1").is_null().cast(pl.Int64).alias("price_lag_1_missing")))
        with self.assertRaisesRegex(ValueError, "SMARD prices.*2026-03-29"):
            predict_day(partial, models, reference, c)
        models.pop("prices")
        with self.assertRaisesRegex(ValueError, "prices prediction failed for 2026-03-29"):
            predict_day(rows, models, reference, c)

    def test_physical_price_gaps_fail_but_nonexistent_spring_lags_are_valid(self) -> None:
        day = date(2026, 3, 30)
        records = history(end=day)
        rows = build_day_features(reader(records), day, require_complete=True)
        self.assertEqual(rows["price_lag_1"].null_count(), 4)
        missing = stamp("2026-03-29T01:00:00Z")
        records["prices"] = [row for row in records["prices"] if row["valid_utc"] != missing]
        with self.assertRaisesRegex(ValueError, "Eligible prices.*2026-03-30.*1 missing quarter"):
            build_day_features(reader(records), day, require_complete=True)

    def test_training_failure_never_writes_a_fitted_model(self) -> None:
        c = config()
        day = date(2026, 3, 29)
        records = history()
        r = reader(records)
        features = build_features(r, c.history_start, day, complete_from=c.train_start)
        with tempfile.TemporaryDirectory() as temporary, patch("forecasts.model.training.CatBoostRegressor.fit",
                                                               side_effect=ValueError("failed training")):
            out = Path(temporary) / "models"
            with self.assertRaisesRegex(ValueError, "prices CatBoost fit failed for 2026-03-29"):
                fit_month(r, features, day, c, out)
            self.assertFalse(out.exists())
        with self.assertRaisesRegex(ValueError, "Eligible SMARD training labels.*1 missing quarter"):
            records["prices"].pop()
            select_training_data(reader(records), features, day, c.train_start)


if __name__ == '__main__':
    unittest.main()
