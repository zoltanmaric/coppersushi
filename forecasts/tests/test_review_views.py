"""Review selection must follow the requested execution, never a fixed old run."""
import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

from forecasts import run
from forecasts.review_views import install


class ReviewViewTests(unittest.TestCase):
    def test_view_follows_selected_execution_and_rejects_comparison_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(run, 'DATA_ROOT', Path(tmp)), redirect_stdout(io.StringIO()):
            client = run.tracking_client()
            experiment = client.create_experiment('germany-luxembourg-local',
                                                 artifact_location=(Path(tmp) / 'artifacts').as_uri())
            for _ in range(2):
                execution = client.create_run(experiment, tags={'record_type': 'execution'})
                install(execution.info.run_id, 'http://127.0.0.1:5001')
                saved = client.get_experiment(experiment)
                assert saved is not None
                encoded = json.loads(saved.tags['mlflow.sharedViewState.forecast-run-review'])['state']
                state = json.loads(zlib.decompress(base64.b64decode(encoded.removeprefix('deflate;'))))
                self.assertEqual(state['searchFilter'], f"tags.`mlflow.parentRunId` = '{execution.info.run_id}'")
            child = client.create_run(experiment, tags={'record_type': 'comparison'})
            with self.assertRaisesRegex(ValueError, 'execution run'):
                install(child.info.run_id, 'http://127.0.0.1:5001')
