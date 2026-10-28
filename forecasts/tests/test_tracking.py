"""Lifecycle checks use a real temporary store and tiny substitute computations."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from forecasts import run
from forecasts.config import RunConfig

CONFIG_PATH = Path(__file__).resolve().parents[1] / "run-config.json"


class TrackingTests(unittest.TestCase):
    def test_success_failure_and_interrupt_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(run, 'DATA_ROOT', Path(tmp)):
            directory = Path(tmp) / 'execution'
            directory.mkdir()
            config = RunConfig.from_dict(json.loads(CONFIG_PATH.read_text()))
            (directory / 'config.json').write_text(json.dumps(config.to_dict()))
            (directory / 'manifest.json').write_text(json.dumps(dict(
                exploratory=True, code_revision='revision', run_id='fixture')))
            client = run.tracking_client()
            ids = []

            def compute(args: list[str], **kwargs: object) -> None:
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
                def fail(args: list[str], **kwargs: object) -> None:
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

    def test_unchanged_retry_preserves_failed_attempt(self) -> None:
        from mlflow import MlflowClient
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = MlflowClient(tracking_uri=f"sqlite:///{root / 'tracking.db'}")
            client.create_experiment('germany-luxembourg-local',
                                     artifact_location=(root / 'artifacts').as_uri())
            config_path = run.ROOT / 'forecasts/run-config.json'
            with patch.object(run, 'RUNS', root / 'runs'), patch.object(run, 'tracking_client', return_value=client):
                first, _ = run.prepare(config_path, exploratory=True)
                original = (first / 'manifest.json').read_bytes()
                with patch.object(run.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'fixture')):
                    with self.assertRaises(subprocess.CalledProcessError):
                        run.run_flow(first, root / 'snapshot')
                second, config = run.prepare(config_path, exploratory=True)
                def succeed(args: list[str], **kwargs: object) -> None:
                    attempt = args[args.index('--mlflow-run') + 1]
                    (second / 'result.json').write_text('{"ok": true}')
                    run.finish(second, attempt, 'retry/1')
                with patch.object(run.subprocess, 'run', side_effect=succeed):
                    run.run_flow(second, root / 'snapshot')
                self.assertNotEqual(first, second)
                self.assertEqual((first / 'manifest.json').read_bytes(), original)
                before = json.loads(original)
                after = json.loads((second / 'manifest.json').read_text())
                self.assertEqual(before['experiment_fingerprint'], after['experiment_fingerprint'])
                self.assertEqual(before['config'], after['config'])
                attempts = client.search_runs(['1'])
                self.assertEqual({r.info.status for r in attempts}, {'FAILED', 'FINISHED'})
                self.assertEqual({r.data.tags['experiment_fingerprint'] for r in attempts},
                                 {before['experiment_fingerprint']})
                self.assertEqual({r.data.tags['forecast_run'] for r in attempts}, {first.name, second.name})
