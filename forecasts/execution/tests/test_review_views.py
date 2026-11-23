"""Review selection must follow the requested execution, never a fixed old run."""
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch
import zlib

from forecasts.execution.tracking import tracking_client
from forecasts.execution.review_views import install


class ReviewViewTests(unittest.TestCase):
    def test_view_follows_selected_execution_and_rejects_comparison_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, FORECAST_DATA_ROOT=tmp), redirect_stdout(io.StringIO()) as output:
            client = tracking_client()
            experiment = client.create_experiment('germany-luxembourg-local',
                                                 artifact_location=(Path(tmp) / 'artifacts').as_uri())
            links = {}
            for _ in range(2):
                execution = client.create_run(experiment, tags={'record_type': 'execution'})
                install(execution.info.run_id, 'http://127.0.0.1:5001')
                link = next(line.removeprefix("Forecast review: ") for line in output.getvalue().splitlines()
                            if line.startswith("Forecast review: "))
                links[execution.info.run_id] = link
                output.seek(0)
                output.truncate()
            saved = client.get_experiment(experiment)
            assert saved is not None
            for parent_id, link in links.items():
                query = urlsplit(link).fragment.split("?", 1)[1]
                key = parse_qs(query)["viewStateShareKey"][0]
                encoded = json.loads(saved.tags[f"mlflow.sharedViewState.{key}"])["state"]
                state = json.loads(zlib.decompress(base64.b64decode(encoded.removeprefix('deflate;'))))
                self.assertEqual(state['searchFilter'], f"tags.`mlflow.parentRunId` = '{parent_id}'")
            child = client.create_run(experiment, tags={'record_type': 'comparison'})
            with self.assertRaisesRegex(ValueError, 'execution run'):
                install(child.info.run_id, 'http://127.0.0.1:5001')
