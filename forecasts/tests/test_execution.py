"""Frozen definitions, source isolation and retained reproduction attempts."""
import json
from pathlib import Path
import subprocess
import sys
import tarfile
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
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'repo'
        sources = self.repo / 'forecasts'
        sources.mkdir(parents=True)
        (sources / '__init__.py').write_text('')
        (sources / 'flow.py').write_text(FLOW)
        (sources / 'marker.txt').write_text('frozen version')
        (sources / 'run-config.json').write_bytes(CONFIG.read_bytes())
        self.proposal = self.repo / 'wiki/price-forecasting/research/proposal.md'
        self.proposal.parent.mkdir(parents=True)
        self.proposal.write_text('Frozen evaluation proposal')
        self.environment = run._environment()
        (self.repo / 'pyproject.toml').write_text('[project]\nname = "fixture"\n')
        (self.repo / 'pixi.lock').write_text('frozen runtime dependencies\n')
        for args in [('init', '-q'), ('add', 'forecasts', 'pyproject.toml', 'pixi.lock', 'wiki'),
                     ('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Fixture')]:
            subprocess.run(['git', '-C', str(self.repo), *args], check=True)
        for name, value in [('ROOT', self.repo), ('DATA_ROOT', self.root / 'data'), ('RUNS', self.root / 'data/runs')]:
            patcher = patch.object(run, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_preparation_freezes_definitions_without_using_launcher_packages(self) -> None:
        with patch.object(run, '_environment', side_effect=AssertionError('launcher is not the runtime')):
            directory, _ = run.prepare(self.repo / 'forecasts/run-config.json')
        manifest = json.loads((directory / 'manifest.json').read_text())
        self.assertNotIn('environment', manifest)
        for name, field in [('pixi.lock', 'lock_sha256'), ('pyproject.toml', 'project_sha256')]:
            self.assertEqual(run.digest(directory / name), manifest[field])
        with tarfile.open(directory / 'code.tar') as archive:
            self.assertIn('pixi.lock', archive.getnames())
            self.assertIn('pyproject.toml', archive.getnames())
        (self.repo / 'pixi.lock').write_text('uncommitted change')
        with self.assertRaisesRegex(ValueError, 'committed code'):
            run.prepare(self.repo / 'forecasts/run-config.json')

    def test_prepared_execution_ignores_later_source_and_lock_edits(self) -> None:
        directory, _ = run.prepare(self.repo / 'forecasts/run-config.json', proposal=self.proposal)
        self.proposal.write_text('edited proposal')
        (self.repo / 'forecasts/marker.txt').write_text('edited checkout')
        (self.repo / 'forecasts/flow.py').write_text('raise AssertionError("mutable checkout executed")\n')
        (self.repo / 'pixi.lock').write_text('different dependencies')
        # Substitute installation only; run the archived flow in a real subprocess.
        with patch.object(run, '_restore_runtime', return_value=[sys.executable]), \
                patch.object(run, '_probe_environment', return_value=self.environment):
            run.run_flow(directory, self.root / 'snapshot')
        self.assertEqual((directory / 'executed.txt').read_text(), 'frozen version')
        manifest = json.loads((directory / 'manifest.json').read_text())
        self.assertEqual(manifest['environment'], self.environment)
        self.assertEqual(manifest['proposal']['wiki_path'], self.proposal.relative_to(self.repo).as_posix())
        self.assertEqual(manifest['proposal']['git_revision'], manifest['code_revision'])
        self.assertEqual(manifest['proposal']['sha256'], run.digest(directory / 'proposal.md'))
        client = run.tracking_client()
        experiment = client.get_experiment_by_name('germany-luxembourg-local')
        assert experiment is not None
        tracked = client.search_runs([experiment.experiment_id])[0]
        self.assertEqual(tracked.info.status, 'FINISHED')
        frozen_proposal = Path(client.download_artifacts(tracked.info.run_id, 'research/proposal.md'))
        self.assertEqual(frozen_proposal.read_text(), 'Frozen evaluation proposal')
        self.assertEqual((self.repo / 'forecasts/marker.txt').read_text(), 'edited checkout')

    def test_changed_frozen_definitions_are_rejected_before_install(self) -> None:
        directory, _ = run.prepare(self.repo / 'forecasts/run-config.json')
        manifest = json.loads((directory / 'manifest.json').read_text())
        code = self.root / 'extracted'
        with tarfile.open(directory / 'code.tar') as archive:
            archive.extractall(code, filter='data')
        (code / 'pixi.lock').write_text('corrupt lock')
        with self.assertRaisesRegex(ValueError, 'pixi.lock'):
            run._restore_runtime(code, manifest, {})

    def test_reproduction_retries_preserve_failed_and_successful_attempts(self) -> None:
        source, _ = run.prepare(self.repo / 'forecasts/run-config.json')
        manifest = json.loads((source / 'manifest.json').read_text())
        manifest.update(environment=self.environment, artifacts={'code.tar': run.digest(source / 'code.tar')})
        (source / 'manifest.json').write_text(json.dumps(manifest))
        calls = []

        def fail_install(args: list[str], **kwargs: object) -> None:
            if 'install' in args:
                raise subprocess.CalledProcessError(1, args)

        def replay(args: list[str], **kwargs: object) -> None:
            if 'replay' in args:
                output = Path(args[args.index('--destination') + 1])
                output.mkdir()
                (output / 'verification.json').write_text(json.dumps({
                    'run_id': source.name, 'predictions_match': True, 'scores_match': True}))
                calls.append(output.parent)
                if len(calls) > 1:
                    self.assertEqual(args[args.index('--snapshot') + 1], str(self.root / 'snapshot'))
                    self.assertNotIn('--profile', args)

        with patch.object(run.subprocess, 'run', side_effect=fail_install):
            with self.assertRaises(subprocess.CalledProcessError):
                run.reproduce(source.name, 'fixture', 'fixture', 'eu-west-1')
        parent = run.DATA_ROOT / 'reproductions' / source.name
        failed = next(parent.iterdir())
        original = (failed / 'attempt.json').read_bytes()
        self.assertEqual(json.loads(original)['status'], 'failed')
        with patch.object(run.subprocess, 'run', side_effect=replay), \
                patch.object(run, '_probe_environment', return_value=self.environment):
            first = run.reproduce(source.name, 'fixture', 'fixture', 'eu-west-1')
            second = run.reproduce(source.name, snapshot=self.root / 'snapshot')
        self.assertEqual(len({failed, first, second}), 3)
        self.assertEqual((failed / 'attempt.json').read_bytes(), original)
        for attempt in calls:
            self.assertEqual(json.loads((attempt / 'attempt.json').read_text())['status'], 'verified')
            self.assertTrue((attempt / 'result/verification.json').exists())
