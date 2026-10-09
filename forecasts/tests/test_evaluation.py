"""Scores, operational fallbacks and the complete selection/fit boundary."""
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pyarrow as pa
import scoringrules

from forecasts.dataset import BERLIN, COUNTRY, cutoff, quarters, stamp
from forecasts.evaluation import FEATURES, fit_models, fit_reference, matrix, predict_day, training_rows
from forecasts.schemas import SCHEMAS, validate
from forecasts.scoring import metrics, paired_blocks, wis
from forecasts.snapshot import InputReader, LOCATIONS, select_records

ROOT = Path(__file__).resolve().parents[2]


def config():
    c = json.loads((ROOT / 'forecasts/run-config.json').read_text())
    c.update(features=FEATURES, history_start='2026-03-01', train_start='2026-03-15', reference_min_errors=96,
             reference_min_per_quarter=7)
    c['catboost'].update(iterations=8, depth=2)
    return c


def history():
    records = {n: [] for n in SCHEMAS}
    for i, t in enumerate(quarters(date(2026, 3, 1), date(2026, 3, 29))):
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


def reader(records):
    return InputReader({n: validate(n, pa.Table.from_pylist(v, schema=SCHEMAS[n])) for n, v in records.items()})


class EvaluationTests(unittest.TestCase):
    def test_wis_known_cases_and_independent_reference(self):
        q = np.array([[-2., -1., 0., 1., 2.]] * 4)
        y = np.array([0., 3., -3., 1.])
        np.testing.assert_allclose(wis(y, q), [.24, 2.04, 2.04, .44])
        intervals = scoringrules.interval_score(y, q[:, [1, 0]], q[:, [3, 4]],
                                                np.array([.5, .05]), backend='numpy')
        reference = (.5 * abs(y - q[:, 2]) + intervals @ np.array([.25, .025])) / 2.5
        np.testing.assert_allclose(wis(y, q), reference)

    def test_metrics_equal_day_weighting_retains_clock_change_counts(self):
        y = np.zeros(196)
        q = np.array([[-1, -1, 0, 1, 1]] * 196)
        y[:100] = 2
        result = metrics(y, q, ['2025-10-26'] * 100 + ['2025-10-27'] * 96)
        self.assertAlmostEqual(result['coverage_95'], 96 / 196)
        self.assertEqual(result['daily_coverage_95'], .5)
        self.assertEqual(result['rows'], 196)

    def test_block_comparison_reproducible_and_does_not_bridge_gaps(self):
        days = [f'2026-01-{d:02}' for d in list(range(1, 8)) + list(range(20, 27))]
        y = np.zeros(14)
        ref = np.zeros((14, 5))
        pred = np.ones((14, 5))
        settings = dict(seed=3, samples=100, block_days=7)
        a = paired_blocks(y, dict(reference=ref, model=pred), days, settings)
        self.assertEqual(a, paired_blocks(y, dict(reference=ref, model=pred), days, settings))
        self.assertEqual(a['model']['ci_95'], [1., 1.])
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            paired_blocks(y[:2], dict(reference=ref[:2]), days[:2], settings)

    def test_late_candidates_do_not_change_selection_fitting_calibration_or_predictions(self):
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
                features = [row for d in range(28) for row in r.features(date(2026, 3, 1) + timedelta(days=d))]
                train, y = training_rows(r, features, fit_day, date(2026, 3, 15))
                reference = fit_reference(r, train, y, fit_day, c)
                models, failures = fit_models(train, y, c, Path(temporary) / str(i))
                self.assertFalse(failures)
                outcomes.append((matrix(train, FEATURES['demand']), y, reference,
                                 predict_day(r.features(fit_day), models, reference, c)))
        np.testing.assert_allclose(outcomes[0][0], outcomes[1][0], equal_nan=True)
        np.testing.assert_array_equal(outcomes[0][1], outcomes[1][1])
        self.assertEqual(outcomes[0][2], outcomes[1][2])
        for name in outcomes[0][3][1]:
            np.testing.assert_allclose(outcomes[0][3][1][name], outcomes[1][3][1][name],
                                       atol=c['tolerance']['absolute'], rtol=c['tolerance']['relative'])

    def test_missing_sources_and_prediction_failure_choose_explicit_fallback(self):
        c = config()
        r = reader(history())
        rows = r.features(date(2026, 3, 29))
        class Model:
            def predict(self, x):
                return np.tile([2., -2., 0., -1., 1.], (len(x), 1))
        reference = dict(medians={q: -5. for q in range(96)}, offsets=[-2, -1, 0, 1, 2])
        models = {n: Model() for n in FEATURES}
        raw, predicted, failed, crossing, chosen, reason = predict_day(rows, models, reference, c)
        self.assertEqual(chosen, 'demand')
        self.assertTrue((np.diff(predicted['demand'], axis=1) >= 0).all())
        self.assertEqual(crossing['demand'], 92)
        for row in rows:
            row['demand_source_unavailable'] = 1
        self.assertEqual(predict_day(rows, models, reference, c)[4], 'weather')
        for row in rows:
            row['weather_source_unavailable'] = 1
        self.assertEqual(predict_day(rows, models, reference, c)[4], 'prices')
        for row in rows:
            row['weather_source_unavailable'] = 0
            row['demand_source_unavailable'] = 0
            row['price_lags_unavailable'] = 1
        self.assertEqual(predict_day(rows, models, reference, c)[4], 'reference')
        for row in rows:
            row['price_lags_unavailable'] = 0
        result = predict_day(rows, {}, reference, c)
        self.assertEqual(result[4], 'reference')
        self.assertIn('prediction_failure', result[5])
        self.assertTrue(np.isfinite(result[1]['system']).all())
        self.assertTrue((result[1]['system'] < 0).any())


if __name__ == '__main__':
    unittest.main()
