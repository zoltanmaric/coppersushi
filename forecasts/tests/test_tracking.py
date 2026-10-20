"""Lifecycle checks use a real temporary store and tiny substitute computations."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from forecasts import run


class TrackingTests(unittest.TestCase):
    def test_success_failure_and_interrupt_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(run, 'ROOT', Path(tmp)):
            directory = Path(tmp) / 'execution'
            directory.mkdir()
            config = dict(snapshot_id='snapshot', train_start='2025-10-15',
                          evaluation_start='2026-01-01', end_exclusive='2026-02-01',
                          catboost={}, features={'prices': ['quarter']})
            (directory / 'config.json').write_text(json.dumps(config))
            (directory / 'manifest.json').write_text(json.dumps(dict(
                exploratory=True, code_revision='revision', run_id='fixture')))
            client = run.tracking_client()
            ids = []

            def compute(args, **kwargs):
                run_id = args[args.index('--mlflow-run') + 1]
                ids.append(run_id)
                parent = client.get_run(run_id)
                self.assertEqual(parent.info.status, 'RUNNING')
                self.assertLessEqual(parent.info.start_time, int(time.time() * 1000))
                (directory / 'result.json').write_text('{"ok": true}')
                run.track(directory, config, {'metrics': {'prices': {'wis': 2.0}}}, 'fixture/1', run_id)
                run.finish(directory, run_id, 'fixture/1')
                self.assertEqual(client.get_run(run_id).info.status, 'RUNNING')

            with patch.object(run.subprocess, 'run', side_effect=compute):
                run.run_flow(directory, Path(tmp))
            parent = client.get_run(ids[0])
            self.assertEqual(parent.info.status, 'FINISHED')
            self.assertIsNotNone(parent.info.end_time)
            children = client.search_runs([parent.info.experiment_id],
                filter_string=f"tags.`mlflow.parentRunId` = '{ids[0]}'")
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0].data.metrics['wis'], 2.0)
            self.assertEqual(children[0].data.tags['timing_semantics'], 'logging_only')
            self.assertIn('CatBoost', children[0].info.run_name)
            self.assertEqual(children[0].info.status, 'FINISHED')

            for error, status in [(subprocess.CalledProcessError(1, 'fixture'), 'FAILED'),
                                  (KeyboardInterrupt(), 'KILLED')]:
                def fail(args, **kwargs):
                    ids.append(args[args.index('--mlflow-run') + 1])
                    self.assertEqual(client.get_run(ids[-1]).info.status, 'RUNNING')
                    raise error
                with patch.object(run.subprocess, 'run', side_effect=fail):
                    with self.assertRaises(type(error)):
                        run.run_flow(directory, Path(tmp))
                failed = client.get_run(ids[-1])
                self.assertEqual(failed.info.status, status)
                self.assertEqual(failed.data.tags['failure_type'], type(error).__name__)
                self.assertEqual(client.search_runs([failed.info.experiment_id],
                    filter_string=f"tags.`mlflow.parentRunId` = '{ids[-1]}'"), [])
