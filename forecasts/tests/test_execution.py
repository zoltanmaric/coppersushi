"""Accepted execution must match preserved code, dependencies and attempt identity."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from forecasts import run

CONFIG = Path(__file__).resolve().parents[1] / 'run-config.json'
FLOW = '''import argparse
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('command')
for name in ('config', 'snapshot', 'output', 'mlflow-run'):
    p.add_argument('--' + name)
a = p.parse_args()
Path(a.output, 'executed.txt').write_text(Path(__file__).with_name('marker.txt').read_text())
'''


class ExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'repo'
        sources = self.repo / 'forecasts'
        sources.mkdir(parents=True)
        (sources / '__init__.py').write_text('')
        (sources / 'flow.py').write_text(FLOW)
        (sources / 'marker.txt').write_text('frozen version')
        (sources / 'run-config.json').write_bytes(CONFIG.read_bytes())
        self.environment = run._environment()
        (sources / 'requirements-lock.txt').write_text(''.join(
            f'{name}=={version}\n' for name, version in sorted(self.environment['packages'].items())))
        for args in [('init', '-q'), ('add', 'forecasts'),
                     ('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Fixture')]:
            subprocess.run(['git', '-C', str(self.repo), *args], check=True)
        for name, value in [('ROOT', self.repo), ('DATA_ROOT', self.root / 'data'), ('RUNS', self.root / 'data/runs')]:
            patcher = patch.object(run, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unrestorable_environment_is_rejected_before_creating_run(self) -> None:
        environment = {**self.environment, 'packages': {**self.environment['packages'], 'unlocked-dev-tool': '1.0'}}
        with patch.object(run, '_environment', return_value=environment):
            with self.assertRaisesRegex(ValueError, 'unlocked-dev-tool'):
                run.prepare(self.repo / 'forecasts/run-config.json')
        self.assertFalse(run.RUNS.exists())

    def test_prepared_execution_ignores_later_checkout_edits(self) -> None:
        directory, _ = run.prepare(self.repo / 'forecasts/run-config.json')
        (self.repo / 'forecasts/marker.txt').write_text('edited checkout')
        (self.repo / 'forecasts/flow.py').write_text('raise AssertionError("mutable checkout executed")\n')
        run.run_flow(directory, self.root / 'snapshot')
        self.assertEqual((directory / 'executed.txt').read_text(), 'frozen version')
        manifest = json.loads((directory / 'manifest.json').read_text())
        client = run.tracking_client()
        experiment = client.get_experiment_by_name('germany-luxembourg-local')
        assert experiment is not None
        records = client.search_runs([experiment.experiment_id])
        self.assertEqual(records[0].info.status, 'FINISHED')
        self.assertFalse(manifest['exploratory'])
        self.assertEqual((self.repo / 'forecasts/marker.txt').read_text(), 'edited checkout')

    def test_reproduction_retries_preserve_failed_and_successful_attempts(self) -> None:
        source, _ = run.prepare(self.repo / 'forecasts/run-config.json')
        manifest = json.loads((source / 'manifest.json').read_text())
        manifest['artifacts'] = {'code.tar': run.digest(source / 'code.tar')}
        (source / 'manifest.json').write_text(json.dumps(manifest))
        calls = []

        def fail_install(args: list[str], **kwargs: object) -> None:
            if 'pip' in args:
                raise subprocess.CalledProcessError(1, args)

        def replay(args: list[str], **kwargs: object) -> None:
            if 'replay' in args:
                output = Path(args[args.index('--destination') + 1])
                output.mkdir()
                (output / 'verification.json').write_text(json.dumps({
                    'run_id': source.name, 'predictions_match': True, 'scores_match': True}))
                calls.append(output.parent)

        with patch.object(run.subprocess, 'run', side_effect=fail_install):
            with self.assertRaises(subprocess.CalledProcessError):
                run.reproduce(source.name, 'fixture', 'fixture', 'eu-west-1')
        parent = run.DATA_ROOT / 'reproductions' / source.name
        failed = next(parent.iterdir())
        original = (failed / 'attempt.json').read_bytes()
        self.assertEqual(json.loads(original)['status'], 'failed')
        with patch.object(run.subprocess, 'run', side_effect=replay):
            first = run.reproduce(source.name, 'fixture', 'fixture', 'eu-west-1')
            second = run.reproduce(source.name, 'fixture', 'fixture', 'eu-west-1')
        self.assertEqual(len({failed, first, second}), 3)
        self.assertEqual((failed / 'attempt.json').read_bytes(), original)
        for attempt in calls:
            self.assertEqual(json.loads((attempt / 'attempt.json').read_text())['status'], 'verified')
            self.assertTrue((attempt / 'result/verification.json').exists())
