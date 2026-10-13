"""The presentation must preserve evidence, including awkward clock and truth cases."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from forecasts.explain import build_payload, digest, export, METHODS, QUANTILES, scores


class ExplainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / 'run'
        self.run.mkdir()
        self.rows = []
        for day in ('2026-03-29', '2026-10-25'):
            start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('Europe/Berlin'))
            stop = (start + timedelta(days=1)).astimezone(ZoneInfo('UTC'))
            current = start.astimezone(ZoneInfo('UTC'))
            while current < stop:
                row = {'delivery_utc': current.isoformat(), 'delivery_date': day,
                       'fold': day[:8] + '01', 'target': None if day.startswith('2026-10') else -5.,
                       'selected_model': 'weather', 'fallback_reason': 'demand:demand_source_unavailable',
                       'demand_selected_update_utc': None, 'demand_missing': 1}
                for name in METHODS:
                    row.update({f'{name}_q{q}': value for q, value in zip(QUANTILES, (-10., -6., -4., 0., 3.))})
                self.rows.append(row)
                current += timedelta(minutes=15)
        pq.write_table(pa.Table.from_pylist(self.rows), self.run / 'predictions.parquet')
        config = {'quantiles': list(QUANTILES), 'snapshot_id': 'test', 'train_start': '2025-10-15',
                  'evaluation_start': '2026-03-01', 'end_exclusive': '2026-11-01', 'catboost': {}, 'features': {'prices': ['lag']}}
        (self.run / 'config.json').write_text(json.dumps(config))
        report = {'metrics': scores(self.rows), 'comparison': {}, 'delivery_rows': 192, 'scored_rows': 92,
                  'missing_truth': 100, 'breakdowns': {'month': {}}, 'folds': [], 'timing_limits': {},
                  'limitations': [], 'raw_crossing_fraction': {}, 'prediction_failures': [], 'fallback_rows': {'weather':192}}
        for month in ('2026-03', '2026-10'):
            selected = [r for r in self.rows if r['delivery_date'].startswith(month)]
            report['breakdowns']['month'][month] = {'metrics': scores(selected)}
            report['folds'].append({'first_delivery_day': month + '-01'})
        (self.run / 'report.json').write_text(json.dumps(report))
        self.manifest = {'config': config, 'run_id': 'test', 'code_revision': 'test', 'exploratory': True,
                         'mlflow_run_id': 'test', 'metaflow_run_id': 'test'}
        self.sign()

    def sign(self):
        self.manifest['artifacts'] = {name: digest(self.run / name) for name in
                                     ('predictions.parquet', 'report.json', 'config.json')}
        (self.run / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_dst_missing_truth_and_negative_prices_survive(self):
        payload = build_payload(self.run)
        spring, autumn = payload['days']
        self.assertEqual([len(spring['points']), len(autumn['points'])], [92, 100])
        self.assertEqual(spring['points'][0]['actual'], -5)
        self.assertEqual(autumn['metrics']['system'], {'rows': 0})
        clocks = [p['clock'] for p in autumn['points']]
        self.assertIn('02:00 CEST', clocks)
        self.assertIn('02:00 CET', clocks)
        self.assertEqual(spring['issue'], '2026-03-28T11:00:00+01:00')
        self.assertEqual(autumn['issue'], '2026-10-24T11:00:00+02:00')
        self.assertEqual(spring['metrics']['system']['median_mae'], 1.)
        self.assertEqual(spring['metrics']['system']['coverage_95'], 1.)

    def test_corruption_and_inconsistent_report_fail_before_export(self):
        output = Path(self.tmp.name) / 'export'
        path = self.run / 'report.json'
        report = json.loads(path.read_text())
        report['metrics']['system']['wis'] += 1
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            export(self.run, output)
        self.assertFalse(output.exists())
        self.sign()
        with self.assertRaisesRegex(ValueError, 'Metric mismatch'):
            export(self.run, output)
        self.assertFalse(output.exists())

    def test_unscored_quantiles_still_require_validation(self):
        self.rows[-1]['system_q0.025'] = float('nan')
        pq.write_table(pa.Table.from_pylist(self.rows), self.run / 'predictions.parquet')
        self.sign()
        with self.assertRaisesRegex(ValueError, 'finite ordered'):
            build_payload(self.run)

    def test_changed_wiki_requires_narrative_review(self):
        import forecasts.explain as explain
        actual_digest = explain.digest
        def changed(path):
            return 'changed' if path.name == 'evaluation.md' else actual_digest(path)
        with patch.object(explain, 'digest', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'review narrative'):
                build_payload(self.run)
